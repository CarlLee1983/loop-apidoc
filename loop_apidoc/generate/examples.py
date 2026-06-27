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


def _comment(text: str, prefix: str = "# ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.split("\n"))


def _signature_comment_steps(schemes: list[CryptoScheme]) -> str:
    if not schemes:
        return ""
    lines = ["# 簽章步驟（shell 無法內嵌加密，請先跑 request.py / request.ts 取得簽章值）"]
    for s in schemes:
        algo = s.algorithm or "<來源未指明演算法>"
        lines.append(f"#   {s.name or 'signature'}：{algo}")
        for step in s.payload_assembly:
            step_num = "-" if step.step is None else step.step
            lines.append(f"#     {step_num}. {step.desc or '<來源未說明>'}")
    return "\n".join(lines)


def _render_curl(shape: dict, schemes: list[CryptoScheme]) -> str:
    parts = [_comment(HEADER_NOTE), ""]
    sig = _signature_comment_steps(schemes)
    if sig:
        parts += [sig, ""]
    data_fields = shape["body"] or shape["query"]
    lines = [f"curl -X {shape['method']} '{shape['url']}' \\"]
    if shape["content_type"]:
        lines.append(f"  -H 'Content-Type: {shape['content_type']}' \\")
    for name, _kind, value in shape["header"]:
        lines.append(f"  -H '{name}: {value}' \\")
    for i, (name, _kind, value) in enumerate(data_fields):
        tail = "" if i == len(data_fields) - 1 else " \\"
        lines.append(f"  --data-urlencode '{name}={value}'{tail}")
    # Remove trailing backslash from final line if no data fields
    if lines:
        lines[-1] = lines[-1].rstrip(" \\")
    parts.append("\n".join(lines))
    return "\n".join(parts) + "\n"
