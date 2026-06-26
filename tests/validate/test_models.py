from __future__ import annotations

from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)


def _issue(severity: Severity) -> Issue:
    return Issue(
        code=IssueCode.REQUIRED_INFO_MISSING,
        severity=severity,
        location="paths./users.get",
        evidence="no response defined",
        suggested_fix="add a response from source",
    )


def test_issue_code_values_match_spec():
    assert IssueCode.SOURCE_UNVERIFIED.value == "SOURCE_UNVERIFIED"
    assert IssueCode.UNSUPPORTED_ASSERTION.value == "UNSUPPORTED_ASSERTION"
    assert {c.value for c in IssueCode} == {
        "SOURCE_UNVERIFIED",
        "REQUIRED_INFO_MISSING",
        "SOURCE_CONFLICT",
        "OPENAPI_INVALID",
        "OUTPUT_MISMATCH",
        "UNSUPPORTED_ASSERTION",
    }


def test_issue_auto_fixable_defaults_false():
    assert _issue(Severity.WARNING).auto_fixable is False


def test_report_ok_when_no_errors():
    report = ValidationReport(issues=[_issue(Severity.WARNING)])
    assert report.ok is True
    assert report.warnings() == report.issues
    assert report.errors() == []


def test_report_not_ok_with_any_error():
    report = ValidationReport(issues=[_issue(Severity.WARNING), _issue(Severity.ERROR)])
    assert report.ok is False
    assert len(report.errors()) == 1


def test_empty_report_is_ok():
    assert ValidationReport().ok is True
