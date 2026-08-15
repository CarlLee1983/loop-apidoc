"""error_code 錨點:你點名的那個需求,終於接得上型別化的錯誤目錄。

這裡驗的是「每個回報的碼都是真的、都有引用」——這道檢查在輸入閘,報一個不存在
的碼會在建立 run 目錄之前就中止。「收齊了沒有」是另一回事,走 validation,驗在
`test_cli_focus_error_code_floor.py`。
"""
from __future__ import annotations

import json

from tests.focus.support import (
    INVENTORY,
    directive,
    evidence,
    response,
    setup,
    verify,
)

_ERRORS = [
    {"code": "1001", "meaning": "餘額不足", "http_status": "400",
     "applicable_to": [], "source": "manual.md lines 2-3"},
    {"code": "1002", "meaning": "簽章錯誤", "http_status": "401",
     "applicable_to": [], "source": "manual.md lines 2-3"},
]


def _setup_with_errors(tmp_path, *, directives, responses):
    sources, extraction, focus = setup(
        tmp_path, directives=directives, responses=responses)
    inventory = json.loads(json.dumps(INVENTORY))
    inventory["errors"] = _ERRORS
    (extraction / "inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
    return sources, extraction, focus


def _code_directive(**overrides) -> dict:
    return directive(id="errors", intent="collect_error_codes",
                     text="把供應商的錯誤碼收齊", **overrides)


def _anchor(code: str) -> dict:
    return {"type": "error_code", "value": code, "evidence": [evidence()]}


def _code_response(*codes: str, **overrides) -> dict:
    return response(id="errors",
                    anchors=[_anchor(code) for code in codes], **overrides)


def test_a_code_in_the_error_catalogue_resolves(tmp_path):
    sources, extraction, focus = _setup_with_errors(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("1001")])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output


def test_several_codes_are_judged_per_code(tmp_path):
    sources, extraction, focus = _setup_with_errors(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("1001", "9999", "1002")])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "9999" in res.output
    # 對得上的兩個不該被連坐報錯
    assert "'1001'" not in res.output
    assert "'1002'" not in res.output


def test_a_code_the_extraction_does_not_carry_is_rejected(tmp_path):
    sources, extraction, focus = _setup_with_errors(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("9999")])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "9999" in res.output


def test_each_reported_code_needs_its_own_evidence(tmp_path):
    sources, extraction, focus = _setup_with_errors(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("1001") | {"anchors": [
            _anchor("1001"),
            {"type": "error_code", "value": "1002", "evidence": []}]}])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2


def test_the_input_gate_never_judges_completeness(tmp_path):
    # 目錄有兩個碼,只回報一個 —— 輸入閘照樣通過。收齊與否是實質而非結構問題,
    # 由記載錯誤碼下界在 validation 判定,而下界來自來源的表格結構、不是目錄筆數。
    sources, extraction, focus = _setup_with_errors(
        tmp_path, directives=[_code_directive()],
        responses=[_code_response("1001")])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output


def test_a_field_anchor_is_refused_for_a_collect_error_codes_intent(tmp_path):
    sources, extraction, focus = _setup_with_errors(
        tmp_path, directives=[_code_directive()],
        responses=[response(id="errors", anchors=[
            {"type": "field", "value": "1001", "evidence": [evidence()]}])])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "collect_error_codes" in res.output


def test_the_gate_never_reads_the_url_corpus_entities(tmp_path):
    # 那份 entities 是 `\b[1-9]\d{3,4}\b` 的正則產物:價格、時間戳、訂單號全中,
    # 無行號無出處、不受 manifest 綁定。拿它當閘門依據會製造大量假違規。
    #
    # 掃 source_facts 而不只掃 focus:記載錯誤碼下界的實作住在那裡,而它正是最
    # 可能伸手拿這個捷徑的地方——那些 entities 看起來就像下界要的東西。
    from pathlib import Path

    import loop_apidoc.focus as focus_package
    import loop_apidoc.source_facts as source_facts_package

    packages = [
        Path(focus_package.__file__).parent,
        Path(source_facts_package.__file__).parent,
    ]
    offenders = [
        f"{package.name}/{path.name}"
        for package in packages
        for path in sorted(package.glob("*.py"))
        if "url_corpus" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
