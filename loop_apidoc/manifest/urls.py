from __future__ import annotations

import hashlib
from datetime import datetime

import httpx

from loop_apidoc.manifest.models import UrlSource

# Default ceiling on probed URL content. Probing only needs a content hash, so
# we stream and stop once the cap is hit rather than buffering an unbounded
# response into memory.
_MAX_BYTES = 25 * 1024 * 1024  # 25 MiB


def probe_url(
    url: str,
    fetched_at: datetime,
    client: httpx.Client,
    *,
    max_bytes: int = _MAX_BYTES,
) -> UrlSource:
    try:
        with client.stream("GET", url) as response:
            status = response.status_code
            if not response.is_success:
                return UrlSource(
                    url=url,
                    fetched_at=fetched_at,
                    http_status=status,
                    content_sha256=None,
                )

            digest = hashlib.sha256()
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    return UrlSource(
                        url=url,
                        fetched_at=fetched_at,
                        http_status=status,
                        content_sha256=None,
                        note=f"content exceeded {max_bytes} byte cap; not hashed",
                    )
                digest.update(chunk)

            return UrlSource(
                url=url,
                fetched_at=fetched_at,
                http_status=status,
                content_sha256=digest.hexdigest(),
            )
    except httpx.HTTPError as error:
        return UrlSource(
            url=url,
            fetched_at=fetched_at,
            http_status=None,
            content_sha256=None,
            note=f"fetch failed: {error.__class__.__name__}",
        )
