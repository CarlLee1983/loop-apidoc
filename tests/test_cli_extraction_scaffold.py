from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.manifest.models import LocalSource, Manifest, ProcessingStatus, SourceFormat


runner = CliRunner()


def test_scaffold_extraction_writes_review_only_tree(tmp_path: Path):
    sources, manifest = _sources_and_manifest(tmp_path)
    output = tmp_path / "work" / "scaffold"

    result = runner.invoke(
        app,
        ["scaffold-extraction", "--sources", str(sources), "--manifest", str(manifest), "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary == {"endpoints": 1, "fields": 1, "examples": 1, "omitted_tables": 0, "output": str(output)}
    assert (output / "inventory.json").exists()
    assert (output / "endpoints" / "ep00.json").exists()


def test_scaffold_extraction_refuses_nonempty_output(tmp_path: Path):
    sources, manifest = _sources_and_manifest(tmp_path)
    output = tmp_path / "scaffold"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")

    result = runner.invoke(
        app,
        ["scaffold-extraction", "--sources", str(sources), "--manifest", str(manifest), "--output", str(output)],
    )

    assert result.exit_code == 2
    assert "scaffold-extraction error: output already exists" in result.output


def _sources_and_manifest(tmp_path: Path) -> tuple[Path, Path]:
    sources = tmp_path / "sources"
    sources.mkdir()
    source = (
        "# Ping API\n"
        "## GET /ping\n"
        "### Query\n"
        "| Name | Type | Required |\n"
        "| --- | --- | --- |\n"
        "| verbose | boolean | no |\n"
        "### Response\n"
        "```json\n"
        "{\"ok\": true}\n"
        "```\n"
    )
    (sources / "sources.md").write_text(source, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    now = datetime.now(UTC)
    manifest.write_text(
        Manifest(
            sources_root=str(sources),
            generated_at=now,
            local_sources=[LocalSource(
                relative_path="sources.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=len(source),
                sha256="a",
                scanned_at=now,
                supported=True,
                status=ProcessingStatus.PENDING,
            )],
        ).model_dump_json(),
        encoding="utf-8",
    )
    return sources, manifest
