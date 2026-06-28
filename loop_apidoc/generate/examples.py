from __future__ import annotations

import json
import re

from loop_apidoc.plan.models import CryptoScheme, NormalizationPlan

HEADER_NOTE = (
    "Derived from openapi.yaml + integration-contract.json — NOT a source document.\n"
    "Values shown as <placeholder> are not provided by the source; fill them in."
)

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


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
    if isinstance(schema, dict) and "example" in schema:
        return ("source", schema["example"])
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


def _is_json(content_type: str | None) -> bool:
    """True only when the declared content type is JSON.

    Drives a *consistent* body-encoding choice across all three renderers
    (curl / TS / Python): JSON → JSON body everywhere; otherwise form-urlencoded.
    Unknown/absent content type fails to form (the common default for these
    integrations) rather than fabricating a JSON content type.
    """
    if not content_type:
        return False
    return content_type.split(";")[0].strip().lower().endswith("json")


def _interpolate_path(url: str, path_params: list) -> str:
    """Replace `{name}` path placeholders in the URL with their resolved value."""
    for name, _kind, value in path_params:
        url = url.replace("{" + str(name) + "}", str(value))
    return url


def _query_suffix(query: list) -> str:
    if not query:
        return ""
    return "?" + "&".join(f"{name}={value}" for name, _kind, value in query)


def _signature_explicit(scheme: CryptoScheme) -> bool:
    return bool(scheme.algorithm) and bool(scheme.payload_assembly)


def _is_cbc(scheme: CryptoScheme) -> bool:
    """Check if the scheme's mode is confirmed to be CBC.

    Returns True only if:
    - mode field is explicitly "CBC" (case-insensitive), OR
    - mode is None/unset but algorithm string contains "CBC"

    Otherwise returns False (fail-closed: unknown/non-CBC modes are not rendered as runnable code).
    """
    mode = (scheme.mode or "").upper()
    algo = (scheme.algorithm or "").upper()
    if mode:
        return mode == "CBC"
    return "CBC" in algo


_PAYLOAD_NOTE = "簽章 payload：來源指定下列欄位進入簽章（確切串接/排序為示意，請依 payload_assembly 核對 source）"
_PAYLOAD_GAP = "<payload：來源未列出簽章欄位，請依 payload_assembly 組裝>"


def _func_name(scheme: CryptoScheme, idx: int, total: int) -> str:
    """Signature function name; unique per scheme only when more than one exists.
    Mirrors the naming used by _ts_signature / _py_signature."""
    if total > 1:
        return f"sign_{_snake(scheme.name or str(idx))}"
    return "sign"


def _wire_target(scheme: CryptoScheme, shape: dict) -> tuple[str, str] | None:
    """If this runnable scheme's signature value should be written back into the
    request, return (location, field_name); else None.

    location is 'body' or 'header'. Wiring happens only when the scheme is runnable
    (explicit + CBC) AND verify.field names a body field or header present in this
    request — otherwise keep comment-only / gap behavior (no fabrication)."""
    if not (_signature_explicit(scheme) and _is_cbc(scheme)):
        return None
    target = scheme.verify.field if scheme.verify else None
    if not target:
        return None
    if target in [n for n, _k, _v in shape["body"]]:
        return ("body", target)
    if target in [n for n, _k, _v in shape["header"]]:
        return ("header", target)
    return None


def _payload_field_names(scheme: CryptoScheme, shape: dict, target: str) -> list[str]:
    """Body field names the source says enter the signature payload: union of
    payload_assembly[].fields ∩ this request's body fields, excluding the target."""
    body_names = [n for n, _k, _v in shape["body"]]
    names: list[str] = []
    for step in scheme.payload_assembly:
        for f in step.fields:
            if f in body_names and f != target and f not in names:
                names.append(f)
    return names


