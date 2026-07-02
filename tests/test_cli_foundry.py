from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from tests.foundry._fixtures import write_run_dir

runner = CliRunner()
_RUN_ID = "20260702T120000.000000Z"


def _init(project: Path) -> None:
    result = runner.invoke(app, [
        "foundry", "init",
        "--project", str(project),
        "--docset", "tappay-backend",
        "--title", "TapPay Backend API",
        "--provider", "tappay",
        "--product", "backend-api",
        "--source", "sources/tappay/backend.md:primary",
        "--source", "sources/tappay/errors.md:supplemental",
    ])
    assert result.exit_code == 0, result.output


def test_init_import_approve_flow(tmp_path: Path) -> None:
    _init(tmp_path)
    docset_json = tmp_path / ".foundry" / "api" / "docsets" / "tappay-backend" / "docset.json"
    assert docset_json.is_file()
    assert json.loads(docset_json.read_text())["sources"][1]["role"] == "supplemental"

    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    imp = runner.invoke(app, [
        "foundry", "import", "--project", str(tmp_path),
        "--docset", "tappay-backend", "--run", str(run_dir),
    ])
    assert imp.exit_code == 0, imp.output

    appr = runner.invoke(app, [
        "foundry", "approve", "--project", str(tmp_path),
        "--docset", "tappay-backend", "--run", _RUN_ID, "--by", "human-review", "--json",
    ])
    assert appr.exit_code == 0, appr.output
    payload = json.loads(appr.output)
    assert payload["status"] == "approved"
    assert payload["validation"]["score"] == 92

    cur = runner.invoke(app, [
        "foundry", "current", "--project", str(tmp_path), "--docset", "tappay-backend", "--json",
    ])
    assert cur.exit_code == 0, cur.output
    assert json.loads(cur.output)["current_asset"] == payload["asset_id"]


def test_approve_missing_candidate_exits_2(tmp_path: Path) -> None:
    _init(tmp_path)
    result = runner.invoke(app, [
        "foundry", "approve", "--project", str(tmp_path),
        "--docset", "tappay-backend", "--run", _RUN_ID, "--by", "a",
    ])
    assert result.exit_code == 2, result.output


def test_approve_failing_validation_exits_1(tmp_path: Path) -> None:
    _init(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID, validation_ok=False)
    runner.invoke(app, [
        "foundry", "import", "--project", str(tmp_path),
        "--docset", "tappay-backend", "--run", str(run_dir),
    ])
    result = runner.invoke(app, [
        "foundry", "approve", "--project", str(tmp_path),
        "--docset", "tappay-backend", "--run", _RUN_ID, "--by", "a",
    ])
    assert result.exit_code == 1, result.output


def test_list_shows_registered_docset(tmp_path: Path) -> None:
    _init(tmp_path)
    result = runner.invoke(app, ["foundry", "list", "--project", str(tmp_path), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["docsets"][0]["docset_id"] == "tappay-backend"
