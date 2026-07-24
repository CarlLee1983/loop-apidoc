from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from loop_apidoc.freshness.models import SourceKind


class GovernanceStatus(str, Enum):
    NO_ACTION = "no_action"
    REVIEW_REQUIRED = "review_required"
    ATTENTION_REQUIRED = "attention_required"


class GovernanceTriggerKind(str, Enum):
    SOURCE_CHANGED = "source_changed"
    FRESHNESS_INCONCLUSIVE = "freshness_inconclusive"


class GovernanceTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    kind: GovernanceTriggerKind
    reason: str | None = None
    run_dir: str | None = None


class GovernanceSnapshotSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: SourceKind
    sha256: str
    path: str


class GovernanceSnapshotItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    sources: list[GovernanceSnapshotSource] = Field(default_factory=list)


class GovernanceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    source_count: int
    items: list[GovernanceSnapshotItem] = Field(default_factory=list)


class GovernanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GovernanceStatus
    scanned_count: int
    triggers: list[GovernanceTrigger] = Field(default_factory=list)
    snapshot: GovernanceSnapshot | None = None


class GovernanceReviewSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sha256: str
    path: str


class GovernanceReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    kind: GovernanceTriggerKind
    reason: str | None = None
    run_dir: str | None = None
    sources: list[GovernanceReviewSource] = Field(default_factory=list)
    required_steps: list[str]


class GovernanceReviewPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    items: list[GovernanceReviewItem] = Field(default_factory=list)
