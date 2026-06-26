from __future__ import annotations

import re

_BAD = re.compile(r"[^A-Za-z0-9._-]+")


def component_key(name: str | None, idx: int, *, prefix: str = "item") -> str:
    """Sanitize any name into a valid OpenAPI component key (^[A-Za-z0-9._-]+$).
    Used for securitySchemes and schemas, whose names from the sources may carry
    spaces/parens/CJK that are illegal as component keys."""
    key = _BAD.sub("_", (name or "").strip()).strip("_")
    return key or f"{prefix}{idx}"


def security_scheme_key(name: str | None, idx: int) -> str:
    """Sanitize a security-scheme name into a valid OpenAPI component key
    (must match ^[A-Za-z0-9._-]+$).

    NotebookLM names schemes with spaces/parens/slashes ("AES256 Encryption
    (TradeInfo)"), which are illegal as component keys. The same key must be used
    by the OpenAPI writer, the Markdown writer and the provenance map so the
    consistency check still sees one identifier — hence this single deterministic
    helper. The human-readable original name is preserved in descriptions, not
    discarded.
    """
    return component_key(name, idx, prefix="scheme")
