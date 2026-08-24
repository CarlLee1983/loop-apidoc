from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from loop_apidoc.core.governance import (
    ApprovalRejected,
    approve_release,
    make_candidate_release,
    publish_release,
)
from loop_apidoc.core.lifecycle import LifecycleMachine
from loop_apidoc.core.models import (
    Actor,
    ActorKind,
    CurrentPointer,
    DomainEvent,
    ExtractionWorkItem,
    LifecycleState,
    PolicyProfile,
    ReleaseStatus,
    ValidationVerdict,
    WorkflowRecord,
)
from loop_apidoc.core.persistence import (
    CommandReceipt,
    CommandInProgressError,
    ConcurrentCommitError,
    CoreSnapshot,
    LifecycleCommit,
    ReservationDisposition,
)
from loop_apidoc.core.policy import ValidationPolicyEngine
from loop_apidoc.core.ports import (
    ApprovalPort,
    ArtifactSink,
    Clock,
    CoreUnitOfWork,
    RuntimePort,
    SourcePort,
)
from loop_apidoc.core.reconciliation import reconcile_claims
from loop_apidoc.domain.builder import ContractClaimInput, build_grounded_contract
from loop_apidoc.domain.models import ContractMetadata
from loop_apidoc.domain.projections import ProjectionCompiler, ProjectionInput
from loop_apidoc.domain.rules import ApiDomainRulePack


@dataclass(frozen=True)
class _ReservedCommand:
    source_set_id: str
    key: str
    snapshot: CoreSnapshot | None
    reservation_token: str | None
    receipt: CommandReceipt | None = None
    replay: bool = False


