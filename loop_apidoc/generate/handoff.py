from __future__ import annotations

import json
import re
from collections.abc import Iterator

from loop_apidoc.plan.models import NormalizationPlan

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def _esc(s: str) -> str:
    """JSON-pointer escape: ~ -> ~0 then / -> ~1 (order matters)."""
    return s.replace("~", "~0").replace("/", "~1")


def _snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip())
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return re.sub(r"_+", "_", s) or "value"


def _iter_operations(openapi: dict) -> Iterator[dict]:
    for path, item in (openapi.get("paths") or {}).items():
        for method, op in (item or {}).items():
            if method.lower() in _HTTP_METHODS and isinstance(op, dict):
                yield {
                    "operation_id": op.get("operationId"),
                    "method": method.upper(),
                    "path": path,
                    "op": op,
                    "webhook": None,
                }
    for name, item in (openapi.get("webhooks") or {}).items():
        for method, op in (item or {}).items():
            if method.lower() in _HTTP_METHODS and isinstance(op, dict):
                yield {
                    "operation_id": op.get("operationId"),
                    "method": method.upper(),
                    "path": None,
                    "op": op,
                    "webhook": name,
                }


def _op_identity(rec: dict) -> tuple[str, list[str]]:
    """Return (operationId-or-deterministic-fallback, generator_gaps)."""
    oid = rec["operation_id"]
    if oid:
        return oid, []
    base = rec["webhook"] or rec["path"] or "operation"
    fallback = _snake(f"{rec['method']}_{base}")
    return fallback, [
        f"generator: operation {rec['method']} {base} has no operationId; used fallback {fallback}"
    ]


def _contract_pointer(rec: dict) -> str:
    if rec["webhook"] is not None:
        return f"../openapi.yaml#/webhooks/{_esc(rec['webhook'])}/{rec['method'].lower()}"
    return f"../openapi.yaml#/paths/{_esc(rec['path'])}/{rec['method'].lower()}"


def _request_signing_labels(plan: NormalizationPlan) -> list[str]:
    """`crypto:<name>` labels for request/signature-purpose schemes (mirrors examples.py)."""
    contract = plan.integration
    if contract is None:
        return []
    labels: list[str] = []
    for idx, s in enumerate(contract.crypto):
        if s.purpose in (None, "request", "signature"):
            labels.append(f"crypto:{s.name or idx}")
    return labels


def _operation_groups(openapi: dict) -> list[dict]:
    """One group per OpenAPI tag (first-appearance order); untagged ops -> 'Ungrouped'."""
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for rec in _iter_operations(openapi):
        oid, _ = _op_identity(rec)
        tags = rec["op"].get("tags") or ["Ungrouped"]
        for tag in tags:
            if tag not in groups:
                groups[tag] = []
                order.append(tag)
            if oid not in groups[tag]:
                groups[tag].append(oid)
    return [{"name": tag, "operations": groups[tag]} for tag in order]


def _build_sdk_hints(openapi: dict, plan: NormalizationPlan) -> str:
    crypto_labels = _request_signing_labels(plan)
    notes: list[dict] = []
    gaps: list[str] = []
    for rec in _iter_operations(openapi):
        oid, op_gaps = _op_identity(rec)
        gaps.extend(op_gaps)
        notes.append(
            {
                "operation_id": oid,
                "method": rec["method"],
                "path": rec["path"] if rec["path"] is not None else f"webhook:{rec['webhook']}",
                "contract_pointer": _contract_pointer(rec),
                "example_paths": (
                    [f"../examples/{oid}/request.ts"] if rec["operation_id"] else []
                ),
                "requires": ["runtime:base_url", *crypto_labels],
                "gaps": op_gaps,
            }
        )
    doc = {
        "version": "1.0",
        "contracts": {
            "openapi": "../openapi.yaml",
            "integration": "../integration-contract.json",
        },
        "operation_groups": _operation_groups(openapi),
        "implementation_notes": notes,
        "gaps": gaps,
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def build_handoff(
    openapi: dict, plan: NormalizationPlan, integration: dict | None
) -> dict[str, str]:
    return {"handoff/sdk-hints.json": _build_sdk_hints(openapi, plan)}
