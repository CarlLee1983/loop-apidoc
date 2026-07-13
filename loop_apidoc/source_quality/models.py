from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class QualityVerdict(str, Enum):
    PASS = "pass"
    REJECT = "reject"


class FindingSeverity(str, Enum):
    BLOCKER = "blocker"
    WARNING = "warning"


class QualityObservation(BaseModel):
    source: str
    locator: str
    category: str
    evidence: str
    severity: FindingSeverity
    affected_scope: list[str] = Field(default_factory=list)
    required_supplement: str
    acceptance_criteria: str

    @field_validator(
        "source",
        "locator",
        "category",
        "evidence",
        "required_supplement",
        "acceptance_criteria",
    )
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class QualityFinding(QualityObservation):
    id: str

    @property
    def is_blocker(self) -> bool:
        return self.severity is FindingSeverity.BLOCKER


class SourceQualityReport(BaseModel):
    verdict: QualityVerdict
    source_set: str
    base_source_set: str | None = None
    findings: list[QualityFinding] = Field(default_factory=list)

    @property
    def blocker_count(self) -> int:
        return sum(finding.is_blocker for finding in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(
            finding.severity is FindingSeverity.WARNING for finding in self.findings
        )


class SourceDiffEntry(BaseModel):
    path: str
    kind: str
    summary: str


class SourceDiffReport(BaseModel):
    entries: list[SourceDiffEntry] = Field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        counts = {"added": 0, "removed": 0, "changed": 0}
        for entry in self.entries:
            counts[entry.kind] = counts.get(entry.kind, 0) + 1
        return counts
