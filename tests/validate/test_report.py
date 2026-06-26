from __future__ import annotations

from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)
from loop_apidoc.validate.report import render_markdown, write_reports


def _report() -> ValidationReport:
    return ValidationReport(issues=[
        Issue(code=IssueCode.REQUIRED_INFO_MISSING, severity=Severity.ERROR,
              location="paths./u.get", evidence="no response", suggested_fix="add response"),
        Issue(code=IssueCode.REQUIRED_INFO_MISSING, severity=Severity.WARNING,
              location="operational", evidence="no rate limit", suggested_fix="add ops"),
    ])


def test_render_markdown_reports_fail_and_counts():
    md = render_markdown(_report())
    assert "FAIL" in md
    assert "REQUIRED_INFO_MISSING" in md
    assert "paths./u.get" in md
    assert "add response" in md


def test_render_markdown_pass_for_empty():
    assert "PASS" in render_markdown(ValidationReport())


def test_write_reports_emits_both_files(tmp_path):
    out = tmp_path / "validation"
    write_reports(_report(), out)
    loaded = ValidationReport.model_validate_json((out / "report.json").read_text())
    assert loaded == _report()
    assert "FAIL" in (out / "report.md").read_text()
