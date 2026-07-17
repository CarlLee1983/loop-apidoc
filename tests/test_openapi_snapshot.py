from __future__ import annotations

import json
from pathlib import Path

import httpx

from loop_apidoc.openapi_snapshot import snapshot_openapi_url

def test_snapshot_openapi_url_writes_immutable_source_and_coverage(tmp_path: Path):
    source = {
        "openapi": "3.0.4",
        "info": {"title": "Transfer Operator", "version": "1.0"},
        "paths": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept"].startswith("application/json")
        return httpx.Response(
            200,
            json=source,
            headers={"content-type": "application/json"},
        )

    sources = tmp_path / "sources"
    coverage = tmp_path / "work" / "url_sources" / "coverage.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = snapshot_openapi_url(
            "https://spec.example.com/transfer/openapi.json",
            sources=sources,
            coverage_output=coverage,
            client=client,
        )

    snapshot = sources / "openapi.json"
    assert snapshot.is_file()
    assert json.loads(snapshot.read_text(encoding="utf-8")) == source
    assert result.snapshot_path == snapshot
    assert len(result.sha256) == 64
    ledger = json.loads(coverage.read_text(encoding="utf-8"))
    assert ledger == {
        "entry_url": "https://spec.example.com/transfer/openapi.json",
        "confirmed_by_user": False,
        "expected": [{
            "url": "https://spec.example.com/transfer/openapi.json",
            "title": "Transfer Operator",
            "source": "user",
        }],
        "results": [{
            "url": "https://spec.example.com/transfer/openapi.json",
            "status": "fetched",
            "file": "sources/openapi.json",
            "method": "direct",
        }],
    }


def test_snapshot_openapi_url_rejects_non_openapi_without_writing(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"info": {"title": "not a spec"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            snapshot_openapi_url(
                "https://spec.example.com/not-openapi.json",
                sources=tmp_path / "sources",
                coverage_output=tmp_path / "coverage.json",
                client=client,
            )
        except ValueError as exc:
            assert "OpenAPI" in str(exc)
        else:
            raise AssertionError("expected non-OpenAPI document to be rejected")

    assert not (tmp_path / "sources").exists()
    assert not (tmp_path / "coverage.json").exists()
