from __future__ import annotations

from pathlib import Path

import httpx

from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.manifest.models import ProcessingStatus


def test_build_manifest_combines_local_and_urls(tmp_path: Path, fixed_now):
    (tmp_path / "openapi.yaml").write_text("openapi: 3.1.0", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"doc")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with client:
        manifest = build_manifest(
            sources_root=tmp_path,
            urls=["https://example.com/api"],
            generated_at=fixed_now,
            client=client,
        )

    assert manifest.sources_root == str(tmp_path)
    assert manifest.generated_at == fixed_now
    assert len(manifest.local_sources) == 1
    assert manifest.local_sources[0].status is ProcessingStatus.PENDING
    assert len(manifest.url_sources) == 1
    assert manifest.url_sources[0].http_status == 200


def test_build_manifest_without_urls_needs_no_client(tmp_path: Path, fixed_now):
    (tmp_path / "guide.md").write_text("hi", encoding="utf-8")

    manifest = build_manifest(
        sources_root=tmp_path,
        urls=[],
        generated_at=fixed_now,
    )

    assert manifest.url_sources == []
    assert len(manifest.local_sources) == 1


def test_build_manifest_creates_and_closes_own_client(tmp_path, fixed_now, monkeypatch):
    (tmp_path / "readme.md").write_text("guide", encoding="utf-8")

    closed = {"value": False}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"doc")

    # Create a mock client with tracking close
    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    original_close = mock_client.close

    def tracking_close():
        closed["value"] = True
        original_close()

    mock_client.close = tracking_close

    # Mock the Client constructor to return our tracked client
    monkeypatch.setattr(
        "loop_apidoc.manifest.builder.httpx.Client",
        lambda *args, **kwargs: mock_client,
    )

    manifest = build_manifest(
        sources_root=tmp_path,
        urls=["https://example.com/api"],
        generated_at=fixed_now,
        client=None,
    )

    assert len(manifest.url_sources) == 1
    assert manifest.url_sources[0].http_status == 200
    assert closed["value"] is True
