from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock

from loop_apidoc.core.models import (
    ApprovalDecision,
    ContractRelease,
    DomainEvent,
    EvidenceBundle,
    ReleaseStatus,
    SourceSet,
)
from loop_apidoc.core.artifacts import projection_content_address
from loop_apidoc.core.persistence import (
    CommandReceipt,
    CommandReservation,
    CommandInProgressError,
    CommitDisposition,
    CommitResult,
    ConcurrentCommitError,
    CoreSnapshot,
    LifecycleCommit,
    ReservationDisposition,
)
from loop_apidoc.domain.projections import Projection


@dataclass(frozen=True)
class _ActiveReservation:
    idempotency_key: str
    token: str


def _command_receipt(
    snapshot: CoreSnapshot,
    idempotency_key: str,
) -> CommandReceipt | None:
    return next(
        (
            receipt
            for receipt in snapshot.command_receipts
            if receipt.idempotency_key == idempotency_key
        ),
        None,
    )


class InMemoryCoreUnitOfWork:
    """CAS-backed aggregate persistence used by shadow execution and tests.

    The adapter models the durable contract: payload, workflow, current pointer,
    and events either become visible together or not at all.  ``fail_next_commit_at``
    exposes each logical boundary so callers can prove that guarantee.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, CoreSnapshot] = {}
        self._events: list[DomainEvent] = []
        self._event_ids: set[str] = set()
        self._reservations: dict[str, _ActiveReservation] = {}
        self._next_failure_boundary: str | None = None
        self._lose_next_commit_acknowledgement = False
        self._lock = RLock()

    @property
    def events(self) -> tuple[DomainEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def load(self, source_set_id: str) -> CoreSnapshot | None:
        with self._lock:
            return self._snapshots.get(source_set_id)

    def reserve(
        self,
        source_set_id: str,
        idempotency_key: str,
    ) -> CommandReservation:
        """Fence one aggregate before a caller can invoke an external port."""
        with self._lock:
            current = self._snapshots.get(source_set_id)
            if (
                current is not None
                and idempotency_key in current.workflow.processed_idempotency_keys
            ):
                receipt = _command_receipt(current, idempotency_key)
                if receipt is None:
                    raise RuntimeError(
                        "committed idempotency key has no durable command receipt: "
                        f"{idempotency_key}"
                    )
                return CommandReservation(
                    disposition=ReservationDisposition.ALREADY_COMMITTED,
                    snapshot=current,
                    receipt=receipt,
                )
            if source_set_id in self._reservations:
                return CommandReservation(
                    disposition=ReservationDisposition.IN_PROGRESS,
                    snapshot=current,
                )
            token = uuid.uuid4().hex
            self._reservations[source_set_id] = _ActiveReservation(
                idempotency_key=idempotency_key,
                token=token,
            )
            return CommandReservation(
                disposition=ReservationDisposition.ACQUIRED,
                snapshot=current,
                token=token,
            )

    def release(
        self,
        source_set_id: str,
        idempotency_key: str,
        reservation_token: str,
    ) -> None:
        """Release a reservation only when its full fence still matches."""
        with self._lock:
            active = self._reservations.get(source_set_id)
            if active == _ActiveReservation(
                idempotency_key=idempotency_key,
                token=reservation_token,
            ):
                del self._reservations[source_set_id]

    def fail_next_commit_at(self, boundary: str) -> None:
        if boundary not in {"payload", "workflow", "current", "event"}:
            raise ValueError(f"unknown commit boundary: {boundary}")
        with self._lock:
            self._next_failure_boundary = boundary

    def lose_next_commit_acknowledgement(self) -> None:
        """Commit once, then simulate a transport failure before the caller knows."""

        with self._lock:
            self._lose_next_commit_acknowledgement = True

    def commit(self, change: LifecycleCommit) -> CommitResult:
        with self._lock:
            active = self._reservations.get(change.source_set_id)
            if active != _ActiveReservation(
                idempotency_key=change.idempotency_key,
                token=change.reservation_token,
            ):
                current = self._snapshots.get(change.source_set_id)
                if (
                    current is not None
                    and change.idempotency_key
                    in current.workflow.processed_idempotency_keys
                ):
                    return CommitResult(
                        disposition=CommitDisposition.ALREADY_COMMITTED,
                        snapshot=current,
                    )
                raise CommandInProgressError(
                    "lifecycle commit does not hold the active reservation: "
                    f"{change.source_set_id}"
                )
            current = self._snapshots.get(change.source_set_id)
            if current != change.expected:
                if (
                    current is not None
                    and change.idempotency_key
                    in current.workflow.processed_idempotency_keys
                ):
                    del self._reservations[change.source_set_id]
                    return CommitResult(
                        disposition=CommitDisposition.ALREADY_COMMITTED,
                        snapshot=current,
                    )
                raise ConcurrentCommitError(
                    f"source-set changed before commit: {change.source_set_id}"
                )
            durable_change = self._append_command_receipt(change)
            self._validate_change(durable_change)
            for boundary in ("payload", "workflow", "current", "event"):
                if self._next_failure_boundary == boundary:
                    self._next_failure_boundary = None
                    raise RuntimeError(f"simulated commit failure at {boundary}")
            self._snapshots[durable_change.source_set_id] = durable_change.updated
            for event in durable_change.events:
                self._event_ids.add(event.id)
                self._events.append(event)
            del self._reservations[durable_change.source_set_id]
            if self._lose_next_commit_acknowledgement:
                self._lose_next_commit_acknowledgement = False
                raise RuntimeError("simulated commit acknowledgement loss")
            return CommitResult(
                disposition=CommitDisposition.APPLIED,
                snapshot=durable_change.updated,
            )

    @staticmethod
    def _append_command_receipt(change: LifecycleCommit) -> LifecycleCommit:
        expected_receipts = (
            change.expected.command_receipts if change.expected is not None else ()
        )
        if change.updated.command_receipts != expected_receipts:
            raise ValueError("lifecycle commands may only append their own receipt")
        receipt = CommandReceipt(
            idempotency_key=change.idempotency_key,
            workflow=change.updated.workflow,
            validation_decision=change.updated.validation_decision,
            release=change.updated.release,
        )
        return change.model_copy(
            update={
                "updated": change.updated.model_copy(
                    update={"command_receipts": expected_receipts + (receipt,)}
                )
            }
        )

    def _validate_change(self, change: LifecycleCommit) -> None:
        updated = change.updated
        if updated.source_set.id != change.source_set_id:
            raise ValueError("snapshot source set does not match commit")
        if updated.workflow.source_set_id != change.source_set_id:
            raise ValueError("workflow source set does not match commit")
        if change.idempotency_key not in updated.workflow.processed_idempotency_keys:
            raise ValueError("workflow does not record commit idempotency key")
        self._assert_command_receipts(change)
        if len({event.id for event in change.events}) != len(change.events):
            raise ValueError("commit event ids must be unique")
        if any(event.id in self._event_ids for event in change.events):
            raise ValueError("commit event was already persisted")

        expected = change.expected
        if expected is not None:
            self._assert_once_set_payloads(expected, updated)
        self._assert_release_and_current_are_coherent(expected, updated)

    @staticmethod
    def _assert_command_receipts(change: LifecycleCommit) -> None:
        expected_receipts = (
            change.expected.command_receipts if change.expected is not None else ()
        )
        updated_receipts = change.updated.command_receipts
        if updated_receipts[: len(expected_receipts)] != expected_receipts:
            raise ValueError("command receipts are immutable once recorded")
        if len(updated_receipts) != len(expected_receipts) + 1:
            raise ValueError("commit must append exactly one command receipt")
        receipt = updated_receipts[-1]
        if receipt.idempotency_key != change.idempotency_key:
            raise ValueError("command receipt does not match commit idempotency key")
        if receipt.workflow != change.updated.workflow:
            raise ValueError("command receipt workflow does not match committed workflow")
        if receipt.validation_decision != change.updated.validation_decision:
            raise ValueError(
                "command receipt validation decision does not match committed snapshot"
            )
        if receipt.release != change.updated.release:
            raise ValueError("command receipt release does not match committed snapshot")
        receipt_keys = frozenset(item.idempotency_key for item in updated_receipts)
        if len(receipt_keys) != len(updated_receipts):
            raise ValueError("command receipt idempotency keys must be unique")
        if receipt_keys != change.updated.workflow.processed_idempotency_keys:
            raise ValueError("command receipts and workflow keys differ")

    @staticmethod
    def _assert_once_set_payloads(
        expected: CoreSnapshot,
        updated: CoreSnapshot,
    ) -> None:
        if expected.source_set != updated.source_set:
            raise ValueError("source sets are immutable")
        for name in (
            "evidence_bundle",
            "runtime_result",
            "claims",
            "contract",
            "validation_decision",
            "projections",
        ):
            prior = getattr(expected, name)
            replacement = getattr(updated, name)
            if prior is not None and replacement != prior:
                raise ValueError(f"{name} is immutable once recorded")

    @staticmethod
    def _assert_release_and_current_are_coherent(
        expected: CoreSnapshot | None,
        updated: CoreSnapshot,
    ) -> None:
        previous_release = expected.release if expected is not None else None
        release = updated.release
        if previous_release is not None and release is not None:
            allowed = {
                ("candidate", "approved"),
                ("approved", "published"),
                ("published", "stale"),
                ("published", "superseded"),
                ("published", "revoked"),
                ("stale", "superseded"),
                ("stale", "revoked"),
            }
            if release != previous_release and (
                previous_release.status.value,
                release.status.value,
            ) not in allowed:
                raise ValueError("release content is immutable outside lifecycle transitions")
        if updated.current is not None:
            if release is None or release.status is not ReleaseStatus.PUBLISHED:
                raise ValueError("a current pointer requires a published release")
            if (
                updated.current.contract_id != release.contract_id
                or updated.current.release_id != release.release_id
                or updated.current.status is not release.status
            ):
                raise ValueError("current pointer does not match published release")
        elif release is not None and release.status is ReleaseStatus.PUBLISHED:
            raise ValueError("a published release requires a current pointer")
        if expected is not None and expected.current is not None:
            if updated.current != expected.current:
                raise ValueError("current pointers are immutable within one release")

class InMemoryArtifactSink:
    def __init__(self) -> None:
        self.publications: dict[str, tuple[Projection, ...]] = {}

    def publish(
        self,
        release: ContractRelease,
        projections: tuple[Projection, ...],
    ) -> tuple[str, ...]:
        if release.status is not ReleaseStatus.APPROVED:
            raise ValueError("only approved releases may publish artifacts")
        if not projections:
            raise ValueError("artifact publication requires at least one projection")
        publication_id = projection_content_address(projections)
        existing = self.publications.get(publication_id)
        if existing is not None and existing != projections:
            raise ValueError("published projections are immutable")
        self.publications[publication_id] = projections
        return tuple(
            f"memory://{publication_id}/{projection.name}" for projection in projections
        )


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class StaticApprovalAdapter:
    def __init__(self, decision: ApprovalDecision) -> None:
        self.decision = decision
        self.requests = 0

    def request(self, release: ContractRelease) -> ApprovalDecision:
        del release
        self.requests += 1
        return self.decision


class StaticSourceAdapter:
    def __init__(self, bundle: EvidenceBundle) -> None:
        self.bundle = bundle

    def acquire(self, source_set: SourceSet) -> EvidenceBundle:
        if (source_set.id, source_set.version) != (
            self.bundle.source_set_id,
            self.bundle.source_set_version,
        ):
            raise ValueError("static evidence bundle does not match source set")
        return self.bundle
