"""語意完整性閘門對哪些來源根本沒作用 —— 從靜默變成報告裡的一筆事實。

零事實與零匹配是兩種不同的失能:前者沒有東西可比對(換前處理路徑),後者比對不到
任何端點(補 extraction)。措辭必須分開,否則 operator 會對壓平的 HTML 反覆重讀。

一律打 `validate_outputs` 這個 seam:投影由呼叫端算好傳入,validate 不認識來源事實
的內部結構,測試也就不綁死新模組的簽章。
"""
from __future__ import annotations

from tests.validate.support import report as _report, unscanned as _unscanned
from loop_apidoc.validate.fact_coverage import FactCoverage


def test_a_source_with_no_facts_is_reported_with_the_preprocess_remedy():
    report = _report({"dump.md": FactCoverage(facts=0, matched=0)})
    issue = _unscanned(report)[0]

    assert issue.location == "dump.md"
    assert "normalize-html-snapshot" in issue.suggested_fix
    assert issue.severity.value == "warning"


def test_a_source_whose_facts_match_nothing_points_at_the_extraction():
    report = _report({"api.md": FactCoverage(facts=4, matched=0)})
    issue = _unscanned(report)[0]

    assert issue.location == "api.md"
    assert "4" in issue.evidence
    assert "normalize-html-snapshot" not in issue.suggested_fix
    assert "extraction" in issue.suggested_fix


def test_the_two_shapes_do_not_share_wording():
    zero_facts = _unscanned(_report({"a.md": FactCoverage(facts=0, matched=0)}))[0]
    zero_match = _unscanned(_report({"a.md": FactCoverage(facts=3, matched=0)}))[0]

    assert zero_facts.evidence != zero_match.evidence
    assert zero_facts.suggested_fix != zero_match.suggested_fix


def test_a_source_with_at_least_one_match_is_not_reported():
    assert _unscanned(_report({"api.md": FactCoverage(facts=3, matched=1)})) == []


def test_an_absent_projection_reports_nothing():
    """未傳投影 ＝ 這項未評估,維持 `validate_run_dir` 的既有行為。"""
    assert _unscanned(_report(None)) == []


def test_the_warning_never_fails_the_report():
    report = _report({
        "dump.md": FactCoverage(facts=0, matched=0),
        "api.md": FactCoverage(facts=9, matched=0),
    })

    assert len(_unscanned(report)) == 2
    assert report.ok is True
