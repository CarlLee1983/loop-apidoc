from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.agentcli.assemble import (
    AssembleInputError,
    build_extraction_from_files,
    load_extraction_inputs,
    run_assemble_pipeline,
)
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.run.models import RunStatus

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
    inventory, endpoint_texts, integration = load_extraction_inputs(tmp_path / "extraction")
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


# ── Task 2: run_assemble_pipeline ───────────────────────────────────────────


def test_run_assemble_pipeline_writes_outputs(tmp_path):
    _write_extraction(tmp_path / "extraction")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text("# Demo API\nGET /ping", encoding="utf-8")
    out = tmp_path / "out"

    result = run_assemble_pipeline(
        sources_root=sources,
        extraction_dir=tmp_path / "extraction",
        output_root=out,
        run_id="run-test",
        generated_at=datetime(2026, 6, 27, tzinfo=timezone.utc),
        urls=[],
    )

    run_dir = out / "run-test"
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "openapi.yaml").is_file()
    assert (run_dir / "api-guide.zh-TW.md").is_file()
    assert (run_dir / "provenance.json").is_file()
    assert (run_dir / "preparation-report.json").is_file()
    assert (run_dir / "preparation-report.md").is_file()
    assert (run_dir / "plan" / "normalization-plan.json").is_file()
    assert (run_dir / "validation" / "report.json").is_file()
    prep_payload = json.loads(
        (run_dir / "preparation-report.json").read_text(encoding="utf-8")
    )
    assert prep_payload["status"] == "ready"
    assert prep_payload["summary"]["ready"] == 4
    assert result.status in (RunStatus.PASSED, RunStatus.FAILED)
    assert result.run_dir == str(run_dir)


def test_run_assemble_pipeline_bad_input_leaves_no_run_dir(tmp_path):
    # 擷取輸入錯誤(缺 inventory.json)應在寫入任何輸出前就失敗,
    # 不留下孤兒 run 目錄。
    (tmp_path / "extraction").mkdir()  # 空目錄,無 inventory.json
    sources = tmp_path / "sources"
    sources.mkdir()
    out = tmp_path / "out"

    with pytest.raises(AssembleInputError):
        run_assemble_pipeline(
            sources_root=sources,
            extraction_dir=tmp_path / "extraction",
            output_root=out,
            run_id="run-test",
            generated_at=datetime(2026, 6, 27, tzinfo=timezone.utc),
            urls=[],
        )

    assert not (out / "run-test").exists()
