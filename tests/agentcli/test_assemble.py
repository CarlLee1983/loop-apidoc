from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop_apidoc.agentcli.assemble import (
    AssembleInputError,
    build_extraction_from_files,
    load_extraction_inputs,
)
from loop_apidoc.extraction.store import ExtractionStore

_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "§1"}],
    "security_schemes": [],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "§2"}],
    "schemas": [],
    "errors": [],
    "operational": [],
    "missing": [],
}
_ENDPOINT = {
    "method": "GET", "path": "/ping",
    "parameters": [], "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [],
}


def _write_extraction(extraction_dir: Path) -> None:
    extraction_dir.mkdir(parents=True, exist_ok=True)
    (extraction_dir / "inventory.json").write_text(
        json.dumps(_INVENTORY, ensure_ascii=False), encoding="utf-8")
    eps = extraction_dir / "endpoints"
    eps.mkdir()
    (eps / "ep0.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")


def test_load_extraction_inputs_reads_inventory_and_endpoints(tmp_path):
    _write_extraction(tmp_path / "extraction")
    inventory, endpoint_texts = load_extraction_inputs(tmp_path / "extraction")
    assert inventory["overview"] == "Demo API"
    assert len(endpoint_texts) == 1
    assert json.loads(endpoint_texts[0])["path"] == "/ping"


def test_load_extraction_inputs_missing_inventory_raises(tmp_path):
    (tmp_path / "extraction").mkdir()
    with pytest.raises(AssembleInputError):
        load_extraction_inputs(tmp_path / "extraction")


def test_load_extraction_inputs_bad_json_raises(tmp_path):
    d = tmp_path / "extraction"
    d.mkdir()
    (d / "inventory.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(AssembleInputError):
        load_extraction_inputs(d)


def test_build_extraction_from_files_produces_stage_and_endpoint_artifacts(tmp_path):
    store = ExtractionStore(tmp_path / "store")
    extraction = build_extraction_from_files(
        _INVENTORY, [json.dumps(_ENDPOINT, ensure_ascii=False)], store)
    stage_ids = {a.stage_id for a in extraction.artifacts}
    # inventory 切出 03/04/05/07/08/09 + 敘事 01/02/10,per-endpoint 為 06
    assert {"03", "04", "05", "06", "07", "08", "09"} <= stage_ids
    ep06 = [a for a in extraction.artifacts if a.stage_id == "06"]
    assert len(ep06) == 1
    assert json.loads(ep06[0].answer)["path"] == "/ping"
