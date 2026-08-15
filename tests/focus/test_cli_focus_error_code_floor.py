"""記載錯誤碼下界:窮盡型指令終於有了可比的底線。

在此之前,滿足 `collect_error_codes` 最便宜的方式是回報一個碼——那個答案在輸出裡
與真正掃過一遍完全無法區分。下界從來源自己攤出來的錯誤碼表格取得:報得比它少就
點名漏掉哪幾個,報得比它多仍然通過(下界是底線,不是等式),來源沒有可辨識的表格
就不下判斷。

短少走 validation 而不是輸入閘:回應本身格式正確、碼都是真的也都有引用,壞的是
實質而非結構,而人要判斷「來源真的只有這些,還是查得不夠」時需要產物留在手上。
"""
from __future__ import annotations

import json

from tests.focus.support import (
    INVENTORY,
    assemble,
    directive,
    error_codes,
    evidence,
    issues_with_code,
    response,
    setup,
)

_ERRORS = [
    {"code": "1001", "meaning": "餘額不足", "http_status": "400",
     "applicable_to": [], "source": "manual.md lines 2-3"},
    {"code": "1002", "meaning": "簽章錯誤", "http_status": "401",
     "applicable_to": [], "source": "manual.md lines 2-3"},
]

_ERROR_TABLE = """
## 錯誤碼

| 錯誤碼 | 說明 |
| --- | --- |
| 1001 | 餘額不足 |
| 1002 | 簽章錯誤 |
"""


def _setup(tmp_path, *, directives, responses, table: str = _ERROR_TABLE):
    sources, extraction, focus = setup(
        tmp_path, directives=directives, responses=responses)
    inventory = json.loads(json.dumps(INVENTORY))
    inventory["errors"] = _ERRORS
    (extraction / "inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
    # 附加在既有內文之後,前面幾行的行號不變,錨點證據照樣對得上。
    with (sources / "manual.md").open("a", encoding="utf-8") as handle:
        handle.write(table)
    return sources, extraction, focus


def _code_directive(**overrides) -> dict:
    return directive(id="errors", intent="collect_error_codes",
                     text="把供應商的錯誤碼收齊", **overrides)


def _code_response(*codes: str, **overrides) -> dict:
    return response(
        id="errors",
        anchors=[{"type": "error_code", "value": code, "evidence": [evidence()]}
                 for code in codes],
        **overrides)


def _payload(res) -> dict:
    return json.loads(res.stdout)


def test_an_answer_covering_the_floor_passes(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("1001", "1002")])

    payload = _payload(assemble(tmp_path, sources, extraction, focus, "--json"))

    assert issues_with_code(payload, "FOCUS_INCOMPLETE") == []


def test_an_answer_short_of_the_floor_names_the_codes_left_out(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("1001")])

    payload = _payload(assemble(tmp_path, sources, extraction, focus, "--json"))
    issue = issues_with_code(payload, "FOCUS_INCOMPLETE")[0]

    assert "1002" in issue["evidence"]
    assert "1001" not in issue["evidence"]
    assert "errors" in issue["location"]


def test_the_issue_cites_where_each_omitted_code_is_documented(tmp_path):
    """operator 打開報告就是要去看那幾行,所以出處是罰單的一部分。"""
    sources, extraction, focus = _setup(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("1001")])

    payload = _payload(assemble(tmp_path, sources, extraction, focus, "--json"))
    issue = issues_with_code(payload, "FOCUS_INCOMPLETE")[0]

    assert "manual.md" in issue["evidence"]
    assert "manual.md" in issue["requery_scope"]


def test_severity_follows_the_directive_kind_for_an_expectation(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_code_directive(kind="expectation")],
        responses=[_code_response("1001")])

    payload = _payload(assemble(tmp_path, sources, extraction, focus, "--json"))

    assert issues_with_code(payload, "FOCUS_INCOMPLETE")[0]["severity"] == "error"
    assert "FOCUS_INCOMPLETE" in error_codes(payload)


