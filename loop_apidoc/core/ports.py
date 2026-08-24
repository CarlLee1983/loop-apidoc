from __future__ import annotations

from datetime import datetime
from typing import Protocol

from loop_apidoc.core.models import (
    ApprovalDecision,
    ContractRelease,
    EvidenceBundle,
    ExtractionWorkItem,
    RuntimeResult,
    SourceSet,
)
from loop_apidoc.core.persistence import (
    CommandReservation,
    CommitResult,
    CoreSnapshot,
    LifecycleCommit,
)
from loop_apidoc.domain.projections import Projection


class RuntimePort(Protocol):
    def propose(self, work_item: ExtractionWorkItem) -> RuntimeResult: ...


class SourcePort(Protocol):
    def acquire(self, source_set: SourceSet) -> EvidenceBundle: ...


class CoreUnitOfWork(Protocol):
    """Atomic lifecycle persistence with one aggregate-exclusive command fence."""

    def load(self, source_set_id: str) -> CoreSnapshot | None: ...

    def reserve(
        self,
        source_set_id: str,
        idempotency_key: str,
    ) -> CommandReservation: ...

    def commit(self, change: LifecycleCommit) -> CommitResult: ...

    def release(
        self,
        source_set_id: str,
        idempotency_key: str,
        reservation_token: str,
    ) -> None: ...


class ArtifactSink(Protocol):
    """Content-addressed publication sink; retrying identical content is safe."""

    def publish(
        self, release: ContractRelease, projections: tuple[Projection, ...]
    ) -> tuple[str, ...]: ...


class ApprovalPort(Protocol):
    def request(self, release: ContractRelease) -> ApprovalDecision: ...


class IdentityProvider(Protocol):
    def current_actor(self) -> str: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
