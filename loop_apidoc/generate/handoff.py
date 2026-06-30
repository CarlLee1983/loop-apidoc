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


def _base_url_initial(openapi: dict) -> str:
    servers = openapi.get("servers") or []
    return (servers[0].get("url") if servers else None) or "<base_url>"


def _runtime_config_lines(openapi: dict, plan: NormalizationPlan) -> list[str]:
    lines = [f"- [ ] `base_url` — initial value: `{_base_url_initial(openapi)}`"]
    schemes = ((openapi.get("components") or {}).get("securitySchemes") or {})
    for name, scheme in schemes.items():
        kind = scheme.get("type", "")
        where = scheme.get("name") or scheme.get("scheme") or scheme.get("in") or ""
        suffix = f" ({where})" if where else ""
        lines.append(f"- [ ] Auth `{name}` — {kind}{suffix}")
    contract = plan.integration
    if contract is not None:
        for idx, s in enumerate(contract.crypto):
            ks = s.key_source
            if ks and (ks.key or ks.iv):
                parts = [p for p in (ks.key and f"key=`{ks.key}`", ks.iv and f"iv=`{ks.iv}`") if p]
                lines.append(
                    f"- [ ] Secret for `{s.name or idx}` — {', '.join(parts)} "
                    f"(`../integration-contract.json#/crypto/{idx}`)"
                )
    return lines


def _implementation_order_lines(openapi: dict, plan: NormalizationPlan) -> list[str]:
    crypto_labels = _request_signing_labels(plan)
    lines: list[str] = []
    for rec in _iter_operations(openapi):
        oid, _ = _op_identity(rec)
        ident = (
            f"`{oid}` (`{rec['method']} {rec['path']}`)"
            if rec["path"] is not None
            else f"`{oid}` (webhook `{rec['webhook']}` receiver)"
        )
        lines.append(f"- [ ] Implement {ident}")
        lines.append(f"  - Contract: `{_contract_pointer(rec)}`")
        if rec["operation_id"]:
            lines.append(f"  - Example: `../examples/{oid}/request.ts`")
        for label in crypto_labels:
            lines.append(f"  - Requires {label}")
    if not lines:
        lines.append("- No source-grounded operations were found.")
    return lines


def _mechanism_lines(plan: NormalizationPlan) -> list[str]:
    contract = plan.integration
    if contract is None:
        return ["- Integration contract not present for this run."]
    lines: list[str] = []
    for idx, s in enumerate(contract.crypto):
        lines.append(
            f"- [ ] Signing/encryption `{s.name or idx}` "
            f"(`../integration-contract.json#/crypto/{idx}`)"
        )
    for idx, cb in enumerate(contract.callbacks):
        lines.append(
            f"- [ ] Callback `{cb.name or idx}` "
            f"(`../integration-contract.json#/callbacks/{idx}`)"
        )
    for idx, _cond in enumerate(contract.field_conditions):
        lines.append(
            f"- [ ] Field condition #{idx} "
            f"(`../integration-contract.json#/field_conditions/{idx}`)"
        )
    if not lines:
        lines.append(
            "- No source-grounded signing, encryption, callback, condition, or "
            "test-case mechanisms were found."
        )
    return lines


def _blocker_lines(plan: NormalizationPlan, integration: dict | None) -> list[str]:
    lines: list[str] = []
    for m in plan.missing_items:
        lines.append(f"- [ ] Blocked: {m.area} — {m.detail}")
    for c in plan.source_conflicts:
        lines.append(f"- [ ] Conflict: {c.area} — {c.detail}")
    for u in plan.unverified_items:
        lines.append(f"- [ ] Unverified: {u.area} — {u.detail}")
    for gap in (integration or {}).get("missing", []) or []:
        lines.append(f"- [ ] Gap: {gap.get('area')} — {gap.get('detail')}")
    if not lines:
        lines.append("- No outstanding blockers, conflicts, unverified items, or gaps.")
    return lines


