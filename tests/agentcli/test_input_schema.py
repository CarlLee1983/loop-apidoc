from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop_apidoc.agentcli.assemble import AssembleInputError, load_extraction_inputs

_INVENTORY = {
    "title": None, "version": None, "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "§1"}],
    "security_schemes": [], "errors": [], "operational": [],
    "schemas": [{"name": "Body", "fields": [
        {"name": "amount", "type": "int", "required": True, "description": None}],
        "enums": [], "constraints": None, "source": "§3"}],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "ping",
                   "source": "§2"}],
    "missing": [],
}
_ENDPOINT = {
    "method": "GET", "path": "/ping", "source": "§2", "parameters": [],
    "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None,
                   "schema_ref": None}],
    "tags": [], "security": [], "examples": [], "missing": [],
}


def _write(extraction: Path, inventory=_INVENTORY, endpoint=_ENDPOINT,
           integration=None) -> None:
    (extraction / "endpoints").mkdir(parents=True)
    (extraction / "inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
    (extraction / "endpoints" / "ep0.json").write_text(
        json.dumps(endpoint, ensure_ascii=False), encoding="utf-8")
    if integration is not None:
        (extraction / "integration.json").write_text(
            json.dumps(integration, ensure_ascii=False), encoding="utf-8")


def test_valid_inputs_pass(tmp_path):
    extraction = tmp_path / "x"
    _write(extraction)
    inv, eps, integ = load_extraction_inputs(extraction)
    assert inv["overview"] == "Demo API"
    assert len(eps) == 1
    assert integ is None


def test_localized_schema_field_key_is_rejected(tmp_path):
    # schemas[].fields 用本地化鍵(型態/必填)而非 English name/type → 必須被擋下,
    # 且錯誤訊息指出 inventory.json 與出錯欄位路徑。
    bad = json.loads(json.dumps(_INVENTORY))
    bad["schemas"][0]["fields"] = [{"型態": "int", "必填": True}]
    extraction = tmp_path / "x"
    _write(extraction, inventory=bad)
    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)
    msg = str(exc.value)
    assert "inventory.json" in msg
    assert "schemas" in msg and "fields" in msg


def test_malformed_endpoint_detail_is_rejected(tmp_path):
    # parameters 應為 list,給成物件 → 擋下並指出 ep0.json。
    bad = json.loads(json.dumps(_ENDPOINT))
    bad["parameters"] = {"oops": "not a list"}
    extraction = tmp_path / "x"
    _write(extraction, endpoint=bad)
    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)
    assert "ep0.json" in str(exc.value)
    assert "parameters" in str(exc.value)


@pytest.mark.parametrize("methods", [[], ["GET", "  "], ["GET", "get"], "GET"])
def test_invalid_multi_method_endpoint_detail_is_rejected(tmp_path, methods):
    bad = json.loads(json.dumps(_ENDPOINT))
    bad.pop("method")
    bad["methods"] = methods
    extraction = tmp_path / "x"
    _write(extraction, endpoint=bad)

    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)

    assert "ep0.json" in str(exc.value)
    assert "methods" in str(exc.value)


def test_invalid_multi_method_inventory_entry_is_rejected(tmp_path):
    bad = json.loads(json.dumps(_INVENTORY))
    bad["endpoints"][0].pop("method")
    bad["endpoints"][0]["methods"] = []
    extraction = tmp_path / "x"
    _write(extraction, inventory=bad)

    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)

    assert "inventory.json" in str(exc.value)
    assert "endpoints[0].methods" in str(exc.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [("method", "BOGUS"), ("method", " GET "),
     ("methods", ["GET", "BOGUS"]), ("methods", ["GET", " POST "])],
)
def test_noncanonical_endpoint_http_methods_are_rejected(tmp_path, field, value):
    bad = json.loads(json.dumps(_ENDPOINT))
    bad.pop("method")
    bad[field] = value
    extraction = tmp_path / "x"
    _write(extraction, endpoint=bad)

    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)

    assert "ep0.json" in str(exc.value)
    assert field in str(exc.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [("method", "BOGUS"), ("method", " GET "),
     ("methods", ["GET", "BOGUS"]), ("methods", ["GET", " POST "])],
)
def test_noncanonical_inventory_http_methods_are_rejected(tmp_path, field, value):
    bad = json.loads(json.dumps(_INVENTORY))
    bad["endpoints"][0].pop("method")
    bad["endpoints"][0][field] = value
    extraction = tmp_path / "x"
    _write(extraction, inventory=bad)

    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)

    assert "inventory.json" in str(exc.value)
    assert field in str(exc.value)


