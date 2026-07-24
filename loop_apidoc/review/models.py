from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from loop_apidoc.diff.models import DiffReport
from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.score.models import ScoreReport
from loop_apidoc.validate.models import ValidationReport


class ReviewInputError(ValueError):
    """The requested run, candidate, docset, or Foundry evidence is invalid."""


class ReviewConflictError(ValueError):
    """A decision no longer binds to the current candidate/base evidence."""


class ReviewStateError(ValueError):
    """A review draft has invalid subjects or cannot be promoted."""


class ReviewMode(str, Enum):
    BASELINE = "baseline"
    UPDATE = "update"


class ReviewSubjectKind(str, Enum):
    DIFF = "diff"
    VALIDATION = "validation"
    MANUAL = "manual"


class ReviewEvidence(BaseModel):
    """A Core evidence relationship attached to a review subject."""

    claim_identity: str
    claim_path: str
    relationship: Literal[
        "explicit_support", "derived_support", "contradicts", "insufficient"
    ]
    source_id: str
    source_locator: str
    fragment_locator: dict[str, Any]
    fragment_digest: str
    normalized_excerpt: str | None = None


class ReviewDisposition(str, Enum):
    ACCEPT = "accept"
    NEEDS_EVIDENCE = "needs_evidence"
    REJECT = "reject"
    SKIP = "skip"


class RequestedAction(str, Enum):
    NONE = "none"
    RECHECK_SOURCE = "recheck_source"
    CORRECT_EXTRACTION = "correct_extraction"
    COMPARE_CONTRACT = "compare_contract"
    CLARIFY_PROVIDER = "clarify_provider"


class ReviewRequest(BaseModel):
    docset_id: str
    run_dir: Path


class ReviewKey(BaseModel):
    docset_id: str
    candidate_run_id: str


class ReviewBinding(BaseModel):
    schema_version: Literal[1] = 1
    docset_id: str
    candidate_run_id: str
    candidate_artifact_digests: dict[str, str]
    base_asset_id: str | None = None
    base_artifact_digests: dict[str, str] = Field(default_factory=dict)
    diff_digest: str | None = None


class ReviewSubject(BaseModel):
    id: str
    kind: ReviewSubjectKind
    location: str
    summary: str
    evidence: list[ReviewEvidence] = Field(default_factory=list)


class ReviewItem(BaseModel):
    subject_id: str
    subject_kind: ReviewSubjectKind
    disposition: ReviewDisposition
    note: str = ""
    requested_action: RequestedAction = RequestedAction.NONE


class HandoffTask(BaseModel):
    task_id: str
    status: Literal["open", "done"] = "open"
    instruction: str
    subject_ids: list[str] = Field(default_factory=list)


class ReviewWaiver(BaseModel):
    """A human-approved, expiring review exception; never evidence support."""

    subject_id: str
    claim_identity: str
    reason: str
    approved_by: str
    expires_at: datetime
    scope: list[str] = Field(default_factory=list)


class ReviewDraft(BaseModel):
    binding: ReviewBinding
    items: list[ReviewItem] = Field(default_factory=list)
    handoff: list[HandoffTask] = Field(default_factory=list)
    waivers: list[ReviewWaiver] = Field(default_factory=list)
    note: str = ""


class ReviewDecision(ReviewDraft):
    schema_version: Literal[1] = 1
    binding: ReviewBinding
    saved_at: datetime


class ReviewSnapshot(BaseModel):
    key: ReviewKey
    binding: ReviewBinding
    mode: ReviewMode
    validation: ValidationReport
    provenance: ProvenanceDocument
    score: ScoreReport | None = None
    diff: DiffReport | None = None
    subjects: list[ReviewSubject] = Field(default_factory=list)
    decision: ReviewDecision | None = None


class ApprovalResult(BaseModel):
    asset_id: str
    current_asset: str
    needs_follow_up: bool
    open_handoff_count: int
