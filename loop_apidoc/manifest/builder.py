from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import httpx

from loop_apidoc.manifest.models import Manifest, UrlSource
from loop_apidoc.manifest.scanner import scan_sources
from loop_apidoc.manifest.urls import probe_url


def build_manifest(
    sources_root: Path,
    urls: list[str],
    generated_at: datetime,
    client: httpx.Client | None = None,
    excludes: Sequence[str] = (),
) -> Manifest:
    local_sources = scan_sources(sources_root, scanned_at=generated_at, excludes=excludes)

    url_sources: list[UrlSource] = []
    if urls:
        owns_client = client is None
        active_client = client or httpx.Client(timeout=10.0, follow_redirects=True)
        try:
            url_sources = [
                probe_url(url, fetched_at=generated_at, client=active_client)
                for url in urls
            ]
        finally:
            if owns_client:
                active_client.close()

    return Manifest(
        sources_root=str(sources_root),
        generated_at=generated_at,
        local_sources=local_sources,
        url_sources=url_sources,
    )
