"""field 錨點:把注意力下在某個欄位上,而不是整個端點。

解析必須沿 `schema_ref` 走進 inventory 的共用 schema —— 把 body 抽成共用型別是
正確擷取,不解析它就會把正確的答案判成找不到。
"""
from __future__ import annotations

from tests.focus.support import (
    directive,
    evidence,
    response,
    setup,
    verify,
)

_INVENTORY_WITH_SCHEMA = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "manual.md lines 1-1"}],
    "security_schemes": [], "errors": [], "operational": [],
    "schemas": [
        {"name": "SettleBody",
         "fields": [{"name": "merchant_trade_no", "type": "str",
                     "required": True, "description": None},
                    {"name": "amount", "type": "int", "required": True,
                     "description": None}],
         "enums": [], "constraints": None, "source": "manual.md lines 2-3"},
    ],
    "endpoints": [
        {"method": "GET", "path": "/ping", "summary": "Ping the service",
         "source": "manual.md lines 2-3"},
    ],
    "missing": [],
}
_ENDPOINT_WITH_REF = {
    "method": "GET", "path": "/ping", "summary": "Ping the service",
    "source": "manual.md lines 2-3", "parameters": [],
    "request": {"schema_ref": "SettleBody"},
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [],
}


def _setup_with_schema(tmp_path, *, directives, responses):
    sources, extraction, focus = setup(
        tmp_path, directives=directives, responses=responses)
    import json
    (extraction / "inventory.json").write_text(
        json.dumps(_INVENTORY_WITH_SCHEMA, ensure_ascii=False), encoding="utf-8")
    (extraction / "endpoints" / "ep1.json").unlink()
    (extraction / "endpoints" / "ep0.json").write_text(
        json.dumps(_ENDPOINT_WITH_REF, ensure_ascii=False), encoding="utf-8")
    return sources, extraction, focus


def _field_directive(**overrides) -> dict:
    return directive(id="trade-no", intent="find_field",
                     text="結算通知一定要帶商店訂單編號", **overrides)


def _field_response(value: str, **overrides) -> dict:
    return response(id="trade-no", anchors=[
        {"type": "field", "value": value, "evidence": [evidence()]}],
        **overrides)


def test_a_field_reachable_through_a_schema_ref_resolves(tmp_path):
    sources, extraction, focus = _setup_with_schema(
        tmp_path, directives=[_field_directive()],
        responses=[_field_response("SettleBody.merchant_trade_no")])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output


def test_a_bare_field_name_resolves(tmp_path):
    sources, extraction, focus = _setup_with_schema(
        tmp_path, directives=[_field_directive()],
        responses=[_field_response("merchant_trade_no")])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output


def test_a_field_the_extraction_does_not_contain_is_rejected(tmp_path):
    sources, extraction, focus = _setup_with_schema(
        tmp_path, directives=[_field_directive()],
        responses=[_field_response("SettleBody.store_order_id")])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "store_order_id" in res.output


def test_an_operation_anchor_is_refused_for_a_find_field_intent(tmp_path):
    sources, extraction, focus = _setup_with_schema(
        tmp_path, directives=[_field_directive()],
        responses=[response(id="trade-no", anchors=[
            {"type": "operation", "value": "GET /ping",
             "evidence": [evidence()]}])])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2
    assert "find_field" in res.output


def test_a_field_anchor_still_requires_exact_evidence(tmp_path):
    sources, extraction, focus = _setup_with_schema(
        tmp_path, directives=[_field_directive()],
        responses=[response(id="trade-no", anchors=[
            {"type": "field", "value": "merchant_trade_no", "evidence": []}])])

    res = verify(sources, extraction, focus)

    assert res.exit_code == 2


def test_a_circular_schema_reference_terminates(tmp_path):
    import json
    inventory = json.loads(json.dumps(_INVENTORY_WITH_SCHEMA))
    inventory["schemas"].append(
        {"name": "Loop", "fields": [{"name": "self_ref", "type": "Loop",
                                     "required": False, "description": None}],
         "enums": [], "constraints": None, "source": "manual.md lines 2-3",
         "schema_ref": "SettleBody"})
    inventory["schemas"][0]["schema_ref"] = "Loop"
    sources, extraction, focus = _setup_with_schema(
        tmp_path, directives=[_field_directive()],
        responses=[_field_response("self_ref")])
    (extraction / "inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8")

    res = verify(sources, extraction, focus)

    assert res.exit_code == 0, res.output