def _build_integration_tasks(
    openapi: dict, plan: NormalizationPlan, integration: dict | None
) -> str:
    parts = [
        "# Developer Integration Tasks",
        "",
        "Derived navigation aid — NOT a contract. See `../openapi.yaml` for the schema.",
        "",
        "## Run Context",
        "",
        "- Primary contract: `../openapi.yaml`",
        "- Integration mechanisms: `../integration-contract.json`",
        "- Validation status: `../validation/report.md`",
        "- Request examples: `../examples/README.md`",
        "",
        "## Runtime Configuration",
        "",
        *_runtime_config_lines(openapi, plan),
        "",
        "## Implementation Order",
        "",
        *_implementation_order_lines(openapi, plan),
        "",
        "## Integration Mechanisms",
        "",
        *_mechanism_lines(plan),
        "",
        "## Blockers & Gaps",
        "",
        *_blocker_lines(plan, integration),
    ]
    return "\n".join(parts) + "\n"


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


def _param_value(name: str, node: dict) -> object:
    """Source value only (example / single-enum / const / default); else `<name>`.

    Mirrors examples._resolve_value — never derives a type-based sample, so we
    never emit fabricated "string"/0/true placeholders.
    """
    if isinstance(node, dict) and "example" in node:
        return node["example"]
    schema = node.get("schema") if isinstance(node.get("schema"), dict) else node
    if isinstance(schema, dict):
        if "example" in schema:
            return schema["example"]
        enum = schema.get("enum")
        if isinstance(enum, list) and len(enum) == 1:
            return enum[0]
        if "const" in schema:
            return schema["const"]
        if "default" in schema:
            return schema["default"]
    return f"<{_snake(name)}>"


def _postman_item(rec: dict, plan: NormalizationPlan) -> dict:
    oid, _ = _op_identity(rec)
    op = rec["op"]
    path = rec["path"] or ""
    segments = [seg for seg in path.split("/") if seg]
    headers = []
    query = []
    for raw in op.get("parameters", []) or []:
        loc = raw.get("in")
        value = _param_value(raw.get("name", ""), raw)
        if loc == "header":
            headers.append({"key": raw.get("name"), "value": value})
        elif loc == "query":
            query.append({"key": raw.get("name"), "value": value})
    url = {"raw": "{{base_url}}" + path, "host": ["{{base_url}}"], "path": segments}
    if query:
        url["query"] = query
    request: dict = {"method": rec["method"], "header": headers, "url": url}
    body = (op.get("requestBody") or {}).get("content") or {}
    if body:
        content_type = next(iter(body))
        schema = body[content_type].get("schema", {}) or {}
        fields = {
            pname: _param_value(pname, {"schema": pnode})
            for pname, pnode in (schema.get("properties") or {}).items()
        }
        request["body"] = {
            "mode": "raw",
            "raw": json.dumps(fields, ensure_ascii=False, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    desc_lines = [f"OpenAPI: `{_contract_pointer(rec)}`"]
    if rec["operation_id"]:
        desc_lines.append(f"Example: `../examples/{oid}/request.ts`")
    contract = plan.integration
    if contract is not None and contract.crypto:
        desc_lines.append(
            "Requires signing — see `../integration-contract.json#/crypto/0` "
            "(no pre-request script generated; implement crypto from the contract)."
        )
    return {"name": oid, "request": request, "description": "\n".join(desc_lines)}


def _build_postman_collection(openapi: dict, plan: NormalizationPlan) -> str:
    title = (openapi.get("info") or {}).get("title") or "Untitled API"
    doc = {
        "info": {
            "name": title,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [{"key": "base_url", "value": _base_url_initial(openapi)}],
        "item": [_postman_item(rec, plan) for rec in _iter_operations(openapi)],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def build_handoff(
    openapi: dict, plan: NormalizationPlan, integration: dict | None
) -> dict[str, str]:
    return {
        "handoff/integration-tasks.md": _build_integration_tasks(openapi, plan, integration),
        "handoff/postman_collection.json": _build_postman_collection(openapi, plan),
        "handoff/sdk-hints.json": _build_sdk_hints(openapi, plan),
    }
