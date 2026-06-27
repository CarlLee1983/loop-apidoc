from __future__ import annotations

import re

from loop_apidoc.plan.models import CryptoScheme, NormalizationPlan

HEADER_NOTE = (
    "Derived from openapi.yaml + integration-contract.json — NOT a source document.\n"
    "Values shown as <placeholder> are not provided by the source; fill them in."
)


def _snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip())
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return re.sub(r"_+", "_", s) or "value"


def _placeholder(name: str) -> str:
    return f"<{_snake(name)}>"


def _resolve_value(name: str, node: dict) -> tuple[str, object]:
    """Source value only when the source/openapi states one; else placeholder.

    Never derives a type-based sample — that would violate the no-fabrication
    invariant.
    """
    if "example" in node:
        return ("source", node["example"])
    schema = node.get("schema") if isinstance(node.get("schema"), dict) else node
    enum = schema.get("enum") if isinstance(schema, dict) else None
    if isinstance(enum, list) and len(enum) == 1:
        return ("source", enum[0])
    if isinstance(schema, dict) and "const" in schema:
        return ("source", schema["const"])
    if isinstance(schema, dict) and "default" in schema:
        return ("source", schema["default"])
    return ("placeholder", _placeholder(name))


def _request_shape(
    operation: dict, servers: list[dict], path: str | None, method: str = "POST"
) -> dict:
    base = (servers[0].get("url") if servers else None) or "<base_url>"
    if path is None:
        url = "<your_receiver_url>"
    else:
        url = f"{base}{path}"
    buckets: dict[str, list] = {"query": [], "header": [], "path": [], "body": []}
    for raw in operation.get("parameters", []) or []:
        loc = raw.get("in")
        if loc not in buckets:
            continue
        kind, value = _resolve_value(raw.get("name", ""), raw)
        buckets[loc].append((raw.get("name"), kind, value))
    content_type = None
    body = operation.get("requestBody", {}).get("content", {}) if operation.get("requestBody") else {}
    if body:
        content_type = next(iter(body))
        schema = body[content_type].get("schema", {})
        for pname, pnode in (schema.get("properties") or {}).items():
            kind, value = _resolve_value(pname, {"schema": pnode})
            buckets["body"].append((pname, kind, value))
    security = [k for req in operation.get("security", []) or [] for k in req]
    return {
        "method": method,
        "url": url,
        "query": buckets["query"],
        "header": buckets["header"],
        "path": buckets["path"],
        "body": buckets["body"],
        "content_type": content_type,
        "security": security,
    }


def _signature_explicit(scheme: CryptoScheme) -> bool:
    return bool(scheme.algorithm) and bool(scheme.payload_assembly)


def _request_signing_schemes(plan: NormalizationPlan) -> list[CryptoScheme]:
    contract = plan.integration
    if contract is None:
        return []
    return [s for s in contract.crypto if s.purpose in (None, "request", "signature")]