def _ts_wiring(shape: dict, schemes: list[CryptoScheme]) -> list[str]:
    lines: list[str] = []
    total = len(schemes)
    for idx, s in enumerate(schemes):
        wire = _wire_target(s, shape)
        if wire is None:
            continue
        loc, target = wire
        obj = "body" if loc == "body" else "headers"
        fn = _func_name(s, idx, total)
        pvar = "payload" if total == 1 else f"payload_{_snake(s.name or str(idx))}"
        fields = _payload_field_names(s, shape, target)
        lines.append(f"// {_PAYLOAD_NOTE}")
        if fields:
            arr = ", ".join(json.dumps(f, ensure_ascii=False) for f in fields)
            lines.append(
                f"const {pvar} = [{arr}].map((k) => `${{k}}=${{({obj} as any)[k]}}`).join('&')"
            )
        else:
            lines.append(f"const {pvar} = {json.dumps(_PAYLOAD_GAP, ensure_ascii=False)}")
        lines.append(
            f";({obj} as any)[{json.dumps(target, ensure_ascii=False)}] = {fn}({pvar})"
        )
    return lines


def _py_wiring(shape: dict, schemes: list[CryptoScheme]) -> list[str]:
    lines: list[str] = []
    total = len(schemes)
    for idx, s in enumerate(schemes):
        wire = _wire_target(s, shape)
        if wire is None:
            continue
        loc, target = wire
        obj = "payload" if loc == "body" else "headers"
        fn = _func_name(s, idx, total)
        pvar = "sig_payload" if total == 1 else f"sig_payload_{_snake(s.name or str(idx))}"
        fields = _payload_field_names(s, shape, target)
        lines.append(f"# {_PAYLOAD_NOTE}")
        if fields:
            arr = ", ".join(json.dumps(f, ensure_ascii=False) for f in fields)
            lines.append(f'{pvar} = "&".join(f"{{k}}={{{obj}[k]}}" for k in [{arr}])')
        else:
            lines.append(f"{pvar} = {json.dumps(_PAYLOAD_GAP, ensure_ascii=False)}")
        lines.append(f"{obj}[{json.dumps(target, ensure_ascii=False)}] = {fn}({pvar})")
    return lines


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
    targets = [w[1] for s in schemes if (w := _wire_target(s, shape))]
    if targets:
        parts += [_comment("簽章值請填回欄位：" + ", ".join(targets)), ""]
    url = _interpolate_path(shape["url"], shape["path"]) + _query_suffix(shape["query"])
    # Build line-continuation segments without trailing backslashes, then join —
    # this structurally avoids any dangling ` \` on the final line.
    segments = [f"curl -X {shape['method']} '{url}'"]
    if shape["content_type"]:
        segments.append(f"-H 'Content-Type: {shape['content_type']}'")
    for name, _kind, value in shape["header"]:
        segments.append(f"-H '{name}: {value}'")
    if shape["body"]:
        if _is_json(shape["content_type"]):
            body_obj = {name: value for name, _kind, value in shape["body"]}
            segments.append(f"--data '{json.dumps(body_obj, ensure_ascii=False)}'")
        else:
            for name, _kind, value in shape["body"]:
                segments.append(f"--data-urlencode '{name}={value}'")
    parts.append(" \\\n  ".join(segments))
    return "\n".join(parts) + "\n"


