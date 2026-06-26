from __future__ import annotations

import hashlib

import httpx

from loop_apidoc.manifest.urls import probe_url


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_probe_url_success_records_status_and_hash(fixed_now):
    body = b"hello world"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    with _client(handler) as client:
        result = probe_url("https://example.com/api", fetched_at=fixed_now, client=client)

    assert result.url == "https://example.com/api"
    assert result.http_status == 200
    assert result.content_sha256 == hashlib.sha256(body).hexdigest()
    assert result.fetched_at == fixed_now
    assert result.note is None


def test_probe_url_caps_oversized_content(fixed_now):
    big = b"x" * 4096

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    with _client(handler) as client:
        result = probe_url(
            "https://example.com/huge", fetched_at=fixed_now,
            client=client, max_bytes=1024,
        )

    # Over the cap: not hashed, and the truncation is recorded in the note.
    assert result.http_status == 200
    assert result.content_sha256 is None
    assert result.note is not None
    assert "cap" in result.note.lower()


def test_probe_url_under_cap_hashes_normally(fixed_now):
    body = b"small body"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    with _client(handler) as client:
        result = probe_url(
            "https://example.com/ok", fetched_at=fixed_now,
            client=client, max_bytes=1024,
        )

    assert result.content_sha256 == hashlib.sha256(body).hexdigest()
    assert result.note is None


def test_probe_url_non_success_has_no_hash(fixed_now):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with _client(handler) as client:
        result = probe_url("https://example.com/missing", fetched_at=fixed_now, client=client)

    assert result.http_status == 404
    assert result.content_sha256 is None


def test_probe_url_network_error_records_note(fixed_now):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with _client(handler) as client:
        result = probe_url("https://example.com/down", fetched_at=fixed_now, client=client)

    assert result.http_status is None
    assert result.content_sha256 is None
    assert result.note is not None
    assert "ConnectError" in result.note
