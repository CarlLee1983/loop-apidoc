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


def test_an_unclosed_fence_is_named_as_the_cause():
    """成因已知時就不要叫 operator 從三種可能裡自己猜。

    圍籬未閉合是唯一一種掃描器自己知道確切成因的零事實:從那一行起整份文件都被
    當成在圍籬內。訊息點名行號,operator 打開來源就看得到問題。
    """
    report = _report({"api.md": FactCoverage(facts=0, matched=0, unclosed_fence_line=42)})
    issue = _unscanned(report)[0]

    assert "42" in issue.evidence
    assert "42" in issue.suggested_fix


def test_a_zero_fact_source_without_a_known_cause_still_enumerates_them():
    issue = _unscanned(_report({"dump.md": FactCoverage(facts=0, matched=0)}))[0]

    assert "42" not in issue.evidence
    assert "normalize-html-snapshot" in issue.suggested_fix


def test_a_partially_unread_source_is_reported_even_though_facts_matched():
    """讀到一半才失效才是最危險的:閘門判了前半,報告乾淨,後半根本沒被讀過。

    以事實數／匹配數為唯一判準時這種來源完全不會浮現——比全篇未讀更危險,
    因為閘門看起來運作正常。
    """
    coverage = {"api.md": FactCoverage(facts=3, matched=2, unclosed_fence_line=7)}
    issue = _unscanned(_report(coverage))[0]

    assert "7" in issue.evidence
    assert "extraction" not in issue.suggested_fix


def test_the_known_cause_wins_over_the_zero_match_wording():
    """成因已知時不得再叫人去查 extraction 漏了什麼——那個缺陷並不存在。"""
    coverage = {"api.md": FactCoverage(facts=4, matched=0, unclosed_fence_line=9)}
    issue = _unscanned(_report(coverage))[0]

    assert "9" in issue.evidence
    assert "檢查 extraction" not in issue.suggested_fix
