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
    # spec 要求五個鍵全部存在；review_html 是人工核對入口。
    assert set(payload) >= {
        "run_id", "run_dir", "ok", "status", "report", "review_html"
    }
    assert isinstance(payload["ok"], bool)
    # exit code 必須與 ok 一致(避免「永遠 FAIL」之類的回歸)
    assert res.exit_code == (0 if payload["ok"] else 1)
    assert Path(payload["run_dir"]).is_dir()
    assert Path(payload["review_html"]).name == "review.html"
    assert Path(payload["review_html"]).is_file()


def test_assemble_plain_output_mentions_status(tmp_path):
    """非 --json 路徑:輸出人類可讀的「狀態 …」字串。"""
    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out),
    ])
    assert res.exit_code in (0, 1)
    assert "狀態" in res.stdout
    assert "review.html" in res.stdout


def test_assemble_missing_inventory_exits_2(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    (extraction / "inventory.json").unlink()
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out),
    ])
    assert res.exit_code == 2


def test_assemble_score_writes_score_reports_and_preserves_exit_status(tmp_path):
    sources, extraction, out = _setup(tmp_path)

    res = runner.invoke(app, [
        "assemble",
        "--sources", str(sources),
        "--extraction", str(extraction),
        "--output", str(out),
        "--score",
        "--json",
    ])

    assert res.exit_code in (0, 1)
    payload = json.loads(res.stdout)
    run_dir = Path(payload["run_dir"])
    assert "score" in payload
    assert payload["score"]["status"] in {"pass", "needs_attention", "fail"}
    assert (run_dir / "score" / "score.json").is_file()
    assert (run_dir / "score" / "score.md").is_file()
    assert res.exit_code == (0 if payload["ok"] else 1)


def test_assemble_without_score_does_not_write_score_reports(tmp_path):
    sources, extraction, out = _setup(tmp_path)

    res = runner.invoke(app, [
        "assemble",
        "--sources", str(sources),
        "--extraction", str(extraction),
        "--output", str(out),
        "--json",
    ])

    payload = json.loads(res.stdout)
    assert "score" not in payload
    assert not (Path(payload["run_dir"]) / "score").exists()


def test_assemble_score_failure_does_not_change_exit_code(tmp_path, monkeypatch):
    """Any non-ScoreInputError from scoring must not alter assemble's validation exit code."""
    import loop_apidoc.score as _score_mod

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(_score_mod, "evaluate_score", _boom)

    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble",
        "--sources", str(sources),
        "--extraction", str(extraction),
        "--output", str(out),
        "--score",
        "--json",
    ])

    assert res.exit_code in (0, 1)
    payload = json.loads(res.stdout)
    assert res.exit_code == (0 if payload["ok"] else 1)
    assert "score_error" in payload
    assert "score failed" in payload["score_error"]
    assert "score" not in payload


def test_assemble_score_emits_loop_block(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--json", "--score",
        "--target-score", "85", "--round-index", "1", "--max-rounds", "6",
    ])
    assert res.exit_code in (0, 1)
    payload = json.loads(res.stdout)
    assert "score" in payload
    assert "loop" in payload
    loop = payload["loop"]
    assert loop["verdict"] in {"converged", "plateau", "exhausted", "continue"}
    assert loop["target"] == 85
    assert loop["round_index"] == 1
    assert loop["max_rounds"] == 6
    assert "actionable" in loop and "irreducible" in loop


def test_assemble_without_score_has_no_loop_block(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--json",
    ])
    payload = json.loads(res.stdout)
    assert "loop" not in payload


def test_assemble_score_exit_code_tracks_ok_not_verdict(tmp_path):
    # target 100 is unreachable, so verdict is plateau/exhausted, but the exit
    # code must still track validation ok, never the verdict.
    sources, extraction, out = _setup(tmp_path)
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--json", "--score", "--target-score", "100",
    ])
    payload = json.loads(res.stdout)
    assert res.exit_code == (0 if payload["ok"] else 1)
