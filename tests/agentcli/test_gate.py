from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.agentcli.gate import check_extraction
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)

_AT = datetime(2026, 7, 9, tzinfo=timezone.utc)


def _local(path: str) -> LocalSource:
    return LocalSource(
        relative_path=path,
        mime_type="application/pdf",
        source_format=SourceFormat.PDF,
        size_bytes=1,
        sha256="a" * 64,
        scanned_at=_AT,
        supported=True,
        status=ProcessingStatus.PENDING,
    )


def _manifest(*paths: str) -> Manifest:
    return Manifest(
        sources_root="/s", generated_at=_AT,
        local_sources=[_local(p) for p in paths],
    )


def test_clean_input_has_no_violations():
    manifest = _manifest("a.pdf", "b.pdf")
    inventory = {"endpoints": [{"method": "GET", "path": "/ping",
                                "source": "a.pdf p.1"}]}
    endpoints = [("ep0.json", {"method": "GET", "path": "/ping",
                               "source": "a.pdf p.1"})]

    assert check_extraction(inventory, endpoints, None, manifest) == []


def test_violations_from_two_layers_are_reported_together():
    """一份輸入同時違反 source_guard(path 未以 / 開頭)與 cross_file
    (端點檔不在 inventory)→ 兩層的違規都要出現,不是遇到第一層就停。"""
    manifest = _manifest("a.pdf", "b.pdf")
    inventory = {"endpoints": [{"method": "GET", "path": "api/ping",
                                "source": "a.pdf p.1"}]}
    endpoints = [("ep0.json", {"method": "GET", "path": "/pong",
                               "source": "a.pdf p.1"})]

    violations = check_extraction(inventory, endpoints, None, manifest)

    assert any("endpoints[0].path" in v for v in violations)   # source_guard 層
    assert any("GET /pong" in v for v in violations)            # cross_file 層
