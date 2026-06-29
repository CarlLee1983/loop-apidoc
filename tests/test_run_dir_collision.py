from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.agentcli.assemble import (
    RunDirectoryCollisionError,
    run_assemble_pipeline,
)

_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "§1"}],
    "security_schemes": [], "schemas": [], "errors": [], "operational": [],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "§2"}],
    "missing": [],
}
_ENDPOINT = {
    "method": "GET", "path": "/ping", "parameters": [], "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [],
}


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    extraction = tmp_path / "extraction"
    (extraction / "endpoints").mkdir(parents=True)
    (extraction / "inventory.json").write_text(
        json.dumps(_INVENTORY, ensure_ascii=False), encoding="utf-8")
    (extraction / "endpoints" / "ep0.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text("# Demo API\nGET /ping", encoding="utf-8")
    return sources, extraction, tmp_path / "out"


def _run(sources, extraction, out, run_id):
    now = datetime(2026, 6, 26, 10, 43, 0, tzinfo=timezone.utc)
    return run_assemble_pipeline(
        sources_root=sources, extraction_dir=extraction, output_root=out,
        run_id=run_id, generated_at=now,
    )


def test_reusing_existing_run_dir_raises_collision(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    _run(sources, extraction, out, "fixed-run-id")
    with pytest.raises(RunDirectoryCollisionError) as exc:
        _run(sources, extraction, out, "fixed-run-id")
    assert "fixed-run-id" in str(exc.value)
