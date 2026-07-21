from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.manifest.models import LocalSource, Manifest, ProcessingStatus, SourceFormat


runner = CliRunner()


def _write_manifest(path: Path, sources: Path) -> None:
    now = datetime.now(UTC)
    path.write_text(
        Manifest(
            sources_root=str(sources),
            generated_at=now,
            local_sources=[
                LocalSource(
                    relative_path="api.md", mime_type="text/markdown", source_format=SourceFormat.MARKDOWN,
                    size_bytes=16, sha256="a", scanned_at=now, supported=True, status=ProcessingStatus.PENDING,
                )
            ],
        ).model_dump_json(),
        encoding="utf-8",
    )


def test_extract_markdown_drafts_writes_non_authoritative_fact_index(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "api.md").write_text("## GET /api/ping\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, sources)
    output = tmp_path / "markdown-api-facts.json"

    result = runner.invoke(
        app,
        [
            "extract-markdown-drafts",
            "--sources", str(sources),
            "--manifest", str(manifest),
            "--output", str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["kind"] == "markdown_api_drafts"
    assert payload["authoritative"] is False
    assert payload["sources"][0]["endpoints"][0]["path"] == "/api/ping"


def test_extract_markdown_drafts_refuses_to_overwrite_output(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "api.md").write_text("## GET /api/ping\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, sources)
    output = tmp_path / "markdown-api-facts.json"
    output.write_text("{}", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "extract-markdown-drafts",
            "--sources", str(sources),
            "--manifest", str(manifest),
            "--output", str(output),
        ],
    )

    assert result.exit_code == 2
    assert "extract-markdown-drafts error: output already exists" in result.output
