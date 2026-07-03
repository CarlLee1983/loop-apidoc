from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import UrlSource


def test_url_source_snapshot_file_defaults_none():
    src = UrlSource(url="https://a.example/doc", fetched_at=datetime(2026, 7, 4, tzinfo=timezone.utc), http_status=200)
    assert src.snapshot_file is None


def test_url_source_snapshot_file_roundtrip():
    src = UrlSource(
        url="https://a.example/doc",
        fetched_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
        http_status=200,
        snapshot_file="overview.md",
    )
    assert src.snapshot_file == "overview.md"
    # 舊 JSON(無此欄位)讀回仍為 None
    reloaded = UrlSource.model_validate_json(
        '{"url":"https://a.example/doc","fetched_at":"2026-07-04T00:00:00Z","http_status":200}'
    )
    assert reloaded.snapshot_file is None
