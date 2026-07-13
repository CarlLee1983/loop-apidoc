from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import LocalSource, Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.source_quality.diff import build_source_diff


def _manifest(sha256: str) -> Manifest:
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    return Manifest(
        sources_root="./sources", generated_at=now,
        local_sources=[LocalSource(
            relative_path="manual.md", mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=12, sha256=sha256,
            scanned_at=now, supported=True, status=ProcessingStatus.PENDING,
        )],
    )


def test_hash_change_is_source_change_not_semantic_change() -> None:
    report = build_source_diff(base=_manifest("old"), head=_manifest("new"))

    assert report.entries[0].kind == "changed"
    assert "semantic" not in report.entries[0].summary.lower()
