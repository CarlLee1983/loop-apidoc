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


def test_manifest_command_accepts_a_single_source_file(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    selected = sources / "guide.md"
    selected.write_text("selected", encoding="utf-8")
    (sources / "unselected.md").write_text("unselected", encoding="utf-8")

    result = runner.invoke(app, ["manifest", "--sources", str(selected)])

    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["sources_root"] == str(sources)
    assert [source["relative_path"] for source in data["local_sources"]] == ["guide.md"]
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


def test_manifest_command_accepts_repeatable_exclude(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "guide.md").write_text("hello", encoding="utf-8")
    (sources / "notes.md").write_text("scratch", encoding="utf-8")
    (sources / "draft.md").write_text("wip", encoding="utf-8")

    result = runner.invoke(
        app,
        ["manifest", "--sources", str(sources),
         "--exclude", "notes.*", "--exclude", "draft.*"],
    )

    assert result.exit_code == 0, result.stdout
    statuses = {s["relative_path"]: s["status"] for s in json.loads(result.stdout)["local_sources"]}
    assert statuses == {"guide.md": "pending", "notes.md": "ignored", "draft.md": "ignored"}


def test_manifest_command_ignores_readme_by_default(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "README.md").write_text("dir description", encoding="utf-8")
    (sources / "guide.md").write_text("hello", encoding="utf-8")

    result = runner.invoke(app, ["manifest", "--sources", str(sources)])

    assert result.exit_code == 0, result.stdout
    statuses = {s["relative_path"]: s["status"] for s in json.loads(result.stdout)["local_sources"]}
    assert statuses["README.md"] == "ignored"


def test_manifest_accepts_html_as_a_supported_snapshot_format(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "transfer.html").write_text("<main>Transfer</main>", encoding="utf-8")

    result = runner.invoke(app, ["manifest", "--sources", str(sources)])

    assert result.exit_code == 0, result.stdout
    source = json.loads(result.stdout)["local_sources"][0]
    assert source["source_format"] == "html"
    assert source["supported"] is True
