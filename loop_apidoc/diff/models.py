from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DiffImpact(str, Enum):
    BREAKING = "breaking"
    ADDITIVE = "additive"
    CHANGED = "changed"
    SOURCE_ONLY = "source_only"


class DiffFinding(BaseModel):
    impact: DiffImpact
    area: str
    location: str
    summary: str
    before: Any | None = None
    after: Any | None = None


class DiffReport(BaseModel):
    base_run: str
    head_run: str
    summary: dict[str, int]
    findings: list[DiffFinding] = Field(default_factory=list)
