from __future__ import annotations

from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    RootCause,
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


def test_render_markdown_lists_root_causes_before_issues():
    report = ValidationReport(
        issues=[
            Issue(code=IssueCode.SOURCE_UNVERIFIED, severity=Severity.ERROR,
                  location="integration.crypto.0", evidence="缺 supported 依據",
                  suggested_fix="確認來源", target_file="integration.json"),
            Issue(code=IssueCode.SOURCE_UNVERIFIED, severity=Severity.ERROR,
                  location="integration.crypto.1", evidence="缺 supported 依據",
                  suggested_fix="確認來源", target_file="integration.json"),
        ],
        root_causes=[
            RootCause(code=IssueCode.SOURCE_UNVERIFIED, severity=Severity.ERROR,
                      target_file="integration.json", fix_once="統一改寫 source 格式",
                      affected_locations=["integration.crypto.0",
                                          "integration.crypto.1"]),
        ],
    )

    md = render_markdown(report)

    assert md.index("## 根因（優先處理）") < md.index("## 逐筆問題")
    assert "統一改寫 source 格式" in md
    assert "影響 2 處" in md


def test_render_markdown_omits_root_cause_section_when_empty():
    report = ValidationReport(issues=[])

    assert "## 根因" not in render_markdown(report)
