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


def test_assemble_json_emits_run_dir_and_report(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--json",
    ])
    assert res.exit_code in (0, 1)  # PASS 或驗證 FAIL,皆非崩潰
    payload = json.loads(res.stdout)
    # spec 要求五個鍵全部存在
    assert set(payload) >= {"run_id", "run_dir", "ok", "status", "report"}
    assert isinstance(payload["ok"], bool)
    # exit code 必須與 ok 一致(避免「永遠 FAIL」之類的回歸)
    assert res.exit_code == (0 if payload["ok"] else 1)
    assert Path(payload["run_dir"]).is_dir()


def test_assemble_plain_output_mentions_status(tmp_path):
    """非 --json 路徑:輸出人類可讀的「狀態 …」字串。"""
    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out),
    ])
    assert res.exit_code in (0, 1)
    assert "狀態" in res.stdout


def test_assemble_missing_inventory_exits_2(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    (extraction / "inventory.json").unlink()
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out),
    ])
    assert res.exit_code == 2
