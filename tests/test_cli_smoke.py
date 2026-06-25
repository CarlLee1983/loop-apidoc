from __future__ import annotations

from typer.testing import CliRunner

from loop_apidoc.cli import app


def test_help_runs():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "pipeline" in result.stdout.lower()
