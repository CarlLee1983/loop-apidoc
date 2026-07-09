from __future__ import annotations

from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport
from loop_apidoc.validate.root_cause import derive_root_causes


def _issue(location: str, *, code=IssueCode.SOURCE_UNVERIFIED,
           severity=Severity.ERROR, target_file="integration.json",
           fix="確認來源以取得 supported 引用") -> Issue:
    return Issue(code=code, severity=severity, location=location,
                 evidence="契約條目僅有 unverified 來源", suggested_fix=fix,
                 target_file=target_file)


def test_same_code_and_target_file_converge_into_one_root_cause():
    issues = [_issue("integration.crypto.0"), _issue("integration.crypto.1")]

    causes = derive_root_causes(issues)

    assert len(causes) == 1
    assert causes[0].code is IssueCode.SOURCE_UNVERIFIED
    assert causes[0].target_file == "integration.json"
    assert causes[0].affected_locations == [
        "integration.crypto.0", "integration.crypto.1"]


def test_single_issue_is_not_a_root_cause():
    """一筆就不叫根因 —— 逐筆 issue 已經夠精確。"""
    assert derive_root_causes([_issue("integration.crypto.0")]) == []


def test_issue_without_target_file_is_not_grouped():
    """沒有可靠的一次修完目標,硬分組只會製造假的根因。"""
    issues = [_issue("unverified.06", target_file=None),
              _issue("unverified.07", target_file=None)]

    assert derive_root_causes(issues) == []


def test_different_severity_does_not_group():
    issues = [_issue("a", severity=Severity.ERROR),
              _issue("b", severity=Severity.WARNING)]

    assert derive_root_causes(issues) == []


def test_different_target_file_does_not_group():
    issues = [_issue("a", target_file="integration.json"),
              _issue("b", target_file="inventory.json")]

    assert derive_root_causes(issues) == []


def test_source_unverified_gets_a_one_shot_fix_text():
    """有實證的 code 用對照表的一次修完動作,而非逐筆重複的「確認來源」。"""
    causes = derive_root_causes([_issue("a"), _issue("b")])

    assert "一次" in causes[0].fix_once or "統一" in causes[0].fix_once
    assert causes[0].fix_once != "確認來源以取得 supported 引用"


def test_uncatalogued_code_falls_back_to_shared_suggested_fix():
    issues = [_issue("a", code=IssueCode.OUTPUT_MISMATCH, fix="修正參照後重新產生"),
              _issue("b", code=IssueCode.OUTPUT_MISMATCH, fix="修正參照後重新產生")]

    causes = derive_root_causes(issues)

    assert causes[0].fix_once == "修正參照後重新產生"


def test_root_causes_do_not_change_report_ok():
    """不變式:root_causes 是純加法,絕不影響 severity 閘。"""
    warnings = [_issue("a", severity=Severity.WARNING),
                _issue("b", severity=Severity.WARNING)]
    report = ValidationReport(issues=warnings,
                              root_causes=derive_root_causes(warnings))

    assert report.root_causes  # 有分組
    assert report.ok is True   # 但仍然 PASS


def test_report_defaults_to_no_root_causes():
    assert ValidationReport(issues=[]).root_causes == []
