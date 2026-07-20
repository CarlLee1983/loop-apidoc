from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.core.models import (
    ApprovalDecision,
    ContractRelease,
    CurrentPointer,
    DomainEvent,
    EvidenceBundle,
    GroundedClaim,
    RuntimeResult,
    SourceSet,
    WorkflowRecord,
)
from loop_apidoc.domain.models import GroundedApiContract
from loop_apidoc.domain.projections import Projection


class InMemoryEvidenceStore:
    def __init__(self) -> None:
        self.source_sets: dict[str, SourceSet] = {}
        self.bundles: dict[str, EvidenceBundle] = {}

    def put_source_set(self, source_set: SourceSet) -> None:
        existing = self.source_sets.get(source_set.id)
        if existing is not None and existing != source_set:
            raise ValueError("source-set versions are immutable")
        self.source_sets[source_set.id] = source_set

    def get_source_set(self, source_set_id: str) -> SourceSet:
        return self.source_sets[source_set_id]

    def put_bundle(self, bundle: EvidenceBundle) -> None:
        existing = self.bundles.get(bundle.source_set_id)
        if existing is not None and existing != bundle:
            raise ValueError("evidence bundles are immutable")
        self.bundles[bundle.source_set_id] = bundle

    def get_bundle(self, source_set_id: str) -> EvidenceBundle:
        return self.bundles[source_set_id]


class InMemoryContractStore:
    def __init__(self) -> None:
        self.workflows: dict[str, WorkflowRecord] = {}
        self.runtime_results: dict[str, RuntimeResult] = {}
        self.claims: dict[str, tuple[GroundedClaim, ...]] = {}
        self.contracts: dict[str, GroundedApiContract] = {}
        self.projections: dict[str, tuple[Projection, ...]] = {}
        self.releases: dict[str, ContractRelease] = {}
        self.current: dict[str, CurrentPointer] = {}

    def put_workflow(self, record: WorkflowRecord) -> None:
        self.workflows[record.source_set_id] = record

    def get_workflow(self, source_set_id: str) -> WorkflowRecord:
        return self.workflows[source_set_id]

    def put_runtime_result(self, source_set_id: str, result: RuntimeResult) -> None:
        self.runtime_results[source_set_id] = result

    def get_runtime_result(self, source_set_id: str) -> RuntimeResult:
        return self.runtime_results[source_set_id]

    def put_claims(self, source_set_id: str, claims: tuple[GroundedClaim, ...]) -> None:
        self.claims[source_set_id] = claims

    def get_claims(self, source_set_id: str) -> tuple[GroundedClaim, ...]:
        return self.claims[source_set_id]

    def put_contract(self, source_set_id: str, contract: GroundedApiContract) -> None:
        existing = self.contracts.get(source_set_id)
        if existing is not None and existing != contract:
            raise ValueError("contract snapshots are immutable")
        self.contracts[source_set_id] = contract

    def get_contract(self, source_set_id: str) -> GroundedApiContract:
        return self.contracts[source_set_id]

    def put_projections(
        self,
        source_set_id: str,
        projections: tuple[Projection, ...],
    ) -> None:
        existing = self.projections.get(source_set_id)
        if existing is not None and existing != projections:
            raise ValueError("compiled projections are immutable")
        self.projections[source_set_id] = projections

    def get_projections(self, source_set_id: str) -> tuple[Projection, ...]:
        return self.projections[source_set_id]

    def put_release(self, release: ContractRelease) -> None:
        existing = self.releases.get(release.release_id)
        if existing is not None:
            allowed = {
                ("candidate", "approved"),
                ("approved", "published"),
                ("published", "stale"),
                ("published", "superseded"),
                ("published", "revoked"),
                ("stale", "superseded"),
                ("stale", "revoked"),
            }
            if (
                existing.status.value,
                release.status.value,
            ) not in allowed and existing != release:
                raise ValueError(
                    "release content is immutable outside lifecycle transitions"
                )
        self.releases[release.release_id] = release

    def get_release(self, release_id: str) -> ContractRelease:
        return self.releases[release_id]

    def put_current(self, pointer: CurrentPointer) -> None:
        self.current[pointer.contract_id] = pointer


class InMemoryArtifactSink:
    def __init__(self) -> None:
        self.publications: dict[str, tuple[Projection, ...]] = {}

    def publish(
        self,
        release_id: str,
        projections: tuple[Projection, ...],
    ) -> tuple[str, ...]:
        existing = self.publications.get(release_id)
        if existing is not None and existing != projections:
            raise ValueError("published projections are immutable")
        self.publications[release_id] = projections
        return tuple(
            f"memory://{release_id}/{projection.name}" for projection in projections
        )


class InMemoryEventSink:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []
        self._ids: set[str] = set()

    def append(self, event: DomainEvent) -> None:
        if event.id in self._ids:
            return
        self._ids.add(event.id)
        self.events.append(event)


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

    def request(self, release: ContractRelease) -> ApprovalDecision:
        del release
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
