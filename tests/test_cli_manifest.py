from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()


def test_manifest_command_writes_output(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "guide.md").write_text("hello", encoding="utf-8")
    output = tmp_path / "manifest.json"

    result = runner.invoke(
        app, ["manifest", "--sources", str(sources), "--output", str(output)]
    )

    assert result.exit_code == 0, result.stdout
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["local_sources"][0]["relative_path"] == "guide.md"
    assert data["local_sources"][0]["status"] == "pending"


def test_manifest_command_prints_to_stdout(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "guide.md").write_text("hello", encoding="utf-8")

    result = runner.invoke(app, ["manifest", "--sources", str(sources)])

    assert result.exit_code == 0
    assert '"sources_root"' in result.stdout


def test_manifest_command_rejects_missing_sources_dir(tmp_path: Path):
    missing = tmp_path / "does-not-exist"

    result = runner.invoke(app, ["manifest", "--sources", str(missing)])

    assert result.exit_code != 0