def _ts_value(kind: str, value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _ts_signature(schemes: list[CryptoScheme]) -> str:
    if not schemes:
        return ""

    # Import is only needed when at least one scheme renders runnable CBC code.
    # An explicit-but-non-CBC scheme (e.g. GCM) becomes a gap and uses none of
    # these imports, so it must NOT trigger them — mirroring the Python path.
    has_runnable = any(_signature_explicit(s) and _is_cbc(s) for s in schemes)

    # Determine if we need unique function names (multiple schemes)
    need_unique_names = len(schemes) > 1

    parts = []

    # Emit import exactly once at the top if needed
    if has_runnable:
        parts.append("import { createCipheriv, createHash } from 'node:crypto'\n")

    blocks = []
    for idx, s in enumerate(schemes):
        # Generate unique function name when needed
        if need_unique_names:
            func_name = f"sign_{_snake(s.name or str(idx))}"
        else:
            func_name = "sign"

        if _signature_explicit(s) and _is_cbc(s):
            key = (s.key_source.key if s.key_source else None) or "<hash_key>"
            iv = (s.key_source.iv if s.key_source else None) or "<hash_iv>"
            algo = (s.algorithm or "").lower()
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
            # If explicit but not CBC, the gap is the unsupported crypto mode —
            # GCM etc. need auth-tag/AAD handling this template can't fabricate.
            if _signature_explicit(s) and not _is_cbc(s):
                mode = (s.mode or "").upper() or "unspecified"
                blocks.append(
                    f"// gap: 簽章 {s.name or ''} 聲明為 {mode} 模式，但本範例僅支援 CBC；無法生成可跑函式\n"
                    f"function {func_name}(payload: string): string {{\n"
                    "  throw new Error('來源聲明的加密模式不支援，請參考 integration-contract.json 手動實作')\n"
                    "}\n"
                )
            else:
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
    url = _interpolate_path(shape["url"], shape["path"])
    lines = [f"const url = {_ts_value('source', url)}"]

    if shape["query"]:
        entries = ", ".join(
            f"{_ts_value('s', name)}: {_ts_value(kind, value)}"
            for name, kind, value in shape["query"]
        )
        lines.append("const params = new URLSearchParams({ " + entries + " })")

    header_entries = []
    if shape["content_type"]:
        header_entries.append(f"'Content-Type': {_ts_value('s', shape['content_type'])}")
    for name, kind, value in shape["header"]:
        header_entries.append(f"{_ts_value('s', name)}: {_ts_value(kind, value)}")
    if header_entries:
        lines.append("const headers = { " + ", ".join(header_entries) + " }")

    if shape["body"]:
        # Quote the *original* field name (e.g. "MerchantID") — snake-casing it
        # would put a wrong, API-unrecognised key on the wire.
        body_lines = "\n".join(
            f"  {_ts_value('s', name)}: {_ts_value(kind, value)},"
            for name, kind, value in shape["body"]
        )
        lines.append("const body = {\n" + body_lines + "\n}")

    lines += _ts_wiring(shape, schemes)
    target = "url + '?' + params" if shape["query"] else "url"
    opts = [f"  method: '{shape['method']}',"]
    if header_entries:
        opts.append("  headers,")
    if shape["body"]:
        encoded = "JSON.stringify(body)" if _is_json(shape["content_type"]) else "new URLSearchParams(body)"
        opts.append(f"  body: {encoded},")
    lines.append(
        f"const res = await fetch({target}, {{\n" + "\n".join(opts) + "\n})"
    )
    lines.append("console.log(await res.text())")
    parts.append("\n".join(lines) + "\n")
    return "\n".join(parts) + "\n"


def _py_signature(schemes: list[CryptoScheme]) -> str:
    if not schemes:
        return ""

    # Import is only needed when at least one scheme renders runnable CBC code.
    # An explicit-but-non-CBC scheme (e.g. GCM) becomes a gap and uses none of
    # these imports, so it must NOT trigger them.
    has_runnable = any(_signature_explicit(s) and _is_cbc(s) for s in schemes)

    # Determine if we need unique function names (multiple schemes)
    need_unique_names = len(schemes) > 1

    parts = []

    # Emit imports exactly once at the top if needed
    if has_runnable:
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

        if _signature_explicit(s) and _is_cbc(s):
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
            # If explicit but not CBC, replace "mode" in missing with a note about the crypto mode
            if _signature_explicit(s) and not _is_cbc(s):
                mode = (s.mode or "").upper() or "unspecified"
                blocks.append(
                    f"# gap: 簽章 {s.name or ''} 聲明為 {mode} 模式，但本範例僅支援 CBC；無法生成可跑函式\n"
                    f"def {func_name}(payload: str) -> str:\n"
                    "    raise NotImplementedError('來源聲明的加密模式不支援，請參考 integration-contract.json 手動實作')\n"
                )
            else:
                blocks.append(
                    f"# gap: 簽章 {s.name or ''} 來源未提供 {', '.join(missing)}；無法生成可跑函式\n"
                    f"def {func_name}(payload: str) -> str:\n"
                    "    raise NotImplementedError('來源未提供完整簽章演算法，請依文件補完')\n"
                )

    if has_runnable:
        parts.append("\n")
    parts.append("\n".join(blocks))
    return "".join(parts)


def _py_dict(var: str, fields: list) -> str:
    body = "\n".join(
        f"    {json.dumps(name, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)},"
        for name, _kind, value in fields
    )
    return f"{var} = {{\n{body}\n}}"


def _render_py(shape: dict, schemes: list[CryptoScheme]) -> str:
    parts = [_comment(HEADER_NOTE), "", "import httpx", ""]
    sig = _py_signature(schemes)
    if sig:
        parts += [sig, ""]
    url = _interpolate_path(shape["url"], shape["path"])
    lines = [f"url = {json.dumps(url, ensure_ascii=False)}"]
    call_args = ["url"]
    if shape["query"]:
        lines.append(_py_dict("params", shape["query"]))
        call_args.append("params=params")
    if shape["header"]:
        lines.append(_py_dict("headers", shape["header"]))
        call_args.append("headers=headers")
    if shape["body"]:
        lines.append(_py_dict("payload", shape["body"]))
        call_args.append("json=payload" if _is_json(shape["content_type"]) else "data=payload")
    lines += _py_wiring(shape, schemes)
    lines.append(
        f"resp = httpx.request({json.dumps(shape['method'])}, " + ", ".join(call_args) + ")"
    )
    lines.append("print(resp.text)")
    parts.append("\n".join(lines))
    return "\n".join(parts) + "\n"


def _render_readme(operation_ids: list[str], schemes: list[CryptoScheme]) -> str:
    lines = [
        "# 請求範例（examples/）",
        "",
        HEADER_NOTE,
        "",
        "每個端點一資料夾，含 curl / TypeScript / Python 三語版本。",
        "`<...>` 為來源未提供的值，請自行填入。簽章值請先跑 request.py / request.ts 取得。",
        "",
        "## 端點",
    ]
    lines += [f"- `{oid}/`" for oid in operation_ids]
    if schemes:
        lines += ["", "## 通用簽章機制"]
        for s in schemes:
            lines.append(f"- {s.name or 'signature'}：{s.algorithm or '<來源未指明演算法>'}")
    return "\n".join(lines) + "\n"


def _iter_operations(openapi: dict):
    for path, item in (openapi.get("paths") or {}).items():
        for method, op in item.items():
            if method.lower() in _HTTP_METHODS and isinstance(op, dict):
                yield op.get("operationId"), method.upper(), path, op
    for _name, item in (openapi.get("webhooks") or {}).items():
        for method, op in item.items():
            if method.lower() in _HTTP_METHODS and isinstance(op, dict):
                yield op.get("operationId"), method.upper(), None, op


def build_examples(openapi: dict, plan: NormalizationPlan) -> dict[str, str]:
    servers = openapi.get("servers") or []
    schemes = _request_signing_schemes(plan)
    out: dict[str, str] = {}
    operation_ids: list[str] = []
    for operation_id, method, path, op in _iter_operations(openapi):
        if not operation_id:
            continue
        operation_ids.append(operation_id)
        shape = _request_shape(op, servers, path, method)
        base = f"examples/{operation_id}"
        out[f"{base}/request.sh"] = _render_curl(shape, schemes)
        out[f"{base}/request.ts"] = _render_ts(shape, schemes)
        out[f"{base}/request.py"] = _render_py(shape, schemes)
    if not out:
        return {}
    out["examples/README.md"] = _render_readme(operation_ids, schemes)
    return out
