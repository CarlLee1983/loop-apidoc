from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from loop_apidoc.domain.evidence import (
    ClaimEvidenceRelationship as ClaimEvidenceRelationship,
    ClaimSupportProposal as ClaimSupportProposal,
    EvidenceBundle as EvidenceBundle,
    EvidenceFragment as EvidenceFragment,
    SourceArtifact as SourceArtifact,
    SourceDescriptor as SourceDescriptor,
    SourceSet as SourceSet,
)
from loop_apidoc.domain.models import ClaimStatus, FrozenModel, GroundedApiContract
from loop_apidoc.domain.projections import Projection


class ClaimProposal(FrozenModel):
    id: str
    claim_kind: str
    subject: str
    predicate: str
    value: Any = None
    evidence_refs: tuple[str, ...] = ()
    runtime_identity: str
    runtime_observation: str | None = None
    confidence: float | None = None


class GroundedClaim(FrozenModel):
    id: str
    canonical_identity: str
    claim_kind: str
    value: Any = None
    evidence_refs: tuple[str, ...] = ()
    status: ClaimStatus
    lineage: tuple[str, ...] = ()


class ExtractionWorkItem(FrozenModel):
    task_id: str
    evidence_scope: tuple[str, ...]
    requested_claim_kinds: tuple[str, ...]
    output_schema: str
    grounding_constraints: tuple[str, ...] = ()
    resource_budget: tuple[tuple[str, float], ...] = ()
    deadline: datetime | None = None
    correlation_id: str


class ResourceUsage(FrozenModel):
    input_units: float | None = None
    output_units: float | None = None
    cost: float | None = None
    latency_ms: float | None = None


class RuntimeResult(FrozenModel):
    claim_proposals: tuple[ClaimProposal, ...] = ()
    diagnostics: tuple[str, ...] = ()
    runtime_identity: str
    runtime_version: str
    execution_trace_ref: str | None = None
    resource_usage: ResourceUsage = ResourceUsage()


class ActorKind(str, Enum):
    SYSTEM = "system"
    RUNTIME = "runtime"
    POLICY = "policy"
    APPROVER = "approver"
    PUBLISHER = "publisher"


class Actor(FrozenModel):
    id: str
    kind: ActorKind


class LifecycleState(str, Enum):
    REGISTERED = "registered"
    ACQUIRED = "acquired"
    CLAIMS_PROPOSED = "claims_proposed"
    RECONCILED = "reconciled"
    CONTRACT_BUILT = "contract_built"
    VALIDATED = "validated"
    REVIEW_REQUIRED = "review_required"
    APPROVAL_READY = "approval_ready"
    APPROVED = "approved"
    PUBLISHED = "published"
    STALE = "stale"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class WorkflowRecord(FrozenModel):
    source_set_id: str
    state: LifecycleState
    artifacts: frozenset[str] = frozenset()
    processed_idempotency_keys: frozenset[str] = frozenset()
    runtime_identities: tuple[str, ...] = ()


class DomainEvent(FrozenModel):
    id: str
    aggregate_id: str
    kind: str
    actor: Actor
    occurred_at: datetime | None = None
    correlation_id: str | None = None


class ValidationVerdict(str, Enum):
    ACCEPT = "accept"
    REVIEW = "review"
    REJECT = "reject"


class PolicyProfile(FrozenModel):
    name: str
    severity_overrides: tuple[tuple[str, str], ...] = ()
    human_review_on_warnings: bool = False
    allow_waivers: bool = True


class Waiver(FrozenModel):
    id: str
    claim_identity: str
    reason: str
    approved_by: str
    expires_at: datetime
    scope: tuple[str, ...] = ()


class PolicyFinding(FrozenModel):
    code: str
    message: str
    location: str
    severity: str
    claim_identity: str | None = None
    root_cause: str | None = None
    waiver_id: str | None = None


class CorrectionRequest(FrozenModel):
    root_cause: str
    finding_codes: tuple[str, ...]
    evidence_scope: tuple[str, ...] = ()


class ValidationDecision(FrozenModel):
    verdict: ValidationVerdict
    policy_profile: str
    findings: tuple[PolicyFinding, ...] = ()
    corrections: tuple[CorrectionRequest, ...] = ()


class ApprovalDecision(FrozenModel):
    approved: bool
    actor: Actor
    decided_at: datetime
    reason: str | None = None


class ReleaseStatus(str, Enum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    PUBLISHED = "published"
    STALE = "stale"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class ContractRelease(FrozenModel):
    release_id: str
    contract_id: str
    contract_digest: str
    source_set_id: str
    source_set_version: str
    status: ReleaseStatus
    validation: ValidationDecision
    runtime_identities: tuple[str, ...]
    core_version: str
    domain_version: str
    policy_version: str
    projection_versions: tuple[tuple[str, str], ...]
    created_at: datetime
    approved_at: datetime | None = None
    approved_by: str | None = None
    published_at: datetime | None = None
    artifact_refs: tuple[str, ...] = ()
    supersedes: str | None = None


class CurrentPointer(FrozenModel):
    contract_id: str
    release_id: str
    status: ReleaseStatus


ProjectionValues = tuple[Projection, ...]
ContractValue = GroundedApiContract
