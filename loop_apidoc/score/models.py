from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import ValidationReport


class ScoreStatus(str, Enum):
    PASS = "pass"
    NEEDS_ATTENTION = "needs_attention"
    FAIL = "fail"


class ScoreProfile(str, Enum):
    CI = "ci"
    REVIEW = "review"


class ScoreCategory(str, Enum):
    OPENAPI_VALIDITY = "openapi_validity"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    SOURCE_GROUNDING = "source_grounding"
    REVIEWABILITY = "reviewability"


CATEGORY_WEIGHTS: dict[str, int] = {
    ScoreCategory.OPENAPI_VALIDITY.value: 20,
    ScoreCategory.COMPLETENESS.value: 30,
    ScoreCategory.CONSISTENCY.value: 20,
    ScoreCategory.SOURCE_GROUNDING.value: 20,
    ScoreCategory.REVIEWABILITY.value: 10,
}

DEFAULT_MIN_SCORES: dict[ScoreProfile, int] = {
    ScoreProfile.CI: 85,
    ScoreProfile.REVIEW: 70,
}


class ScoreInputError(ValueError):
    """The run directory cannot be scored because an artifact is missing or invalid."""


class ScoreFinding(BaseModel):
    code: str
    severity: str
    location: str
    evidence: str
    suggested_fix: str
    category: ScoreCategory
    blocking: bool
    score_impact: int = Field(ge=0, le=100)


class ScoreReport(BaseModel):
    status: ScoreStatus
    score: int = Field(ge=0, le=100)
    profile: ScoreProfile
    min_score: int = Field(ge=0, le=100)
    category_scores: dict[str, int]
    blocking_findings: list[ScoreFinding] = Field(default_factory=list)
    findings: list[ScoreFinding] = Field(default_factory=list)


@dataclass(frozen=True)
class ScoreInputs:
    run_dir: Path
    openapi: dict
    validation: ValidationReport
    provenance: ProvenanceDocument
    manifest: Manifest
    plan: dict | None = None
    review_html_exists: bool = False
    validation_markdown_exists: bool = False


def resolved_min_score(profile: ScoreProfile, explicit_min_score: int | None) -> int:
    return DEFAULT_MIN_SCORES[profile] if explicit_min_score is None else explicit_min_score
