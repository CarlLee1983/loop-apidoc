from __future__ import annotations

from enum import Enum
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loop_apidoc.source_risk.models import SourceRiskReport


class QualityVerdict(str, Enum):
    PASS = "pass"
    REJECT = "reject"


class FindingSeverity(str, Enum):
    BLOCKER = "blocker"
    WARNING = "warning"


class QualityObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    locator: str
    category: str
    evidence: str
    severity: FindingSeverity
    affected_scope: list[str] = Field(default_factory=list)
    required_supplement: str
    acceptance_criteria: str
    required_source_refs: list[str] = Field(default_factory=list)

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

    @field_validator("required_source_refs")
    @classmethod
    def _absolute_http_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            parts = urlsplit(value)
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                raise ValueError("required_source_refs must contain absolute http(s) URLs")
            if parts.username or parts.password:
                raise ValueError("required_source_refs must not contain credentials")
        return values


class QualityFinding(QualityObservation):
    id: str

    @property
    def is_blocker(self) -> bool:
        return self.severity is FindingSeverity.BLOCKER


class SourceQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: QualityVerdict
    source_set: str
    base_source_set: str | None = None
    findings: list[QualityFinding] = Field(default_factory=list)
    required_source_refs: list[str] = Field(default_factory=list)
    source_risk: SourceRiskReport | None = None

    @model_validator(mode="after")
    def _require_consistent_derived_fields(self) -> Self:
        blocker_findings = [
            finding for finding in self.findings if finding.is_blocker
        ]
        expected_verdict = (
            QualityVerdict.REJECT if blocker_findings else QualityVerdict.PASS
        )
        if self.verdict is not expected_verdict:
            raise ValueError(
                "verdict must be reject exactly when blocker findings are present"
            )

        expected_required_source_refs = list(
            dict.fromkeys(
                reference
                for finding in blocker_findings
                for reference in finding.required_source_refs
            )
        )
        if self.required_source_refs != expected_required_source_refs:
            raise ValueError(
                "required_source_refs must equal the ordered, de-duplicated "
                "union from blocker findings"
            )
        return self

    @property
    def blocker_count(self) -> int:
        return sum(finding.is_blocker for finding in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(
            finding.severity is FindingSeverity.WARNING for finding in self.findings
        )


class SourceDiffEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    kind: Literal["added", "removed", "changed"]
    summary: str


class SourceDiffReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[SourceDiffEntry] = Field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        counts = {"added": 0, "removed": 0, "changed": 0}
        for entry in self.entries:
            counts[entry.kind] = counts.get(entry.kind, 0) + 1
        return counts
