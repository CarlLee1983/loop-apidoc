from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loop_apidoc.domain.conformance import (
    ApplicabilityEnvelope,
    FeedbackRoute,
    IdentityVersion,
)


class AssetStatus(str, Enum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class ReviewState(str, Enum):
    """Whether a governed asset has outstanding human-review follow-up work."""

    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    NEEDS_FOLLOW_UP = "needs_follow_up"


class SourceRole(str, Enum):
    PRIMARY = "primary"
    SUPPLEMENTAL = "supplemental"


class FoundryInputError(ValueError):
    """A Foundry operation cannot proceed because a docset, candidate, or run
    artifact is missing or invalid."""


class FoundryCurrentStaleError(FoundryInputError):
    """The normative current head cannot be trusted for this operation."""


class FoundryGovernedAssetNotApprovedError(FoundryInputError):
    """A historical governed asset is not an approved release."""


class FoundryGovernedAssetApprovalLineageError(FoundryInputError):
    """A governed historical asset lacks the required approval lineage."""


class FoundryPublicationError(ValueError):
    """Approval failed and rollback or cleanup also failed."""


class FoundryApprovalError(ValueError):
    """A candidate cannot be approved because it fails an approval gate
    (validation not ok, or score below the required minimum)."""


class _StrictGovernanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRef(BaseModel):
    kind: str
    path: str
    role: SourceRole = SourceRole.PRIMARY


class Docset(BaseModel):
    docset_id: str
    title: str
    provider: str
    product: str
    source_scope: str = ""
    current_asset: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)


class AssetValidation(_StrictGovernanceModel):
    ok: bool
    score: int | None = None


class ReviewSummary(_StrictGovernanceModel):
    """Small current-pointer signal; detailed work lives in the decision sidecar."""

    state: ReviewState = ReviewState.UNREVIEWED
    decision_path: str | None = None
    open_handoff_count: int = 0


class AssetArtifacts(_StrictGovernanceModel):
    openapi: str
    provenance: str
    validation: str
    manifest: str | None = None
    integration_contract: str | None = None
    preparation: str | None = None
    review: str | None = None
    score: str | None = None
    handoff: str | None = None
    review_decision: str | None = None
    run_descriptor: str | None = None
    core_execution: str | None = None
    core_release: str | None = None
    core_contract: str | None = None
    core_decision: str | None = None
    core_evidence: str | None = None
    core_claims: str | None = None
    core_relationships: str | None = None


class AssetArtifactDigests(_StrictGovernanceModel):
    """SHA-256 bindings for the artifacts named by an asset manifest."""

    openapi: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    integration_contract: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    preparation: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    review: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    score: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    handoff: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    review_decision: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    run_descriptor: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    core_execution: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    core_release: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    core_contract: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    core_decision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    core_evidence: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    core_claims: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    core_relationships: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )


class AssetArtifactKinds(_StrictGovernanceModel):
    """Declared kind for each artifact binding (regular file or directory tree)."""

    openapi: Literal["file"]
    provenance: Literal["file"]
    validation: Literal["file"]
    manifest: Literal["file"] | None = None
    integration_contract: Literal["file"] | None = None
    preparation: Literal["file"] | None = None
    review: Literal["file"] | None = None
    score: Literal["file"] | None = None
    handoff: Literal["tree"] | None = None
    review_decision: Literal["file"] | None = None
    run_descriptor: Literal["file"] | None = None
    core_execution: Literal["file"] | None = None
    core_release: Literal["file"] | None = None
    core_contract: Literal["file"] | None = None
    core_decision: Literal["file"] | None = None
    core_evidence: Literal["file"] | None = None
    core_claims: Literal["file"] | None = None
    core_relationships: Literal["file"] | None = None


class Asset(_StrictGovernanceModel):
    schema_version: Literal["normative-asset/v1"]
    asset_id: str
    docset_id: str
    status: AssetStatus
    run_id: str
    generated_at: str
    source_hashes: list[str] = Field(default_factory=list)
    validation: AssetValidation
    artifacts: AssetArtifacts
    artifact_digests: AssetArtifactDigests
    artifact_kinds: AssetArtifactKinds
    supersedes: str | None = None
    approved_at: str | None = None
    approved_by: str | None = None
    known_gaps: list[str] = Field(default_factory=list)
    review: ReviewSummary = Field(default_factory=ReviewSummary)

    @model_validator(mode="after")
    def _require_one_digest_per_artifact(self) -> Asset:
        _validate_artifact_bindings(
            self.artifacts, self.artifact_digests, self.artifact_kinds
        )
        if self.status is AssetStatus.APPROVED and (
            self.approved_by is None or not self.approved_by.strip()
        ):
            raise ValueError("approved normative asset requires approved_by")
        return self


class CurrentPointer(_StrictGovernanceModel):
    schema_version: Literal["normative-current/v1"]
    docset_id: str
    current_asset: str
    asset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: AssetStatus
    validation: AssetValidation
    generated_at: str
    approved_at: str | None = None
    artifacts: AssetArtifacts
    artifact_digests: AssetArtifactDigests
    artifact_kinds: AssetArtifactKinds
    review: ReviewSummary = Field(default_factory=ReviewSummary)

    @model_validator(mode="after")
    def _require_one_digest_per_artifact(self) -> CurrentPointer:
        _validate_artifact_bindings(
            self.artifacts, self.artifact_digests, self.artifact_kinds
        )
        return self


