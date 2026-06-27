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


def _ts_value(kind: str, value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _ts_signature(schemes: list[CryptoScheme]) -> str:
    if not schemes:
        return ""

    # Determine if we need the import (at least one explicit scheme)
    has_explicit = any(_signature_explicit(s) for s in schemes)

    # Determine if we need unique function names (multiple schemes)
    need_unique_names = len(schemes) > 1

    parts = []

    # Emit import exactly once at the top if needed
    if has_explicit:
        parts.append("import { createCipheriv, createHash } from 'node:crypto'\n")

    blocks = []
    for idx, s in enumerate(schemes):
        # Generate unique function name when needed
        if need_unique_names:
            func_name = f"sign_{_snake(s.name or str(idx))}"
        else:
            func_name = "sign"

        if _signature_explicit(s):
            key = (s.key_source.key if s.key_source else None) or "<hash_key>"
            iv = (s.key_source.iv if s.key_source else None) or "<hash_iv>"
            algo = s.algorithm.lower()
            blocks.append(
                f"// 簽章 {s.name or ''}：{s.algorithm}\n"
                f"function {func_name}(payload: string): string {{\n"
                f"  const key = process.env.{_snake(key).upper()} ?? '{key}'\n"
                f"  const iv = process.env.{_snake(iv).upper()} ?? '{iv}'\n"
                f"  const cipher = createCipheriv('{algo}', key, iv)\n"
                "  const enc = cipher.update(payload, 'utf8', 'hex') + cipher.final('hex')\n"
                "  return createHash('sha256').update(enc).digest('hex').toUpperCase()\n"
                "}\n"
            )
        else:
            missing = [f for f in ("algorithm", "mode", "payload_assembly") if not getattr(s, f, None)]
            blocks.append(
                f"// gap: 簽章 {s.name or ''} 來源未提供 {', '.join(missing)}；無法生成可跑函式\n"
                f"function {func_name}(payload: string): string {{\n"
                "  throw new Error('來源未提供完整簽章演算法，請依文件補完')\n"
                "}\n"
            )

    parts.append("\n".join(blocks))
    return "".join(parts)


def _render_ts(shape: dict, schemes: list[CryptoScheme]) -> str:
    parts = [_comment(HEADER_NOTE, prefix="// "), ""]
    sig = _ts_signature(schemes)
    if sig:
        parts += [sig, ""]
    fields = shape["body"] or shape["query"]
    body_lines = "\n".join(
        f"  {_snake(name)}: {_ts_value(kind, value)}," for name, kind, value in fields
    )
    parts.append(
        f"const url = {_ts_value('source', shape['url'])}\n"
        "const body = {\n" + body_lines + "\n}\n\n"
        f"const res = await fetch(url, {{\n"
        f"  method: '{shape['method']}',\n"
        f"  headers: {{ 'Content-Type': '{shape['content_type'] or 'application/json'}' }},\n"
        "  body: JSON.stringify(body),\n"
        "})\n"
        "console.log(await res.text())\n"
    )
    return "\n".join(parts) + "\n"


def _py_signature(schemes: list[CryptoScheme]) -> str:
    if not schemes:
        return ""

    # Determine if we need the import (at least one explicit scheme)
    has_explicit = any(_signature_explicit(s) for s in schemes)

    # Determine if we need unique function names (multiple schemes)
    need_unique_names = len(schemes) > 1

    parts = []

    # Emit imports exactly once at the top if needed
    if has_explicit:
        parts.append(
            "import hashlib\nimport os\n"
            "from Crypto.Cipher import AES  # pip install pycryptodome\n"
            "from Crypto.Util.Padding import pad\n"
        )

    blocks = []
    for idx, s in enumerate(schemes):
        # Generate unique function name when needed
        if need_unique_names:
            func_name = f"sign_{_snake(s.name or str(idx))}"
        else:
            func_name = "sign"

        if _signature_explicit(s):
            key = (s.key_source.key if s.key_source else None) or "<hash_key>"
            iv = (s.key_source.iv if s.key_source else None) or "<hash_iv>"
            blocks.append(
                f"# 簽章 {s.name or ''}：{s.algorithm}\n"
                f"def {func_name}(payload: str) -> str:\n"
                f"    key = os.environ.get('{_snake(key).upper()}', '{key}').encode()\n"
                f"    iv = os.environ.get('{_snake(iv).upper()}', '{iv}').encode()\n"
                "    cipher = AES.new(key, AES.MODE_CBC, iv)\n"
                "    enc = cipher.encrypt(pad(payload.encode(), 16)).hex()\n"
                "    return hashlib.sha256(enc.encode()).hexdigest().upper()\n"
            )
        else:
            missing = [f for f in ("algorithm", "mode", "payload_assembly") if not getattr(s, f, None)]
            blocks.append(
                f"# gap: 簽章 {s.name or ''} 來源未提供 {', '.join(missing)}；無法生成可跑函式\n"
                f"def {func_name}(payload: str) -> str:\n"
                "    raise NotImplementedError('來源未提供完整簽章演算法，請依文件補完')\n"
            )

    if has_explicit:
        parts.append("\n")
    parts.append("\n".join(blocks))
    return "".join(parts)


def _render_py(shape: dict, schemes: list[CryptoScheme]) -> str:
    import json

    parts = [_comment(HEADER_NOTE), "", "import httpx", ""]
    sig = _py_signature(schemes)
    if sig:
        parts += [sig, ""]
    fields = shape["body"] or shape["query"]
    body_lines = "\n".join(
        f"    {json.dumps(name, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)},"
        for name, _kind, value in fields
    )
    parts.append(
        f"url = {json.dumps(shape['url'], ensure_ascii=False)}\n"
        "payload = {\n" + body_lines + "\n}\n\n"
        f"resp = httpx.request({json.dumps(shape['method'])}, url, "
        + ("json=payload)" if (shape["content_type"] or "").endswith("json") else "data=payload)")
        + "\nprint(resp.text)\n"
    )
    return "\n".join(parts) + "\n"
