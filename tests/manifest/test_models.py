from __future__ import annotations

import json
from datetime import datetime, timezone

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
)


def _local(path: str, status: ProcessingStatus) -> LocalSource:
    return LocalSource(
        relative_path=path,
        mime_type="text/markdown",
        source_format=SourceFormat.MARKDOWN,
        size_bytes=4,
        sha256="abc",
        scanned_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        supported=status is not ProcessingStatus.UNSUPPORTED,
        status=status,
    )


def test_manifest_json_round_trip():
    manifest = Manifest(
        sources_root="/sources",
        generated_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        local_sources=[_local("a.md", ProcessingStatus.PENDING)],
        url_sources=[
            UrlSource(
                url="https://example.com/api",
                fetched_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
                http_status=200,
                content_sha256="deadbeef",
            )
        ],
    )

    payload = manifest.model_dump_json()
    restored = Manifest.model_validate_json(payload)

    assert restored == manifest
    assert json.loads(payload)["local_sources"][0]["status"] == "pending"


def test_manifest_helpers_filter_by_status():
    manifest = Manifest(
        sources_root="/sources",
        generated_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        local_sources=[
            _local("a.md", ProcessingStatus.PENDING),
            _local("b.md", ProcessingStatus.DUPLICATE),
            _local("notes.txt", ProcessingStatus.UNSUPPORTED),
        ],
    )

    assert [s.relative_path for s in manifest.unsupported()] == ["notes.txt"]
    assert [s.relative_path for s in manifest.duplicates()] == ["b.md"]
