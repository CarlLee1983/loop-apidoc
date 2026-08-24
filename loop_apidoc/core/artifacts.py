from __future__ import annotations

import hashlib
import json

from loop_apidoc.domain.projections import Projection


def projection_content_address(projections: tuple[Projection, ...]) -> str:
    """Return a stable address for exactly the compiled artifact bytes."""

    payload = sorted(
        (
            {
                "name": projection.name,
                "version": projection.version,
                "media_type": projection.media_type,
                "content_digest": hashlib.sha256(projection.content).hexdigest(),
            }
            for projection in projections
        ),
        key=lambda item: (
            item["name"],
            item["version"],
            item["media_type"],
            item["content_digest"],
        ),
    )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
