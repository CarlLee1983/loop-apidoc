from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IssueCode(str, Enum):
    SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"
    REQUIRED_INFO_MISSING = "REQUIRED_INFO_MISSING"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    OPENAPI_INVALID = "OPENAPI_INVALID"
    OUTPUT_MISMATCH = "OUTPUT_MISMATCH"
    UNSUPPORTED_ASSERTION = "UNSUPPORTED_ASSERTION"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class Issue(BaseModel):
    code: IssueCode
    severity: Severity
    location: str
    evidence: str
    suggested_fix: str
    auto_fixable: bool = False


class ValidationReport(BaseModel):
    issues: list[Issue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity is Severity.ERROR for i in self.issues)

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]
