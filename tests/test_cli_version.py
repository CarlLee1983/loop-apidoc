from __future__ import annotations

from importlib.metadata import version

from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()


def test_version_flag_prints_installed_version():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0, result.stdout
    assert version("loop-apidoc") in result.stdout


def test_version_flag_listed_in_help():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--version" in result.stdout