def test_legacy_lowercase_methods_are_normalized_before_downstream_use(tmp_path):
    inventory = json.loads(json.dumps(_INVENTORY))
    inventory["endpoints"][0]["method"] = "get"
    endpoint = json.loads(json.dumps(_ENDPOINT))
    endpoint["method"] = "post"
    extraction = tmp_path / "x"
    _write(extraction, inventory=inventory, endpoint=endpoint)

    loaded_inventory, endpoint_texts, _ = load_extraction_inputs(extraction)

    assert loaded_inventory["endpoints"][0]["method"] == "GET"
    assert json.loads(endpoint_texts[0])["method"] == "POST"


def test_generator_supported_param_field_keys_are_allowed(tmp_path):
    # 產生器(openapi.py)會讀 param/field 上的 enum/location/schema 作為 in/type 的
    # 後備鍵;這些是合法 English 鍵(非本地化錯誤),嚴格守門不可誤擋。
    inv = json.loads(json.dumps(_INVENTORY))
    inv["schemas"][0]["fields"] = [
        {"name": "status", "enum": ["A", "B"], "schema": "string"}]
    ep = json.loads(json.dumps(_ENDPOINT))
    ep["parameters"] = [
        {"name": "q", "location": "query", "schema": "string", "enum": ["x"]}]
    extraction = tmp_path / "x"
    _write(extraction, inventory=inv, endpoint=ep)
    load_extraction_inputs(extraction)  # 不應拋出


def test_schema_field_source_is_accepted(tmp_path):
    inv = json.loads(json.dumps(_INVENTORY))
    inv["schemas"][0]["fields"][0]["source"] = "spec.md p.12"
    extraction = tmp_path / "x"
    _write(extraction, inventory=inv)

    loaded, _, _ = load_extraction_inputs(extraction)

    assert loaded["schemas"][0]["fields"][0]["source"] == "spec.md p.12"


@pytest.mark.parametrize(
    "evidence",
    [
        [{"source": "spec.md", "locator": {"kind": "line_range", "start_line": 1,
                                                "end_line": 1},
          "fragment_digest": "a" * 64, "claim_path": "/summary"}],
        [{"version": 1, "source": "spec.md", "locator": {"kind": "line_range",
                                                                 "start_line": 1,
                                                                 "end_line": 1},
          "fragment_digest": "not-a-digest", "claim_path": "/summary"}],
        [{"version": 1, "source": "spec.md", "locator": {"kind": "whole_document"},
          "fragment_digest": "a" * 64, "claim_path": "/summary"}],
    ],
)
def test_malformed_exact_evidence_is_rejected_at_input_boundary(tmp_path, evidence):
    inventory = json.loads(json.dumps(_INVENTORY))
    inventory["endpoints"][0]["evidence"] = evidence
    extraction = tmp_path / "x"
    _write(extraction, inventory=inventory)

    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)

    assert "inventory.json" in str(exc.value)
    assert "evidence" in str(exc.value)


def test_x_extension_key_on_field_is_allowed(tmp_path):
    # x-conditional-required 等 x- 擴充鍵屬合法(benchmark 實際使用),不可誤擋。
    ok = json.loads(json.dumps(_INVENTORY))
    ok["schemas"][0]["fields"][0]["x-conditional-required"] = "當 type=card"
    extraction = tmp_path / "x"
    _write(extraction, inventory=ok)
    load_extraction_inputs(extraction)  # 不應拋出


def test_invalid_integration_is_rejected_with_filename(tmp_path):
    extraction = tmp_path / "x"
    _write(extraction, integration={"crypto": "should-be-a-list"})
    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)
    assert "integration.json" in str(exc.value)


def test_operational_applicability_requires_an_operation_identity(tmp_path):
    inventory = json.loads(json.dumps(_INVENTORY))
    inventory["operational"] = [
        {
            "topic": "Amount semantics",
            "detail": "Use the wager amount.",
            "source": "spec.md p.9",
            "applies_to": [{"field": "request.amount"}],
        }
    ]
    extraction = tmp_path / "x"
    _write(extraction, inventory=inventory)

    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)

    assert "inventory.json" in str(exc.value)
    assert "operational[0].applies_to[0].operation" in str(exc.value)


