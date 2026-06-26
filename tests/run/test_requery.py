from __future__ import annotations

from loop_apidoc.run.requery import stages_for_requery
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def _issue(code: IssueCode, severity: Severity, location: str) -> Issue:
    return Issue(code=code, severity=severity, location=location,
                 evidence="e", suggested_fix="f")


def _report(*issues: Issue) -> ValidationReport:
    return ValidationReport(issues=list(issues))


def test_security_issue_maps_to_stage_04() -> None:
    report = _report(_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR,
                            "components.securitySchemes"))
    assert stages_for_requery(report) == {"04"}


def test_endpoint_path_issue_maps_to_05_and_06() -> None:
    report = _report(_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR,
                            "paths./users.get"))
    assert stages_for_requery(report) == {"05", "06"}


def test_endpoint_index_issue_maps_to_05_and_06() -> None:
    report = _report(_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR,
                            "endpoints[0]"))
    assert stages_for_requery(report) == {"05", "06"}


def test_mixed_security_and_endpoint() -> None:
    report = _report(
        _issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR, "components.securitySchemes"),
        _issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR, "paths./u.post"),
    )
    assert stages_for_requery(report) == {"04", "05", "06"}


def test_warning_severity_is_not_actionable() -> None:
    # summary/examples-missing are WARNING REQUIRED_INFO_MISSING -> not actionable.
    report = _report(_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING,
                            "paths./u.get"))
    assert stages_for_requery(report) == set()


def test_non_requery_codes_are_ignored() -> None:
    report = _report(
        _issue(IssueCode.SOURCE_CONFLICT, Severity.ERROR, "conflict.auth"),
        _issue(IssueCode.OPENAPI_INVALID, Severity.ERROR, "paths"),
    )
    assert stages_for_requery(report) == set()


def test_empty_report() -> None:
    assert stages_for_requery(_report()) == set()