class EvidenceToContractService:
    """Coordinates Core lifecycle effects around one atomic aggregate commit.

    Every command acquires an aggregate-exclusive reservation before it
    preflights or invokes a source, runtime, approver, or artifact sink. Payloads,
    lifecycle state, current pointer, audit events, and a command receipt then
    commit with that reservation's fencing token as one CAS update.
    """

    def __init__(
        self,
        *,
        source: SourcePort,
        runtime: RuntimePort,
        unit_of_work: CoreUnitOfWork,
        artifact_sink: ArtifactSink,
        approval: ApprovalPort,
        clock: Clock,
        domain_rules: ApiDomainRulePack,
        policy_profile: PolicyProfile | None = None,
    ) -> None:
        self.source = source
        self.runtime = runtime
        self.unit_of_work = unit_of_work
        self.artifact_sink = artifact_sink
        self.approval_port = approval
        self.clock = clock
        self.domain_rules = domain_rules
        self.policy_profile = policy_profile or PolicyProfile(name="strict")
        self.lifecycle = LifecycleMachine()
        self.policy = ValidationPolicyEngine()

    def register_source_set(self, source_set) -> WorkflowRecord:
        key = _operation_key(
            source_set.id, "register", source_set.model_dump(mode="json")
        )
        command = self._reserve(source_set.id, key)
        if command.replay:
            return _require(command.receipt, "registered command receipt").workflow
        try:
            if command.snapshot is not None:
                raise ConcurrentCommitError(
                    f"source set is already registered: {source_set.id}"
                )
            record = WorkflowRecord(
                source_set_id=source_set.id,
                state=LifecycleState.REGISTERED,
                artifacts=frozenset({"source_set"}),
                processed_idempotency_keys=frozenset({key}),
            )
            event = DomainEvent(
                id=_id(source_set.id, "register"),
                aggregate_id=source_set.id,
                kind="lifecycle.registered",
                actor=Actor(id="core", kind=ActorKind.SYSTEM),
                occurred_at=self.clock.now(),
                correlation_id=key,
            )
            committed = self._commit(
                command,
                CoreSnapshot(source_set=source_set, workflow=record),
                (event,),
            )
            return committed.workflow
        except BaseException:
            self._release(command)
            raise

    def acquire(self, source_set_id: str) -> None:
        command = self._begin(source_set_id, "acquire")
        if command.replay:
            return
        snapshot = self._require_command_snapshot(command)
        actor = Actor(id="source-adapter", kind=ActorKind.SYSTEM)
        try:
            self._preflight(
                snapshot,
                LifecycleState.ACQUIRED,
                actor,
                command.key,
                frozenset({"evidence_bundle"}),
            )
        except BaseException:
            self._release(command)
            raise
        bundle = self.source.acquire(snapshot.source_set)
        if (bundle.source_set_id, bundle.source_set_version) != (
            snapshot.source_set.id,
            snapshot.source_set.version,
        ):
            raise ValueError("acquired evidence bundle does not match source set")
        workflow, event = self._transition(
            snapshot.workflow,
            LifecycleState.ACQUIRED,
            actor,
            command.key,
            frozenset({"evidence_bundle"}),
        )
        self._commit(
            command,
            snapshot.model_copy(
                update={"evidence_bundle": bundle, "workflow": workflow}
            ),
            (event,),
        )

    def request_claim_proposals(
        self,
        source_set_id: str,
        requested_claim_kinds: tuple[str, ...],
    ) -> None:
        command = self._begin(
            source_set_id,
            "propose",
            {"requested_claim_kinds": requested_claim_kinds},
        )
        if command.replay:
            return
        snapshot = self._require_command_snapshot(command)
        try:
            self._preflight(
                snapshot,
                LifecycleState.CLAIMS_PROPOSED,
                Actor(id="runtime", kind=ActorKind.RUNTIME),
                command.key,
                frozenset({"runtime_result"}),
            )
            bundle = _require(snapshot.evidence_bundle, "evidence bundle")
            work_item = ExtractionWorkItem(
                task_id=_id(source_set_id, "proposal"),
                evidence_scope=tuple(fragment.id for fragment in bundle.fragments),
                requested_claim_kinds=requested_claim_kinds,
                output_schema="claim-proposal/v1",
                grounding_constraints=("evidence-reference-required",),
                correlation_id=_id(source_set_id, "correlation"),
            )
        except BaseException:
            self._release(command)
            raise
        result = self.runtime.propose(work_item)
        workflow, event = self._transition(
            snapshot.workflow,
            LifecycleState.CLAIMS_PROPOSED,
            Actor(id=result.runtime_identity, kind=ActorKind.RUNTIME),
            command.key,
            frozenset({"runtime_result"}),
        )
        workflow = workflow.model_copy(
            update={"runtime_identities": (result.runtime_identity,)}
        )
        self._commit(
            command,
            snapshot.model_copy(
                update={"runtime_result": result, "workflow": workflow}
            ),
            (event,),
        )

    def reconcile(self, source_set_id: str) -> None:
        command = self._begin(source_set_id, "reconcile")
        if command.replay:
            return
        snapshot = self._require_command_snapshot(command)
        try:
            actor = Actor(id="reconciler", kind=ActorKind.SYSTEM)
            self._preflight(
                snapshot,
                LifecycleState.RECONCILED,
                actor,
                command.key,
                frozenset({"grounded_claims"}),
            )
            result = _require(snapshot.runtime_result, "runtime result")
            claims = reconcile_claims(
                result.claim_proposals,
                evidence_bundle=_require(snapshot.evidence_bundle, "evidence bundle"),
            )
            workflow, event = self._transition(
                snapshot.workflow,
                LifecycleState.RECONCILED,
                actor,
                command.key,
                frozenset({"grounded_claims"}),
            )
            self._commit(
                command,
                snapshot.model_copy(update={"claims": claims, "workflow": workflow}),
                (event,),
            )
        except BaseException:
            self._release(command)
            raise

    def build_contract(self, source_set_id: str, metadata: ContractMetadata) -> None:
        command = self._begin(
            source_set_id,
            "build-contract",
            metadata.model_dump(mode="json"),
        )
        if command.replay:
            return
        snapshot = self._require_command_snapshot(command)
        try:
            actor = Actor(id="domain-pack", kind=ActorKind.SYSTEM)
            self._preflight(
                snapshot,
                LifecycleState.CONTRACT_BUILT,
                actor,
                command.key,
                frozenset({"contract"}),
            )
            claims = _require(snapshot.claims, "grounded claims")
            contract = build_grounded_contract(
                metadata,
                tuple(
                    ContractClaimInput(
                        identity=claim.canonical_identity,
                        claim_kind=claim.claim_kind,
                        value=claim.value,
                        status=claim.status,
                        evidence_refs=claim.evidence_refs,
                        support_relationships=claim.support_relationships,
                    )
                    for claim in claims
                ),
            )
            workflow, event = self._transition(
                snapshot.workflow,
                LifecycleState.CONTRACT_BUILT,
                actor,
                command.key,
                frozenset({"contract"}),
            )
            self._commit(
                command,
                snapshot.model_copy(update={"contract": contract, "workflow": workflow}),
                (event,),
            )
        except BaseException:
            self._release(command)
            raise

    def validate(
        self,
        source_set_id: str,
        compilers: tuple[ProjectionCompiler, ...] = (),
    ):
        compiler_versions = tuple(
            (compiler.name, compiler.version) for compiler in compilers
        )
        command = self._begin(
            source_set_id,
            "validate",
            {
                "compilers": compiler_versions,
                "policy_profile": self.policy_profile.model_dump(mode="json"),
            },
        )
        if command.replay:
            return _require(
                _require(command.receipt, "validated command receipt").validation_decision,
                "validation decision",
            )
        snapshot = self._require_command_snapshot(command)
        try:
            actor = Actor(id="policy", kind=ActorKind.POLICY)
            self._preflight(
                snapshot,
                LifecycleState.VALIDATED,
                actor,
                command.key,
                frozenset({"validation_decision"}),
            )
            contract = _require(snapshot.contract, "grounded contract")
            decision = self.policy.decide(
                self.domain_rules.evaluate(contract),
                self.policy_profile,
                now=self.clock.now(),
            )
            if decision.verdict is ValidationVerdict.REJECT:
                workflow, event = self._transition(
                    snapshot.workflow,
                    LifecycleState.VALIDATED,
                    actor,
                    command.key,
                    frozenset({"validation_decision"}),
                )
                committed = self._commit(
                    command,
                    snapshot.model_copy(
                        update={"validation_decision": decision, "workflow": workflow}
                    ),
                    (event,),
                )
                return _require(committed.validation_decision, "validation decision")

            projection_input = ProjectionInput(
                contract=contract,
                source_set=snapshot.source_set,
                evidence=_require(snapshot.evidence_bundle, "evidence bundle"),
            )
            projections = tuple(
                compiler.compile(projection_input) for compiler in compilers
            )
            candidate = make_candidate_release(
                contract,
                decision,
                runtime_identities=snapshot.workflow.runtime_identities,
                core_version="1",
                policy_version=self.policy_profile.name,
                projection_versions=compiler_versions,
                now=self.clock.now(),
            )
            validated_workflow, validated_event = self._transition(
                snapshot.workflow,
                LifecycleState.VALIDATED,
                actor,
                command.key,
                frozenset(
                    {"validation_decision", "candidate_release", "projections"}
                ),
            )
            target = (
                LifecycleState.REVIEW_REQUIRED
                if decision.verdict is ValidationVerdict.REVIEW
                else LifecycleState.APPROVAL_READY
            )
            routed_workflow, routed_event = self._transition(
                validated_workflow,
                target,
                actor,
                command.key,
            )
            committed = self._commit(
                command,
                snapshot.model_copy(
                    update={
                        "validation_decision": decision,
                        "projections": projections,
                        "release": candidate,
                        "workflow": routed_workflow,
                    }
                ),
                (validated_event, routed_event),
            )
            return _require(committed.validation_decision, "validation decision")
        except BaseException:
            self._release(command)
            raise

    def approve(self, source_set_id: str):
        command = self._begin(source_set_id, "approve")
        if command.replay:
            return _require(
                _require(command.receipt, "approved command receipt").release,
                "release",
            )
        snapshot = self._require_command_snapshot(command)
        try:
            self._preflight(
                snapshot,
                LifecycleState.APPROVED,
                Actor(id="approver", kind=ActorKind.APPROVER),
                command.key,
            )
            candidate = _require(snapshot.release, "candidate release")
        except BaseException:
            self._release(command)
            raise
        decision = self.approval_port.request(candidate)
        try:
            approved = approve_release(candidate, decision)
        except ApprovalRejected:
            # A negative decision is fully known and changed no aggregate state,
            # so it must not strand this exact command's reservation.
            self._release(command)
            raise
        workflow, event = self._transition(
            snapshot.workflow,
            LifecycleState.APPROVED,
            Actor(id=approved.approved_by or "approver", kind=ActorKind.APPROVER),
            command.key,
        )
        committed = self._commit(
            command,
            snapshot.model_copy(update={"release": approved, "workflow": workflow}),
            (event,),
        )
        return _require(committed.release, "approved release")

    def publish(self, source_set_id: str):
        command = self._begin(source_set_id, "publish")
        if command.replay:
            return _require(
                _require(command.receipt, "published command receipt").release,
                "release",
            )
        snapshot = self._require_command_snapshot(command)
        try:
            actor = Actor(id="publisher", kind=ActorKind.PUBLISHER)
            self._preflight(
                snapshot,
                LifecycleState.PUBLISHED,
                actor,
                command.key,
            )
            approved = _require(snapshot.release, "approved release")
            if approved.status is not ReleaseStatus.APPROVED:
                raise ApprovalRejected("only approved releases can be published")
            projections = _require(snapshot.projections, "compiled projections")
            refs = self.artifact_sink.publish(approved, projections)
            published = publish_release(approved, refs, self.clock.now())
            workflow, event = self._transition(
                snapshot.workflow,
                LifecycleState.PUBLISHED,
                actor,
                command.key,
            )
            committed = self._commit(
                command,
                snapshot.model_copy(
                    update={
                        "release": published,
                        "current": CurrentPointer(
                            contract_id=published.contract_id,
                            release_id=published.release_id,
                            status=published.status,
                        ),
                        "workflow": workflow,
                    }
                ),
                (event,),
            )
            return _require(committed.release, "published release")
        except BaseException:
            # Artifact sinks are content-addressed: retrying the exact release
            # and projections is safe even if the caller lost the first result.
            self._release(command)
            raise

    def _begin(
        self,
        source_set_id: str,
        action: str,
        payload: Any = None,
    ) -> _ReservedCommand:
        key = _operation_key(source_set_id, action, payload)
        command = self._reserve(source_set_id, key)
        if not command.replay and command.snapshot is None:
            self._release(command)
            raise ValueError(f"source set is not registered: {source_set_id}")
        return command

    def _reserve(self, source_set_id: str, key: str) -> _ReservedCommand:
        reservation = self.unit_of_work.reserve(source_set_id, key)
        if reservation.disposition is ReservationDisposition.IN_PROGRESS:
            raise CommandInProgressError(
                f"command is in progress for source set: {source_set_id}"
            )
        if reservation.disposition is ReservationDisposition.ALREADY_COMMITTED:
            return _ReservedCommand(
                source_set_id=source_set_id,
                key=key,
                snapshot=_require(reservation.snapshot, "committed source-set snapshot"),
                reservation_token=None,
                receipt=_require(reservation.receipt, "committed command receipt"),
                replay=True,
            )
        if reservation.disposition is not ReservationDisposition.ACQUIRED:
            raise RuntimeError("unknown command reservation disposition")
        return _ReservedCommand(
            source_set_id=source_set_id,
            key=key,
            snapshot=reservation.snapshot,
            reservation_token=_require(reservation.token, "command reservation token"),
        )

    def _require_command_snapshot(self, command: _ReservedCommand) -> CoreSnapshot:
        if command.snapshot is None:
            self._release(command)
            raise ValueError(f"source set is not registered: {command.source_set_id}")
        return command.snapshot

    def _release(self, command: _ReservedCommand) -> None:
        if command.reservation_token is not None:
            self.unit_of_work.release(
                command.source_set_id,
                command.key,
                command.reservation_token,
            )

    def _preflight(
        self,
        snapshot: CoreSnapshot,
        target: LifecycleState,
        actor: Actor,
        key: str,
        artifacts: frozenset[str] = frozenset(),
    ) -> None:
        self.lifecycle.preflight(
            snapshot.workflow,
            target,
            actor=actor,
            idempotency_key=key,
            artifacts=artifacts,
        )

    def _transition(
        self,
        record: WorkflowRecord,
        target: LifecycleState,
        actor: Actor,
        key: str,
        artifacts: frozenset[str] = frozenset(),
    ) -> tuple[WorkflowRecord, DomainEvent]:
        workflow, event = self.lifecycle.transition(
            record,
            target,
            actor=actor,
            idempotency_key=key,
            artifacts=artifacts,
        )
        if event is None:
            raise RuntimeError("a preflighted transition unexpectedly produced no event")
        return workflow, event.model_copy(update={"occurred_at": self.clock.now()})

    def _commit(
        self,
        command: _ReservedCommand,
        updated: CoreSnapshot,
        events: tuple[DomainEvent, ...],
    ) -> CoreSnapshot:
        return self.unit_of_work.commit(
            LifecycleCommit(
                source_set_id=command.source_set_id,
                idempotency_key=command.key,
                reservation_token=_require(
                    command.reservation_token,
                    "active command reservation token",
                ),
                expected=command.snapshot,
                updated=updated,
                events=events,
            )
        ).snapshot


def _require(value: Any, label: str):
    if value is None:
        raise ValueError(f"{label} is unavailable for this lifecycle state")
    return value


def _id(aggregate: str, action: str) -> str:
    return hashlib.sha256(f"{aggregate}:{action}".encode()).hexdigest()[:20]


def _operation_key(source_set_id: str, action: str, payload: Any = None) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]
    return f"{source_set_id}:{action}:{digest}"


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, frozenset):
        return sorted(value)
    raise TypeError(f"cannot derive an idempotency key from {type(value)!r}")
