from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()

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
    "method": "GET", "path": "/ping", "source": "§2",
    "parameters": [], "request": None,
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
    (sources / "spec.md").write_text("# Demo API\nGET /ping", encoding="utf-8")
    (sources / "scratch.md").write_text("# 草稿", encoding="utf-8")
    out = tmp_path / "out"
    return sources, extraction, out


def test_assemble_exclude_marks_source_ignored(tmp_path: Path):
    sources, extraction, out = _setup(tmp_path)

    result = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--exclude", "scratch.*",
    ])

    assert result.exit_code in (0, 1), result.stdout
    run_dir = next(out.iterdir())
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    statuses = {s["relative_path"]: s["status"] for s in manifest["local_sources"]}
    assert statuses == {"spec.md": "pending", "scratch.md": "ignored"}


def test_assemble_without_exclude_treats_scratch_as_a_source(tmp_path: Path):
    """兩份文件 → 不指名檔案的 source 觸發邊界檢查 → exit 2。"""
    sources, extraction, out = _setup(tmp_path)

    result = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out),
    ])

    assert result.exit_code == 2
    assert not out.exists() or not any(out.iterdir())
