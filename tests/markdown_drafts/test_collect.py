from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from loop_apidoc.manifest.models import LocalSource, Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.markdown_drafts.collect import collect_markdown_drafts


def test_collect_markdown_drafts_uses_only_pending_manifest_markdown_sources(tmp_path: Path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "balance.md").write_text("## GET /balance\n", encoding="utf-8")
    (tmp_path / "ignored.md").write_text("## GET /ignored\n", encoding="utf-8")
    now = datetime.now(UTC)
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=now,
        local_sources=[
            LocalSource(
                relative_path="api/balance.md", mime_type="text/markdown", source_format=SourceFormat.MARKDOWN,
                size_bytes=18, sha256="a", scanned_at=now, supported=True, status=ProcessingStatus.PENDING,
            ),
            LocalSource(
                relative_path="ignored.md", mime_type="text/markdown", source_format=SourceFormat.MARKDOWN,
                size_bytes=18, sha256="b", scanned_at=now, supported=True, status=ProcessingStatus.IGNORED,
            ),
        ],
    )

    drafts = collect_markdown_drafts(tmp_path, manifest)

    assert drafts.authoritative is False
    assert [source.relative_path for source in drafts.sources] == ["api/balance.md"]
    assert drafts.sources[0].endpoints[0].path == "/balance"
