from __future__ import annotations

from loop_apidoc.run.correction import (
    actionable_codes,
    annotate_fixability,
    classify_issue,
)
from loop_apidoc.run.models import CorrectionCategory
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def _issue(code: IssueCode, severity: Severity = Severity.ERROR) -> Issue:
    return Issue(
        code=code,
        severity=severity,
        location="x",
        evidence="e",
        suggested_fix="f",
    )


def test_classify_each_code() -> None:
    assert classify_issue(_issue(IssueCode.OPENAPI_INVALID)) is CorrectionCategory.AUTO_FIX
    # OUTPUT_MISMATCH is a generator-invariant violation (markdown↔OpenAPI drift,
    # missing required section) or a disk/IO error from validate_run_dir — never a
    # plan-repairable defect. Regeneration is deterministic, so it would recur.
    # Fail-closed as UNFIXABLE rather than burn correction rounds.
    assert classify_issue(_issue(IssueCode.OUTPUT_MISMATCH)) is CorrectionCategory.UNFIXABLE
    assert classify_issue(_issue(IssueCode.REQUIRED_INFO_MISSING)) is CorrectionCategory.RE_QUERY
    assert classify_issue(_issue(IssueCode.SOURCE_UNVERIFIED)) is CorrectionCategory.UNFIXABLE
    assert classify_issue(_issue(IssueCode.SOURCE_CONFLICT)) is CorrectionCategory.UNFIXABLE
    assert classify_issue(_issue(IssueCode.UNSUPPORTED_ASSERTION)) is CorrectionCategory.UNFIXABLE


def test_annotate_fixability_does_not_mutate_input() -> None:
    report = ValidationReport(issues=[_issue(IssueCode.OPENAPI_INVALID)])
    annotated = annotate_fixability(report)
    assert annotated.issues[0].auto_fixable is True
    assert report.issues[0].auto_fixable is False  # unchanged


def test_actionable_codes_filters_unfixable_and_warnings() -> None:
    report = ValidationReport(
        issues=[
            _issue(IssueCode.REQUIRED_INFO_MISSING),
            _issue(IssueCode.SOURCE_CONFLICT),
            _issue(IssueCode.OPENAPI_INVALID, severity=Severity.WARNING),
        ]
    )
    codes = [i.code for i in actionable_codes(report)]
    assert codes == [IssueCode.REQUIRED_INFO_MISSING]
