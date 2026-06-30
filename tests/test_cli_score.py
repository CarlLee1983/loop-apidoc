from __future__ import annotations

import json

from typer.testing import CliRunner

from loop_apidoc.cli import app
from tests.score.test_loader import write_score_run

runner = CliRunner()


def test_score_command_writes_reports_and_prints_json(tmp_path) -> None:
    run_dir = write_score_run(tmp_path / "run")

    result = runner.invoke(app, ["score", "--output", str(run_dir), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["score"] == 100
    assert (run_dir / "score" / "score.json").is_file()
    assert (run_dir / "score" / "score.md").is_file()


def test_score_command_plain_output_mentions_status_and_report(tmp_path) -> None:
    run_dir = write_score_run(tmp_path / "run")

    result = runner.invoke(app, ["score", "--output", str(run_dir)])

    assert result.exit_code == 0
    assert "score PASS" in result.stdout
    assert "score/score.json" in result.stdout


def test_score_command_needs_attention_exits_1(tmp_path) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / "review.html").unlink()

    result = runner.invoke(app, ["score", "--output", str(run_dir), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "needs_attention"


def test_score_command_review_profile_uses_review_threshold(tmp_path) -> None:
    run_dir = write_score_run(tmp_path / "run")

    result = runner.invoke(
        app,
        ["score", "--output", str(run_dir), "--profile", "review", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["profile"] == "review"
    assert payload["min_score"] == 70


def test_score_command_input_error_exits_2_without_output_dir(tmp_path) -> None:
    run_dir = write_score_run(tmp_path / "run")
    (run_dir / "manifest.json").unlink()

    result = runner.invoke(app, ["score", "--output", str(run_dir)])

    assert result.exit_code == 2
    assert "score input error" in result.stderr
    assert not (run_dir / "score").exists()