def test_null_response_status_is_allowed(tmp_path):
    # webhook 風格回應無 HTTP status(benchmark 實際存在)→ 允許 null。
    ep = json.loads(json.dumps(_ENDPOINT))
    ep["responses"] = [{"status": None, "description": "幕後通知", "schema": None}]
    extraction = tmp_path / "x"
    _write(extraction, endpoint=ep)
    load_extraction_inputs(extraction)  # 不應拋出


def _with_errors(*entries) -> dict:
    inventory = json.loads(json.dumps(_INVENTORY))
    inventory["errors"] = list(entries)
    return inventory


@pytest.mark.parametrize("entry, expected_path", [
    ({"meaning": "餘額不足", "source": "§9"}, "errors[0].code"),
    ({"code": 1001, "meaning": "餘額不足", "source": "§9"}, "errors[0].code"),
    ({"code": "", "meaning": "餘額不足", "source": "§9"}, "errors[0].code"),
    ({"code": "   ", "meaning": "餘額不足", "source": "§9"}, "errors[0].code"),
    ({"code": "1001", "source": "§9"}, "errors[0].meaning"),
])
def test_error_entry_without_a_usable_code_or_meaning_is_rejected(
        tmp_path, entry, expected_path):
    # errors[] 是錯誤碼流進 OpenAPI ErrorCode enum 的唯一路徑;缺碼、非字串碼、
    # 空白碼、缺語意都必須在建立 run 目錄之前擋下。
    extraction = tmp_path / "x"
    _write(extraction, inventory=_with_errors(entry))

    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)

    assert "inventory.json" in str(exc.value)
    assert expected_path in str(exc.value)


def test_error_entry_with_empty_meaning_is_allowed(tmp_path):
    # 語意是否完整由 validation 判斷,不在輸入邊界重複把關 —— 兩層都管同一件事
    # 會讓同一個問題從兩個地方冒出來。
    extraction = tmp_path / "x"
    _write(extraction, inventory=_with_errors(
        {"code": "1001", "meaning": "", "http_status": None,
         "applicable_to": [], "source": "§9"}))

    load_extraction_inputs(extraction)  # 不應拋出


def test_error_entry_keeps_extension_keys_and_typed_evidence(tmp_path):
    # 收緊的是「code 一定在且是字串」,不是「禁止未知鍵」:x- 擴充鍵、v1 exact
    # evidence,以及 source_facts 覆蓋檢查刻意讀取的巢狀欄位結構都必須通過。
    extraction = tmp_path / "x"
    _write(extraction, inventory=_with_errors({
        "code": "1001",
        "meaning": "餘額不足",
        "http_status": "400",
        "applicable_to": ["POST /transfer"],
        "source": "spec.md lines 10-20",
        "fields": [{"name": "balance", "type": "int"}],
        "x-vendor-note": "legacy",
        "evidence": [{
            "version": 1,
            "source": "spec.md",
            "locator": {"kind": "line_range", "start_line": 10, "end_line": 20},
            "fragment_digest": "a" * 64,
            "claim_path": "/code",
        }],
    }))

    inventory, _, _ = load_extraction_inputs(extraction)

    # 巢狀欄位結構必須原封不動傳到消費端 —— source_facts 的覆蓋檢查靠它,才不會
    # 把共用錯誤表在每個端點上都算成未覆蓋欄位。
    assert inventory["errors"][0]["fields"] == [{"name": "balance", "type": "int"}]
    assert inventory["errors"][0]["x-vendor-note"] == "legacy"


def test_error_entry_with_malformed_evidence_is_rejected(tmp_path):
    extraction = tmp_path / "x"
    _write(extraction, inventory=_with_errors({
        "code": "1001", "meaning": "餘額不足", "source": "§9",
        "evidence": [{"version": 1, "source": "spec.md"}],
    }))

    with pytest.raises(AssembleInputError) as exc:
        load_extraction_inputs(extraction)

    assert "errors[0].evidence[0]" in str(exc.value)


_BENCH = Path(__file__).resolve().parents[2] / "benchmarks"


@pytest.mark.parametrize("case_dir", sorted(
    p.parent.parent for p in _BENCH.glob("*/extraction/inventory.json")))
def test_committed_benchmark_fixtures_pass(case_dir):
    load_extraction_inputs(case_dir / "extraction")
