from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, PositiveInt


class RiskVerdict(str, Enum):
    PASS = "pass"
    REJECT = "reject"


class RiskSeverity(str, Enum):
    BLOCKER = "blocker"
    WARNING = "warning"


class RiskCoverageStatus(str, Enum):
    SCANNED = "scanned"
    UNSCANNABLE = "unscannable"
    SKIPPED = "skipped"


class SourceRiskFinding(BaseModel):
    rule_id: str
    severity: RiskSeverity
    source_ref: str
    locator: str


class SourceRiskCoverage(BaseModel):
    source_ref: str
    sha256: str
    status: RiskCoverageStatus
    reason: str | None = None


class SourceRiskReport(BaseModel):
    schema_version: str
    ruleset_version: str
    max_bytes: PositiveInt
    manifest_sha256: str
    source_binding_digest: str
    verdict: RiskVerdict
    findings: list[SourceRiskFinding] = Field(default_factory=list)
    coverage: list[SourceRiskCoverage] = Field(default_factory=list)

    @property
    def blocker_count(self) -> int:
        return sum(
            finding.severity is RiskSeverity.BLOCKER for finding in self.findings
        )
