from __future__ import annotations

import re

_BAD = re.compile(r"[^A-Za-z0-9._-]+")


def component_key(name: str | None, idx: int, *, prefix: str = "item") -> str:
    """Sanitize any name into a valid OpenAPI component key (^[A-Za-z0-9._-]+$).
    Used for securitySchemes and schemas, whose names from the sources may carry
    spaces/parens/CJK that are illegal as component keys."""
    key = _BAD.sub("_", (name or "").strip()).strip("_")
    return key or f"{prefix}{idx}"


def schema_key_map(schemas) -> dict[int, str]:
    """Map each plan.schemas index to a UNIQUE OpenAPI component key.

    Two different source names can sanitize to the same key (e.g. both
    '取消授權回應參數（Result）' and '請退款回應參數（Result）' → 'Result'); without
    dedup one schema silently overwrites the other in components.schemas and
    loses its provenance alignment. The OpenAPI builder, the provenance map and
    `$ref` resolution all read this single helper so they agree on one identifier
    per schema."""
    used: set[str] = set()
    out: dict[int, str] = {}
    for idx, entry in enumerate(schemas):
        base = component_key(entry.name, idx, prefix="schema")
        key = base
        suffix = 2
        while key in used:
            key = f"{base}_{suffix}"
            suffix += 1
        used.add(key)
        out[idx] = key
    return out


def webhook_name(summary: str | None, idx: int) -> str:
    """Derive a webhook key from an endpoint summary, taking the leading label
    before the first qualifier or clause boundary — a parenthesis, newline,
    sentence end ('. '/'。') or colon (': '/'：'). e.g. '付款結果通知（綠界 POST…）'
    → '付款結果通知', and 'push webhook event. Sent when…' → 'push webhook event'.

    A whole-paragraph summary (common when one docs page lists many events as
    prose, e.g. GitHub/Stripe) must not become a giant webhook key, so the
    earliest boundary wins. Falls back to webhook<idx> when there is no usable
    summary. Unlike component keys, OpenAPI webhook keys may be any string, so the
    label is kept verbatim (CJK allowed)."""
    raw = (summary or "").strip()
    cut = min(
        (pos for pos in (raw.find(sep) for sep in ("(", "（", "\n", ". ", "。", ": ", "："))
         if pos > 0),
        default=-1,
    )
    if cut > 0:
        raw = raw[:cut].strip()
    return raw or f"webhook{idx}"


def webhook_items(plan) -> list[tuple[str, object]]:
    """Return [(name, endpoint)] for webhook endpoints — those with an HTTP
    method but no path (async callbacks delivered to a caller-defined URL).
    Names are deterministic and de-duplicated, so the OpenAPI builder, the
    Markdown writer and the provenance map all agree on the same identifier."""
    items: list[tuple[str, object]] = []
    counts: dict[str, int] = {}
    for endpoint in plan.endpoints:
        if endpoint.path or not endpoint.method:
            continue
        base = webhook_name(endpoint.summary, len(items))
        seen = counts.get(base, 0)
        name = f"{base}{seen + 1}" if seen else base
        counts[base] = seen + 1
        items.append((name, endpoint))
    return items


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
