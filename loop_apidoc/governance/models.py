from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


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


class GovernanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GovernanceStatus
    scanned_count: int
    triggers: list[GovernanceTrigger] = Field(default_factory=list)
