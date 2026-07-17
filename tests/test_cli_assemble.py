from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def _source_quality_dir(tmp_path: Path, *, verdict: str = "pass") -> Path:
    quality = tmp_path / "source-quality"
    quality.mkdir()
    (quality / "source-quality-report.json").write_text(
        json.dumps({
            "verdict": verdict,
            "source_set": "demo-v1",
            "findings": [],
        }),
        encoding="utf-8",
    )
    (quality / "source-diff.json").write_text(
        json.dumps({"entries": []}), encoding="utf-8"
    )
    return quality


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


def test_assemble_persists_passing_source_quality_artifacts(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    quality = _source_quality_dir(tmp_path)

    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--source-quality", str(quality), "--json",
    ])

    assert res.exit_code in (0, 1), res.output
    run_dir = Path(json.loads(res.stdout)["run_dir"])
    saved = json.loads(
        (run_dir / "source-quality" / "source-quality-report.json").read_text(encoding="utf-8")
    )
    assert saved["source_set"] == "demo-v1"
    assert (run_dir / "source-quality" / "source-diff.json").is_file()


def test_assemble_rejects_source_quality_blocker_without_creating_run_dir(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    quality = _source_quality_dir(tmp_path, verdict="reject")

    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--source-quality", str(quality),
    ])

    assert res.exit_code == 2
    assert "reject" in res.output
    assert not out.exists() or not any(out.iterdir())


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


def test_assemble_score_waives_declared_endpoint_example_gap(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    endpoint_path = extraction / "endpoints" / "ep0.json"
    endpoint = json.loads(endpoint_path.read_text(encoding="utf-8"))
    endpoint["missing"] = ["source does not provide examples"]
    endpoint_path.write_text(json.dumps(endpoint, ensure_ascii=False), encoding="utf-8")

    res = runner.invoke(app, [
        "assemble",
        "--sources", str(sources),
        "--extraction", str(extraction),
        "--output", str(out),
        "--score",
        "--json",
    ])

    payload = json.loads(res.stdout)
    plan = json.loads(
        (Path(payload["run_dir"]) / "plan" / "normalization-plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(
        item.get("query_id") == "06-ep0"
        and item.get("operation_location") == "paths./ping.get"
        for item in plan["missing_items"]
    )
    example_finding = next(
        finding
        for finding in payload["score"]["findings"]
        if finding["code"] == "REQUIRED_INFO_MISSING"
        and finding["location"] == "paths./ping.get"
    )
    assert example_finding["score_impact"] == 0


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


def test_assemble_score_input_error_does_not_change_exit_code(tmp_path, monkeypatch):
    import loop_apidoc.score as _score_mod
    from loop_apidoc.score import ScoreInputError

    def _missing_score_artifact(*_args, **_kwargs):
        raise ScoreInputError("missing score artifact")

    monkeypatch.setattr(_score_mod, "load_score_inputs", _missing_score_artifact)

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
    assert payload["score_error"] == "missing score artifact"
    assert "score" not in payload
    assert "score input error: missing score artifact" in res.stderr


def test_assemble_score_unexpected_exception_propagates(tmp_path, monkeypatch):
    import loop_apidoc.score as _score_mod

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(_score_mod, "evaluate_score", _boom)

    sources, extraction, out = _setup(tmp_path)
    with pytest.raises(RuntimeError, match="boom"):
        runner.invoke(app, [
            "assemble",
            "--sources", str(sources),
            "--extraction", str(extraction),
            "--output", str(out),
            "--score",
            "--json",
        ], catch_exceptions=False)


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


def _coverage_payload() -> dict:
    return {
        "entry_url": "https://docs.example.com/api/",
        "confirmed_by_user": True,
        "expected": [
            {"url": "https://docs.example.com/api/ping", "title": "Ping", "source": "nav"}
        ],
        "results": [
            {"url": "https://docs.example.com/api/ping", "status": "fetched",
             "file": "url_sources/ping.md", "method": "defuddle"}
        ],
    }


def test_assemble_with_url_coverage_adds_phase(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps(_coverage_payload()), encoding="utf-8")
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--url", "https://docs.example.com/api/",
        "--url-coverage", str(coverage), "--json",
    ])
    assert res.exit_code in (0, 1)
    run_dir = Path(json.loads(res.stdout)["run_dir"])
    prep = json.loads((run_dir / "preparation-report.json").read_text(encoding="utf-8"))
    assert any(phase["id"] == "url_coverage" for phase in prep["phases"])


def test_assemble_url_coverage_without_url_exits_2_without_run_dir(tmp_path):
    # 明確傳入 --url-coverage 但 run 沒有任何 URL 來源:靜默丟棄違反
    # fail-loud 原則,必須在建立 run 目錄前報錯。
    sources, extraction, out = _setup(tmp_path)
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps(_coverage_payload()), encoding="utf-8")
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--url-coverage", str(coverage),
    ])
    assert res.exit_code == 2
    assert "--url" in res.output
    assert not out.exists() or not any(out.iterdir())


def test_assemble_malformed_coverage_exits_2_without_run_dir(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    coverage = tmp_path / "coverage.json"
    coverage.write_text('{"results": [{"status": "bogus"}]}', encoding="utf-8")
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--url", "https://docs.example.com/api/",
        "--url-coverage", str(coverage),
    ])
    assert res.exit_code == 2
    # fail-loud before any run dir is created
    assert not out.exists() or not any(out.iterdir())
