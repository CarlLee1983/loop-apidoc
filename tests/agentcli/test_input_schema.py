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


def test_null_response_status_is_allowed(tmp_path):
    # webhook 風格回應無 HTTP status(benchmark 實際存在)→ 允許 null。
    ep = json.loads(json.dumps(_ENDPOINT))
    ep["responses"] = [{"status": None, "description": "幕後通知", "schema": None}]
    extraction = tmp_path / "x"
    _write(extraction, endpoint=ep)
    load_extraction_inputs(extraction)  # 不應拋出


_BENCH = Path(__file__).resolve().parents[2] / "benchmarks"


@pytest.mark.parametrize("case_dir", sorted(
    p.parent.parent for p in _BENCH.glob("*/extraction/inventory.json")))
def test_committed_benchmark_fixtures_pass(case_dir):
    load_extraction_inputs(case_dir / "extraction")
