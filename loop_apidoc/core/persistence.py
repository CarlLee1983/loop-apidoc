from __future__ import annotations

from enum import Enum

from pydantic import ConfigDict

from loop_apidoc.core.models import (
    ContractRelease,
    CurrentPointer,
    DomainEvent,
    GroundedClaim,
    RuntimeResult,
    SourceSet,
    ValidationDecision,
    WorkflowRecord,
)
from loop_apidoc.domain.evidence import EvidenceBundle
from loop_apidoc.domain.models import FrozenModel, GroundedApiContract
from loop_apidoc.domain.projections import Projection


class CommandReceipt(FrozenModel):
    """The immutable result of one successfully committed idempotent command."""

    idempotency_key: str
    workflow: WorkflowRecord
    validation_decision: ValidationDecision | None = None
    release: ContractRelease | None = None


class CoreSnapshot(FrozenModel):
    """The complete persistent state of one source-set lifecycle aggregate."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    source_set: SourceSet
    workflow: WorkflowRecord
    evidence_bundle: EvidenceBundle | None = None
    runtime_result: RuntimeResult | None = None
    claims: tuple[GroundedClaim, ...] | None = None
    contract: GroundedApiContract | None = None
    validation_decision: ValidationDecision | None = None
    projections: tuple[Projection, ...] | None = None
    release: ContractRelease | None = None
    current: CurrentPointer | None = None
    command_receipts: tuple[CommandReceipt, ...] = ()


class ReservationDisposition(str, Enum):
    """Whether a command acquired the aggregate's execution fence."""

    ACQUIRED = "acquired"
    ALREADY_COMMITTED = "already_committed"
    IN_PROGRESS = "in_progress"


class CommandReservation(FrozenModel):
    """The atomic outcome of reserving one aggregate command.

    An acquired reservation carries a fencing token that must accompany the
    lifecycle commit.  A committed command returns its durable receipt and
    latest snapshot, while an in-progress result deliberately grants no
    permission to run effects.
    """

    disposition: ReservationDisposition
    snapshot: CoreSnapshot | None = None
    token: str | None = None
    receipt: CommandReceipt | None = None


class LifecycleCommit(FrozenModel):
    """An optimistic, all-or-nothing lifecycle update for one aggregate."""

    source_set_id: str
    idempotency_key: str
    reservation_token: str
    updated: CoreSnapshot
    expected: CoreSnapshot | None = None
    events: tuple[DomainEvent, ...] = ()


class CommitDisposition(str, Enum):
    APPLIED = "applied"
    ALREADY_COMMITTED = "already_committed"


class CommitResult(FrozenModel):
    disposition: CommitDisposition
    snapshot: CoreSnapshot


class ConcurrentCommitError(RuntimeError):
    """A lifecycle aggregate changed before a distinct operation could commit."""


class CommandInProgressError(ConcurrentCommitError):
    """The aggregate is fenced by another command that may have run an effect."""