def _validate_artifact_bindings(
    artifacts: AssetArtifacts,
    digests: AssetArtifactDigests,
    kinds: AssetArtifactKinds,
) -> None:
    for name in AssetArtifacts.model_fields:
        path = getattr(artifacts, name)
        digest = getattr(digests, name)
        kind = getattr(kinds, name)
        if (path is None) != (digest is None) or (path is None) != (kind is None):
            raise ValueError(f"artifact path, digest, and kind must be paired: {name}")


class FeedbackCase(_StrictGovernanceModel):
    """Immutable manifest binding one feedback case to all review inputs."""

    schema_version: Literal["feedback-case/v1"] = "feedback-case/v1"
    status: Literal["candidate"] = "candidate"
    case_id: str = Field(min_length=1, max_length=240)
    docset_id: str = Field(min_length=1, max_length=200)
    base_asset_id: str = Field(min_length=1, max_length=240)
    base_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_id: str = Field(min_length=1, max_length=200)
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessment_id: str = Field(min_length=1, max_length=240)
    assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    policy_version: str = Field(min_length=1, max_length=200)
    redaction_policy_version: str = Field(min_length=1, max_length=200)


class FeedbackReviewDecision(_StrictGovernanceModel):
    """Write-once human decision bound to every mutable feedback input."""

    schema_version: Literal["feedback-review-decision/v1"] = (
        "feedback-review-decision/v1"
    )
    case_id: str = Field(min_length=1, max_length=240)
    disposition: Literal["approved", "rejected", "needs_evidence"]
    approved_by: IdentityVersion
    decided_at: datetime
    expires_at: datetime | None = None
    base_asset_id: str
    base_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_id: str
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    redaction_policy_version: str
    policy_version: str
    assessment_id: str
    assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str | None = None
    proposal_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    requested_route: FeedbackRoute | None = None
    rationale: str | None = None

    @field_validator("decided_at", "expires_at")
    @classmethod
    def _timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("feedback review times must include a timezone")
        return value

    @model_validator(mode="after")
    def _expiry_follows_decision(self) -> FeedbackReviewDecision:
        if self.expires_at is not None and self.expires_at <= self.decided_at:
            raise ValueError("feedback review expiry must follow the decision")
        if self.disposition == "approved":
            if (
                self.expires_at is None
                or self.proposal_id is None
                or self.proposal_digest is None
            ):
                raise ValueError(
                    "approved feedback requires expiry and proposal binding"
                )
            if self.requested_route is not None:
                raise ValueError("approved feedback cannot request a corrective route")
        elif self.requested_route in {
            None,
            FeedbackRoute.CLOSED_NO_CHANGE,
            FeedbackRoute.AMENDMENT_PROPOSAL,
        }:
            raise ValueError(
                "non-approval feedback requires a corrective requested route"
            )
        return self


class EffectiveAssetArtifacts(_StrictGovernanceModel):
    effective_contract: str
    compatibility_amendment: str
    provenance: str


class EffectiveAsset(_StrictGovernanceModel):
    schema_version: Literal["effective-asset/v1"] = "effective-asset/v1"
    effective_asset_id: str
    docset_id: str
    scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target: ApplicabilityEnvelope
    status: AssetStatus
    base_asset_id: str
    base_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    compatibility_amendment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_amendment_ids: tuple[str, ...]
    supersedes: str | None = None
    supersedes_asset_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    approved_at: datetime
    valid_until: datetime | None = None
    approved_by: IdentityVersion
    open_discrepancy_count: int = Field(ge=0)
    stale_amendment_count: int = Field(ge=0)
    untested_material_claim_count: int = Field(ge=0)
    unresolved_contradiction_count: int = Field(ge=0)
    artifacts: EffectiveAssetArtifacts

    @model_validator(mode="after")
    def _bind_superseded_asset(self) -> EffectiveAsset:
        if (self.supersedes is None) != (self.supersedes_asset_digest is None):
            raise ValueError(
                "supersedes and supersedes_asset_digest must be provided together"
            )
        return self


class EffectiveCurrentPointer(_StrictGovernanceModel):
    schema_version: Literal["effective-current/v1"] = "effective-current/v1"
    current_asset: str
    effective_asset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target: ApplicabilityEnvelope
    base_asset_id: str
    effective_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    compatibility_amendment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_at: datetime
    valid_until: datetime | None = None
    open_discrepancy_count: int = Field(ge=0)
    stale_amendment_count: int = Field(ge=0)
    untested_material_claim_count: int = Field(ge=0)
    unresolved_contradiction_count: int = Field(ge=0)
    artifacts: EffectiveAssetArtifacts


class EffectiveProvenance(_StrictGovernanceModel):
    schema_version: Literal["effective-provenance/v1"] = "effective-provenance/v1"
    base_asset_id: str
    base_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    amendment_ids: tuple[str, ...]
    approval_id: str
    assessment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CatalogDocsetEntry(BaseModel):
    docset_id: str
    title: str
    provider: str
    product: str
    current_asset: str | None = None


class Catalog(BaseModel):
    version: int = 1
    docsets: list[CatalogDocsetEntry] = Field(default_factory=list)


def make_asset_id(docset_id: str, now: datetime) -> str:
    """Mint a human-readable asset id, e.g. tappay-backend-20260702-120000."""
    return f"{docset_id}-{now.strftime('%Y%m%d-%H%M%S')}"
