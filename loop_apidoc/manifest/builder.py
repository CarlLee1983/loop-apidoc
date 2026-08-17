from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import httpx

from loop_apidoc.manifest.models import Manifest, UrlSource
from loop_apidoc.manifest.scanner import ManifestScanError, scan_sources
from loop_apidoc.manifest.urls import probe_url
from loop_apidoc.preparation.coverage import UrlCoverage
from loop_apidoc.rendered_url import canonicalize_url, verified_rendered_url_sources


class ManifestInputError(ManifestScanError):
    """Manifest URL evidence is malformed or internally inconsistent."""


def build_manifest(
    sources_root: Path,
    urls: list[str],
    generated_at: datetime,
    client: httpx.Client | None = None,
    excludes: Sequence[str] = (),
    url_coverage: UrlCoverage | None = None,
) -> Manifest:
    local_sources = scan_sources(sources_root, scanned_at=generated_at, excludes=excludes)

    url_sources: list[UrlSource] = []
    if urls:
        try:
            rendered = (
                verified_rendered_url_sources(
                    sources_root=sources_root,
                    urls=urls,
                    coverage=url_coverage,
                    local_sources=local_sources,
                )
                if url_coverage is not None
                else {}
            )
        except ValueError as exc:
            raise ManifestInputError(str(exc)) from exc
        urls_to_probe = [
            url
            for url in urls
            if url_coverage is None or canonicalize_url(url) not in rendered
        ]
        owns_client = client is None
        probed: dict[str, UrlSource] = {}
        if urls_to_probe:
            active_client = client or httpx.Client(timeout=10.0, follow_redirects=True)
            try:
                probed = {
                    url: probe_url(url, fetched_at=generated_at, client=active_client)
                    for url in urls_to_probe
                }
            finally:
                if owns_client:
                    active_client.close()
        url_sources = [
            (
                rendered.get(canonicalize_url(url))
                if url_coverage is not None
                else None
            )
            or probed[url]
            for url in urls
        ]

    return Manifest(
        sources_root=str(sources_root),
        generated_at=generated_at,
        local_sources=local_sources,
        url_sources=url_sources,
    )