def test_severity_follows_the_directive_kind_for_a_coverage_directive(tmp_path):
    """`kind` 是 severity 的唯一決定者——coverage 的短少不得變成 error。"""
    sources, extraction, focus = _setup(
        tmp_path, directives=[_code_directive(kind="coverage")],
        responses=[_code_response("1001")])

    payload = _payload(assemble(tmp_path, sources, extraction, focus, "--json"))

    assert issues_with_code(payload, "FOCUS_INCOMPLETE")[0]["severity"] == "warning"
    assert "FOCUS_INCOMPLETE" not in error_codes(payload)


def test_a_shortfall_still_produces_the_run_artifacts(tmp_path):
    sources, extraction, focus = _setup(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("1001")])

    payload = _payload(assemble(tmp_path, sources, extraction, focus, "--json"))
    run_dir = tmp_path / "runs" / payload["run_id"]

    assert (run_dir / "openapi.yaml").exists()


def test_a_source_with_no_error_code_table_produces_no_judgement(tmp_path):
    """下界不存在,不是零——沒有結構就不判斷,與今天的行為相同。"""
    sources, extraction, focus = _setup(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("1001")], table="")

    payload = _payload(assemble(tmp_path, sources, extraction, focus, "--json"))

    assert issues_with_code(payload, "FOCUS_INCOMPLETE") == []


def test_a_not_found_answer_is_not_judged_against_the_floor(tmp_path):
    """not_found 有它自己的結局(FOCUS_UNMET),不該再被短少連坐一次。"""
    sources, extraction, focus = _setup(
        tmp_path, directives=[_code_directive()],
        responses=[{"id": "errors", "outcome": "not_found",
                    "reported_by": "inventory",
                    "searched_sources": ["manual.md"]}])

    payload = _payload(assemble(tmp_path, sources, extraction, focus, "--json"))

    assert issues_with_code(payload, "FOCUS_INCOMPLETE") == []
    assert issues_with_code(payload, "FOCUS_UNMET") != []


# 短少不進計分,驗在 tests/score/test_evaluate.py 的 _UNSCORED_CODES ——
# 那裡已經有一道檢查逼每個新 code 二選一,不必在這個 seam 再造一個。


def test_an_answer_beyond_the_floor_still_passes(tmp_path):
    """下界是底線不是等式:來源可能在散文裡還寫了掃描器看不見的碼。"""
    sources, extraction, focus = _setup(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("1001", "1002")],
        table=_ERROR_TABLE.replace("| 1002 | 簽章錯誤 |\n", ""))

    payload = _payload(assemble(tmp_path, sources, extraction, focus, "--json"))

    assert issues_with_code(payload, "FOCUS_INCOMPLETE") == []


def test_a_case_difference_is_not_a_shortfall(tmp_path):
    """來源寫 `E1001`、答案寫 `e1001` —— 那是同一個碼,不是漏掉一個。

    #64 只收數字碼時不會發生;#65 收下 `E1001` / `INVALID_REQUEST` 之後,
    比對就必須不分大小寫,否則會對一個確實被回報的碼開罰單。假違規比漏判貴。
    """
    sources, extraction, focus = _setup(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("e1001")],
        table="""
## 錯誤碼

| 錯誤碼 | 說明 |
| --- | --- |
| E1001 | 餘額不足 |
""")
    inventory = json.loads((extraction / "inventory.json").read_text("utf-8"))
    inventory["errors"] = [{"code": "e1001", "meaning": "餘額不足",
                            "http_status": "400", "applicable_to": [],
                            "source": "manual.md lines 2-3"}]
    (extraction / "inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8")

    payload = _payload(assemble(tmp_path, sources, extraction, focus, "--json"))

    assert issues_with_code(payload, "FOCUS_INCOMPLETE") == []
