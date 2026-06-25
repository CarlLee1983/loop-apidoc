from __future__ import annotations

import hashlib
from datetime import datetime

import httpx

from loop_apidoc.manifest.models import UrlSource


def probe_url(url: str, fetched_at: datetime, client: httpx.Client) -> UrlSource:
    try:
        response = client.get(url)
    except httpx.HTTPError as error:
        return UrlSource(
            url=url,
            fetched_at=fetched_at,
            http_status=None,
            content_sha256=None,
            note=f"fetch failed: {error.__class__.__name__}",
        )

    content_sha256 = None
    if response.is_success:
        content_sha256 = hashlib.sha256(response.content).hexdigest()

    return UrlSource(
        url=url,
        fetched_at=fetched_at,
        http_status=response.status_code,
        content_sha256=content_sha256,
    )
