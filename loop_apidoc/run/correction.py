from __future__ import annotations

from loop_apidoc.run.models import CorrectionCategory
from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)

_CATEGORY: dict[IssueCode, CorrectionCategory] = {
    IssueCode.OPENAPI_INVALID: CorrectionCategory.AUTO_FIX,
    IssueCode.OUTPUT_MISMATCH: CorrectionCategory.AUTO_FIX,
    IssueCode.REQUIRED_INFO_MISSING: CorrectionCategory.RE_QUERY,
    IssueCode.SOURCE_UNVERIFIED: CorrectionCategory.UNFIXABLE,
    IssueCode.SOURCE_CONFLICT: CorrectionCategory.UNFIXABLE,
    IssueCode.UNSUPPORTED_ASSERTION: CorrectionCategory.UNFIXABLE,
}


def classify_issue(issue: Issue) -> CorrectionCategory:
    """Map a validation issue to a correction strategy (spec §10).

    Fail-closed: anything not explicitly fixable is UNFIXABLE so the loop
    never speculates over source-missing or conflicting content.
    """
    return _CATEGORY.get(issue.code, CorrectionCategory.UNFIXABLE)


def annotate_fixability(report: ValidationReport) -> ValidationReport:
    """Return a new report with auto_fixable set per classification."""
    issues = [
        issue.model_copy(
            update={"auto_fixable": classify_issue(issue) is CorrectionCategory.AUTO_FIX}
        )
        for issue in report.issues
    ]
    return ValidationReport(issues=issues)


def actionable_codes(report: ValidationReport) -> list[Issue]:
    """Error-severity issues the loop can act on (auto-fix or re-query)."""
    return [
        issue
        for issue in report.issues
        if issue.severity is Severity.ERROR
        and classify_issue(issue)
        in (CorrectionCategory.AUTO_FIX, CorrectionCategory.RE_QUERY)
    ]
