from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PreparationStatus(str, Enum):
    READY = "ready"
    NEEDS_ATTENTION = "needs_attention"
    BLOCKED = "blocked"


class PreparationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class PreparationFinding(BaseModel):
    severity: PreparationSeverity
    summary: str
    evidence: str = ""
    suggested_action: str
    target_file: str | None = None
    field_path: str | None = None
    requery_scope: str | None = None


class PreparationPhase(BaseModel):
    id: str
    label: str
    status: PreparationStatus
    metrics: dict[str, Any] = Field(default_factory=dict)
    findings: list[PreparationFinding] = Field(default_factory=list)


class PreparationReport(BaseModel):
    status: PreparationStatus
    summary: dict[str, int]
    phases: list[PreparationPhase] = Field(default_factory=list)
