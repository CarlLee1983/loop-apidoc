from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from loop_apidoc.manifest.models import LocalSource, Manifest, ProcessingStatus, SourceFormat


def test_collect_scaffold_inputs_uses_only_readable_pending_markdown(tmp_path: Path):
    from loop_apidoc.extraction_scaffold.collect import collect_scaffold_inputs

    (tmp_path / "api.md").write_text("## GET /ping\n", encoding="utf-8")
    manifest = _manifest(tmp_path, [
        _source("api.md", SourceFormat.MARKDOWN, ProcessingStatus.PENDING),
        _source("ignored.md", SourceFormat.MARKDOWN, ProcessingStatus.IGNORED),
        _source("api.pdf", SourceFormat.PDF, ProcessingStatus.PENDING),
    ])

    inputs = collect_scaffold_inputs(tmp_path, manifest)

    assert [draft.relative_path for draft in inputs.drafts.sources] == ["api.md"]
    assert inputs.source_texts == {"api.md": "## GET /ping\n"}


def test_collect_scaffold_inputs_rejects_no_readable_markdown(tmp_path: Path):
    from loop_apidoc.extraction_scaffold.collect import (
        ExtractionScaffoldInputError,
        collect_scaffold_inputs,
    )

    manifest = _manifest(tmp_path, [_source("missing.md", SourceFormat.MARKDOWN, ProcessingStatus.PENDING)])

    with pytest.raises(ExtractionScaffoldInputError, match="no usable Markdown"):
        collect_scaffold_inputs(tmp_path, manifest)


def _manifest(root: Path, sources: list[LocalSource]) -> Manifest:
    return Manifest(sources_root=str(root), generated_at=datetime.now(UTC), local_sources=sources)


def _source(path: str, source_format: SourceFormat, status: ProcessingStatus) -> LocalSource:
    return LocalSource(
        relative_path=path,
        mime_type="text/markdown",
        source_format=source_format,
        size_bytes=1,
        sha256="a",
        scanned_at=datetime.now(UTC),
        supported=True,
        status=status,
    )
