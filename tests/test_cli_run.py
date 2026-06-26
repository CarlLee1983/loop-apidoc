from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import loop_apidoc.cli as cli
from loop_apidoc.run.models import RunResult, RunStatus
from loop_apidoc.validate.models import ValidationReport

runner = CliRunner()


def test_run_exit_zero_on_pass(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.md").write_text("# x", encoding="utf-8")

    def fake_pipeline(**kwargs) -> RunResult:
        return RunResult(
            run_id="rid",
            run_dir=str(tmp_path / "out" / "rid"),
            report=ValidationReport(issues=[]),
            rounds=0,
            status=RunStatus.PASSED,
        )

    monkeypatch.setattr(cli, "run_pipeline", fake_pipeline)
    result = runner.invoke(
        cli.app,
        [
            "run",
            "--notebook-url",
            "nb://x",
            "--sources",
            str(tmp_path / "src"),
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0


def test_run_exit_one_on_failure(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.md").write_text("# x", encoding="utf-8")

    def fake_pipeline(**kwargs) -> RunResult:
        return RunResult(
            run_id="rid",
            run_dir=str(tmp_path / "out" / "rid"),
            report=ValidationReport(issues=[]),
            rounds=3,
            status=RunStatus.FAILED,
        )

    monkeypatch.setattr(cli, "run_pipeline", fake_pipeline)
    result = runner.invoke(
        cli.app,
        [
            "run",
            "--notebook-url",
            "nb://x",
            "--sources",
            str(tmp_path / "src"),
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 1
