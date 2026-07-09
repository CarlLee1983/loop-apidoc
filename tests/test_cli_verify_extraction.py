from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()

_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "manual.md p.1"}],
    "security_schemes": [], "schemas": [], "errors": [], "operational": [],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "manual.md p.2"}],
    "missing": [],
}
_ENDPOINT = {
    "method": "GET", "path": "/ping", "parameters": [], "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [],
}


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    extraction = tmp_path / "extraction"
    (extraction / "endpoints").mkdir(parents=True)
    (extraction / "inventory.json").write_text(
        json.dumps(_INVENTORY, ensure_ascii=False), encoding="utf-8")
    (extraction / "endpoints" / "ep0.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text("# Demo API\nGET /ping", encoding="utf-8")
    return sources, extraction


def _invoke(sources: Path, extraction: Path, *extra: str):
    return runner.invoke(app, [
        "verify-extraction", "--sources", str(sources),
        "--extraction", str(extraction), *extra,
    ])


def test_clean_extraction_exits_zero(tmp_path):
    sources, extraction = _setup(tmp_path)

    res = _invoke(sources, extraction)

    assert res.exit_code == 0, res.output


def test_violations_exit_two_and_are_all_listed(tmp_path):
    sources, extraction = _setup(tmp_path)
    # 未以 / 開頭的 path(source_guard)+ 端點檔不在 inventory(cross_file)
    (extraction / "endpoints" / "ep0.json").write_text(
        json.dumps({**_ENDPOINT, "path": "pong"}, ensure_ascii=False),
        encoding="utf-8")

    res = _invoke(sources, extraction)

    assert res.exit_code == 2
    assert "ep0.json" in res.output
    assert "/ping" in res.output


def test_json_flag_emits_an_array_of_violations(tmp_path):
    sources, extraction = _setup(tmp_path)
    (extraction / "endpoints" / "ep1.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")

    res = _invoke(sources, extraction, "--json")

    assert res.exit_code == 2
    payload = json.loads(res.output)
    assert isinstance(payload, list)
    assert payload and all(isinstance(v, str) for v in payload)


def test_json_flag_emits_empty_array_when_clean(tmp_path):
    sources, extraction = _setup(tmp_path)

    res = _invoke(sources, extraction, "--json")

    assert res.exit_code == 0
    assert json.loads(res.output) == []


def test_malformed_json_exits_two(tmp_path):
    sources, extraction = _setup(tmp_path)
    (extraction / "endpoints" / "ep0.json").write_text("{ nope", encoding="utf-8")

    res = _invoke(sources, extraction)

    assert res.exit_code == 2


def test_no_run_directory_is_created(tmp_path):
    sources, extraction = _setup(tmp_path)

    _invoke(sources, extraction)

    entries = {p.name for p in tmp_path.iterdir()}
    assert entries == {"sources", "extraction"}
