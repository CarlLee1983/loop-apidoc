from __future__ import annotations

import re

from loop_apidoc.generate.naming import (
    component_key,
    schema_key_map,
    security_scheme_key,
    webhook_items,
)
from loop_apidoc.plan.models import NormalizationPlan

MISSING_STATUS = "missing-source"
X_LOOP_STATUS = "x-loop-status"

# Valid OpenAPI response keys are HTTP status codes (or ranges like 4XX) or
# "default". APIs that always return 200 and signal outcome via a body field give
# descriptive "statuses" instead — those get folded into a 200 response.
_HTTP_STATUS_RE = re.compile(r"^([1-5][0-9]{2}|[1-5]XX)$")


def _status_key(status: str) -> str | None:
    s = status.strip()
    if s.lower() == "default":
        return "default"
    upper = s.upper()
    return upper if _HTTP_STATUS_RE.match(upper) else None

_OPENAPI_SECURITY_TYPES = {"apiKey", "http", "oauth2", "openIdConnect", "mutualTLS"}
_APIKEY_LOCATIONS = {"header", "query", "cookie"}


_JSON_SCHEMA_TYPES = {
    "string", "integer", "number", "boolean", "object", "array", "null",
}
_TYPE_ALIASES = {
    "str": "string", "text": "string", "varchar": "string", "char": "string",
    "int": "integer", "long": "integer",
    "float": "number", "double": "number", "decimal": "number", "numeric": "number",
    "bool": "boolean", "obj": "object", "list": "array",
}


def _normalize_type(raw: str) -> dict:
    """Map a free-form source type ("String(15)") to a VALID JSON-Schema fragment.
    An invalid `type` value fails OpenAPI validation, so unknown hints keep the
    raw text only as a description (non-speculative)."""
    token = re.match(r"[A-Za-z]+", raw.strip())
    base = token.group(0).lower() if token else ""
    mapped = base if base in _JSON_SCHEMA_TYPES else _TYPE_ALIASES.get(base)
    schema: dict = {}
    if mapped:
        schema["type"] = mapped
    if raw.strip() and raw.strip().lower() != mapped:
        schema["description"] = raw.strip()
    return schema


def _schema_from_type(value) -> dict | None:
    """Tolerant mapping of a free-form type hint to a JSON-Schema fragment."""
    if isinstance(value, dict):
        out = dict(value)
        t = out.get("type")
        if isinstance(t, str) and t.lower() not in _JSON_SCHEMA_TYPES:
            out.pop("type", None)
            out.update(_normalize_type(t))
        return out
    if isinstance(value, str) and value.strip():
        return _normalize_type(value)
    return None


def _build_info(plan: NormalizationPlan) -> dict:
    title = plan.resolved_title
    version = plan.resolved_version
    info: dict = {"title": title or "Untitled API", "version": version or "0.0.0"}
    if not title or not version:
        info[X_LOOP_STATUS] = MISSING_STATUS
    return info


def _build_servers(plan: NormalizationPlan) -> list[dict]:
    servers: list[dict] = []
    for env in plan.environments:
        if not env.base_url:
            continue
        entry: dict = {"url": env.base_url}
        if env.name:
            entry["description"] = env.name
        servers.append(entry)
    return servers


def _build_security_scheme(scheme) -> dict:
    raw = (scheme.type or "").strip()
    if raw in _OPENAPI_SECURITY_TYPES:
        out: dict = {"type": raw}
        if raw == "apiKey":
            location = scheme.location if scheme.location in _APIKEY_LOCATIONS else "header"
            out["in"] = location
            out["name"] = scheme.details or "Authorization"
            return out
        if raw == "http":
            # OpenAPI `http` requires a `scheme` (bearer/basic/...). The contract
            # has no dedicated field, so derive it from the details/name text. If
            # neither is present the type cannot be completed into valid OpenAPI,
            # so fall through to the missing-source apiKey placeholder rather than
            # emitting an invalid `{"type": "http"}` with no scheme.
            hint = f"{scheme.details or ''} {scheme.name or ''}".lower()
            if "bearer" in hint:
                out["scheme"] = "bearer"
                return out
            if "basic" in hint:
                out["scheme"] = "basic"
                return out
        else:
            return out
    # Unmapped source type: this is not a standard OpenAPI auth scheme (e.g. a
    # request-signing / body-encryption procedure). Emit a minimal legal apiKey
    # PLACEHOLDER flagged missing-source. The real header/param name is not
    # source-stated, so `name` stays a neutral placeholder and the procedure text
    # (identity + kind + algorithm) is preserved in `description` — never stuffed
    # into `name` (which must be a param name, not a paragraph).
    location = scheme.location if scheme.location in _APIKEY_LOCATIONS else "header"
    out = {
        "type": "apiKey",
        "in": location,
        "name": "unknown",
        X_LOOP_STATUS: MISSING_STATUS,
    }
    description = scheme.name or ""
    if raw:
        description = f"{description}（{raw}）" if description else f"（{raw}）"
    if scheme.details:
        description = f"{description}：{scheme.details}" if description else scheme.details
    if description:
        out["description"] = description
    return out


def _build_security_schemes(plan: NormalizationPlan) -> dict:
    out: dict = {}
    for idx, scheme in enumerate(plan.security_schemes):
        key = security_scheme_key(scheme.name, idx)
        built = _build_security_scheme(scheme)
        # Preserve the original human name (which may be an illegal key) so it
        # isn't lost when the key is sanitized.
        if scheme.name and scheme.name != key and "description" not in built:
            built["description"] = scheme.name
        out[key] = built
    return out


_PARAMETER_LOCATIONS = {"query", "path", "header", "cookie"}


def _build_parameter(raw: dict) -> dict | None:
    name = raw.get("name")
    if not name:
        return None
    location = raw.get("in") or raw.get("location") or "query"
    if location not in _PARAMETER_LOCATIONS:
        location = "query"
    param: dict = {"name": name, "in": location}
    if location == "path":
        param["required"] = True
    elif "required" in raw:
        param["required"] = bool(raw["required"])
    # A parameter object is invalid without `schema` (or content). When the
    # source type can't be mapped (e.g. "String(15)"), use an empty schema —
    # valid and non-speculative — rather than omitting it.
    schema = _schema_from_type(raw.get("type") if "type" in raw else raw.get("schema"))
    param["schema"] = schema or {}
    if raw.get("description"):
        param["description"] = raw["description"]
    return param


# A media-type key must be a valid `type/subtype`; sources often append a human
# note ("application/json (UTF-8)") or carry parameters ("…; charset=utf-8").
# Keep only the leading `type/subtype` token; the note already survives elsewhere
# (e.g. requestBody prose), so nothing source-stated is lost.
_MEDIA_TYPE_RE = re.compile(r"[\w.+-]+/[\w.+-]+")


def _normalize_media_type(raw: str | None) -> str:
    if raw:
        match = _MEDIA_TYPE_RE.match(raw.strip())
        if match:
            return match.group(0)
    return "application/json"


def _union_schema(field: dict, name_to_key: dict[str, str]) -> dict | None:
    """A native OpenAPI `oneOf` (+ optional `discriminator`) for a field the source
    documents as a union of already-named member schemas. Returns None unless the
    field carries a truthy `one_of` that resolves to at least one named schema — a
    dangling `$ref` is never invented (same rule as response `schema_ref`)."""
    one_of = field.get("one_of")
    if not one_of:
        return None
    members = [
        {"$ref": f"#/components/schemas/{name_to_key[name]}"}
        for name in one_of
        if name in name_to_key
    ]
    if not members:
        return None
    result: dict = {"oneOf": members}
    if field.get("description"):
        result["description"] = field["description"]
    disc = field.get("discriminator")
    if isinstance(disc, dict) and disc.get("property_name"):
        built: dict = {"propertyName": disc["property_name"]}
        mapping = disc.get("mapping")
        if isinstance(mapping, dict):
            resolved = {
                value: f"#/components/schemas/{name_to_key[target]}"
                for value, target in mapping.items()
                if target in name_to_key
            }
            if resolved:
                built["mapping"] = resolved
        result["discriminator"] = built
    return result


def _property_schema(field: dict, name_to_key: dict[str, str] | None = None) -> dict:
    """One object property fragment from a source field/param dict.
    A resolvable `one_of` becomes a native `oneOf` union; otherwise the
    field `description` wins over the raw type hint and `enum` is preserved."""
    union = _union_schema(field, name_to_key or {})
    if union is not None:
        return union
    prop = _schema_from_type(
        field.get("type") if "type" in field else field.get("schema")
    ) or {}
    if field.get("description"):
        prop["description"] = field["description"]
    if field.get("enum"):
        prop["enum"] = field["enum"]
    return prop


def _nest_properties(
    fields: list[dict], name_to_key: dict[str, str] | None = None
) -> tuple[dict, list[str]]:
    """Reconstruct nested object/array schemas from the flat dotted-name
    convention the extraction emits: `Parent[].Child` is a field of the object
    elements of array `Parent`; `Parent.Child` is a field of nested object
    `Parent`. A standalone `Parent` field contributes its description/required to
    the container. Returns (properties, required) for the top level."""
    tree: dict = {"children": {}, "order": [], "array": False, "leaf": None}
    for field in fields:
        name = field.get("name")
        if not name:
            continue
        node = tree
        parts = name.split(".")
        for i, part in enumerate(parts):
            is_array = part.endswith("[]")
            key = part[:-2] if is_array else part
            if not key:
                continue
            child = node["children"].get(key)
            if child is None:
                child = {"children": {}, "order": [], "array": False, "leaf": None}
                node["children"][key] = child
                node["order"].append(key)
            if is_array:
                child["array"] = True
            if i == len(parts) - 1:
                child["leaf"] = field
            node = child
    return _materialize_node(tree, name_to_key)


def _materialize_node(
    node: dict, name_to_key: dict[str, str] | None = None
) -> tuple[dict, list[str]]:
    properties: dict = {}
    required: list[str] = []
    for key in node["order"]:
        child = node["children"][key]
        properties[key] = _node_schema(child, name_to_key)
        if child["leaf"] and child["leaf"].get("required"):
            required.append(key)
    return properties, required


def _node_schema(node: dict, name_to_key: dict[str, str] | None = None) -> dict:
    leaf = node["leaf"]
    # A union leaf is terminal: its members already describe the shape, so it is
    # never also expanded as a nested dotted-path object.
    if leaf is not None and leaf.get("one_of"):
        return _property_schema(leaf, name_to_key)
    if not node["children"]:
        return _property_schema(leaf, name_to_key) if leaf else {}
    child_props, child_required = _materialize_node(node, name_to_key)
    obj: dict = {"type": "object", "properties": child_props}
    if child_required:
        obj["required"] = child_required
    schema = {"type": "array", "items": obj} if node["array"] else obj
    if leaf and leaf.get("description"):
        schema["description"] = leaf["description"]
    return schema


def _build_request_body(
    request: dict | None, body_params: list[dict], name_to_key: dict[str, str] | None = None
) -> dict:
    """Assemble requestBody from the prose `request` blob and/or `in:body` fields.

    OpenAPI 3.x has no `in: body` parameter — body fields belong here as an
    object schema. When body fields exist they drive `properties`/`required`;
    any prose `request.schema`/`description` text is preserved (non-speculative)
    rather than dropped. With no body fields the legacy single-schema mapping is
    kept intact."""
    request = request or {}
    content_type = _normalize_media_type(request.get("content_type"))
    if body_params:
        properties, required = _nest_properties(body_params, name_to_key)
        schema: dict = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        prose = request.get("schema")
        if isinstance(prose, str) and prose.strip():
            schema["description"] = prose.strip()
    else:
        schema = _schema_from_type(request.get("schema")) or {}
    body: dict = {"content": {content_type: {"schema": schema}}}
    if request.get("required") is not None:
        body["required"] = bool(request["required"])
    elif body_params:
        # A body carrying source-stated fields is required absent a contrary signal.
        body["required"] = True
    if request.get("description"):
        body["description"] = request["description"]
    return body


def _response_schema(raw: dict, name_to_key: dict[str, str]) -> dict | None:
    """The response body schema: a `$ref` to a named component when the response
    references one (schema_ref), otherwise the inline/prose schema. An
    unresolvable schema_ref yields nothing — a dangling $ref is never invented."""
    ref = raw.get("schema_ref")
    if isinstance(ref, str) and ref.strip():
        key = name_to_key.get(ref.strip())
        return {"$ref": f"#/components/schemas/{key}"} if key else None
    return _schema_from_type(raw.get("schema"))


def _build_responses(
    responses: list[dict], name_to_key: dict[str, str] | None = None
) -> dict:
    name_to_key = name_to_key or {}
    out: dict = {}
    folded: list[str] = []  # business-status descriptions with no HTTP code
    folded_schemas: list[tuple[str, dict]] = []  # (content_type, schema) for the fold
    for raw in responses:
        status = str(raw.get("status") or "").strip()
        if not status:
            continue
        key = _status_key(status)
        schema = _response_schema(raw, name_to_key)
        content_type = _normalize_media_type(raw.get("content_type"))
        if key is None:
            # e.g. "SUCCESS" or a Chinese label: keep it in the description so
            # the information survives, and fold under a single 200 below.
            desc = raw.get("description") or ""
            folded.append(f"{status}：{desc}".rstrip("：") if desc else status)
            if schema:
                folded_schemas.append((content_type, schema))
            continue
        resp: dict = {"description": raw.get("description") or ""}
        if schema:
            resp["content"] = {content_type: {"schema": schema}}
        out[key] = resp
    if folded or folded_schemas:
        key = "200" if "200" not in out else "default"
        resp = out.get(key) or {
            "description": "；".join(d for d in folded if d) or "回應"
        }
        if folded_schemas and "content" not in resp:
            if len(folded_schemas) == 1:
                ct, schema = folded_schemas[0]
            else:
                # several distinct outcome shapes fold under one 200 → oneOf
                ct = "application/json"
                schema = {"oneOf": [s for _, s in folded_schemas]}
            resp["content"] = {ct: {"schema": schema}}
        out[key] = resp
    if not out:
        out["default"] = {
            "description": "來源未提供回應定義",
            X_LOOP_STATUS: MISSING_STATUS,
        }
    return out


_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
_ID_BAD = re.compile(r"[^A-Za-z0-9_]+")


def _operation_id(summary: str | None, method: str, locator: str, used: set[str]) -> str:
    """A unique, identifier-safe operationId. Prefer the doc's own operation code
    in the summary ("[NPA-F01]"); else derive mechanically from method+path. Both
    are source-grounded restatements, not invented facts. Deduped with a suffix."""
    code = None
    if summary:
        match = re.search(r"\[([^\]]+)\]", summary)
        if match:
            code = match.group(1)
    base = _ID_BAD.sub("_", code or f"{method}_{locator}")
    base = re.sub(r"_+", "_", base).strip("_") or method
    oid = base
    suffix = 2
    while oid in used:
        oid = f"{base}_{suffix}"
        suffix += 1
    used.add(oid)
    return oid


def _assign_operation_ids(doc: dict) -> None:
    """Assign a unique operationId to every operation across paths and webhooks."""
    used: set[str] = set()
    for locator, item in list(doc.get("paths", {}).items()) + list(
        doc.get("webhooks", {}).items()
    ):
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() in _HTTP_METHODS and isinstance(op, dict):
                op["operationId"] = _operation_id(
                    op.get("summary"), method, locator, used
                )


def _build_operation(
    endpoints: list,
    name_to_key: dict[str, str] | None = None,
    scheme_keys: dict[str, str] | None = None,
    environments: list | None = None,
) -> dict:
    """Build one OpenAPI operation from one or more source endpoints that share
    the same method+path. OpenAPI permits only a single operation per path+method,
    so when a source lists the same URL more than once (e.g. several payment
    products posting to one gateway endpoint, selected by a parameter) their
    parameters and responses are unioned rather than one overwriting the other."""
    scheme_keys = scheme_keys or {}
    op: dict = {}
    summaries: list[str] = []
    for endpoint in endpoints:
        if endpoint.summary and endpoint.summary not in summaries:
            summaries.append(endpoint.summary)
    if summaries:
        op["summary"] = "；".join(summaries)
    # Source-stated grouping labels, unioned across merged endpoints (first-seen).
    tags: list[str] = []
    for endpoint in endpoints:
        for tag in endpoint.tags:
            if tag and tag not in tags:
                tags.append(tag)
    if tags:
        op["tags"] = tags
    # OpenAPI requires unique (name, in) per operation; keep the first occurrence.
    # `in: body` fields are NOT parameters in OpenAPI 3.x — they are partitioned
    # out here and unioned into requestBody (first occurrence wins on name).
    params = []
    seen: set[tuple[str, str]] = set()
    body_params: list[dict] = []
    body_seen: set[str] = set()
    for endpoint in endpoints:
        for raw in endpoint.parameters:
            if (raw.get("in") or raw.get("location")) == "body":
                name = raw.get("name")
                if not name or name in body_seen:
                    continue
                body_seen.add(name)
                body_params.append(raw)
                continue
            built = _build_parameter(raw)
            if not built:
                continue
            key = (built["name"], built["in"])
            if key in seen:
                continue
            seen.add(key)
            params.append(built)
    if params:
        op["parameters"] = params
    request = next((e.request for e in endpoints if e.request), None)
    if request or body_params:
        op["requestBody"] = _build_request_body(request, body_params, name_to_key)
    # Security schemes this operation requires, resolved from scheme names to the
    # sanitized component keys; unresolvable names are dropped (never invented).
    requirements: list[dict] = []
    seen_schemes: set[str] = set()
    for endpoint in endpoints:
        for name in endpoint.security:
            key = scheme_keys.get(name)
            if key and key not in seen_schemes:
                seen_schemes.add(key)
                requirements.append({key: []})
    if requirements:
        op["security"] = requirements
    responses: list[dict] = []
    for endpoint in endpoints:
        responses.extend(endpoint.responses)
    op["responses"] = _build_responses(responses, name_to_key)
    # 來源明載的 per-endpoint 主機:翻成 operation-level servers,覆寫 root servers。
    # 未解析到 environment 時靜默略過 —— cross_file 已在輸入邊界擋下不存在的名字,
    # 這裡不臆測、不產出壞 URL。
    server_name = next(
        (e.server for e in endpoints if getattr(e, "server", None)), None
    )
    if server_name:
        env = next(
            (e for e in (environments or [])
             if e.name == server_name and e.base_url), None
        )
        if env is not None:
            entry: dict = {"url": env.base_url}
            if env.name:
                entry["description"] = env.name
            op["servers"] = [entry]
    return op


# Path template variables are the names inside single `{...}` segments; OpenAPI
# requires every such token to have a matching `in: path` parameter. The token
# name is source-stated (it is literally in the path string), so synthesizing a
# minimal parameter for it is grounding, not inference.
def _path_template_tokens(path: str) -> list[str]:
    seen: list[str] = []
    for token in re.findall(r"\{([^{}/]+)\}", path):
        if token not in seen:
            seen.append(token)
    return seen


def _build_paths(
    plan: NormalizationPlan,
    name_to_key: dict[str, str],
    scheme_keys: dict[str, str],
) -> dict:
    # Group endpoints by (path, method) preserving first-seen order, so several
    # source endpoints sharing one method+path collapse into a single merged
    # operation instead of the last one overwriting the rest.
    grouped: dict[tuple[str, str], list] = {}
    for endpoint in plan.endpoints:
        if not endpoint.path or not endpoint.method:
            continue
        grouped.setdefault((endpoint.path, endpoint.method.lower()), []).append(
            endpoint
        )
    paths: dict = {}
    for (path, method), endpoints in grouped.items():
        op = _build_operation(
            endpoints, name_to_key, scheme_keys, environments=plan.environments
        )
        declared_path = {
            param["name"]
            for param in op.get("parameters", [])
            if isinstance(param, dict) and param.get("in") == "path"
        }
        synthesized = [
            {"name": token, "in": "path", "required": True, "schema": {}}
            for token in _path_template_tokens(path)
            if token not in declared_path
        ]
        if synthesized:
            op["parameters"] = op.get("parameters", []) + synthesized
        paths.setdefault(path, {})[method] = op
    return paths


def _build_webhooks(
    plan: NormalizationPlan,
    name_to_key: dict[str, str],
    scheme_keys: dict[str, str],
) -> dict:
    """OpenAPI 3.1 top-level `webhooks`: endpoints with a method but no path are
    async callbacks (delivered to a caller-defined URL), not server paths."""
    out: dict = {}
    for name, endpoint in webhook_items(plan):
        out[name] = {
            endpoint.method.lower(): _build_operation(
                [endpoint], name_to_key, scheme_keys
            )
        }
    return out


def _root_tags(plan: NormalizationPlan) -> list[dict]:
    """Unique tag declarations in source order, from every endpoint's tags."""
    names: list[str] = []
    for endpoint in plan.endpoints:
        for tag in endpoint.tags:
            if tag and tag not in names:
                names.append(tag)
    return [{"name": name} for name in names]


def _build_object_schema(entry, name_to_key: dict[str, str] | None = None) -> dict:
    properties, required = _nest_properties(entry.fields, name_to_key)
    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    if entry.constraints:
        schema["description"] = entry.constraints
    # Freeform string enums (the documented contract shape) are not cleanly
    # parseable into per-property `enum` arrays, so preserve them verbatim on
    # the object as a vendor extension rather than inventing structure.
    string_enums = [e for e in entry.enums if isinstance(e, str)]
    if string_enums:
        schema["x-enum-values"] = string_enums
    return schema


def _build_schemas(
    plan: NormalizationPlan, key_map: dict[int, str],
    name_to_key: dict[str, str] | None = None,
) -> dict:
    out: dict = {}
    for idx, entry in enumerate(plan.schemas):
        if entry.name:
            key = key_map[idx]
            obj = _build_object_schema(entry, name_to_key)
            # When the source name can't be a valid component key (CJK, slashes,
            # spaces) the key is sanitized/falls back to schema<idx>; keep the
            # original human-readable name in `title` so it isn't lost.
            if key != entry.name:
                obj["title"] = entry.name
            out[key] = obj
        for enum_idx, enum in enumerate(entry.enums):
            if not isinstance(enum, dict):
                continue  # string enums are folded into the parent schema
            enum_name = enum.get("name")
            values = enum.get("values")
            if enum_name and values:
                key = component_key(enum_name, enum_idx, prefix="enum")
                out[key] = {"type": "string", "enum": values}
    return out


def build_openapi(plan: NormalizationPlan) -> dict:
    # One shared schema-key assignment so paths ($ref), components and provenance
    # all agree on the same component identifier per schema.
    key_map = schema_key_map(plan.schemas)
    name_to_key = {
        entry.name: key_map[idx]
        for idx, entry in enumerate(plan.schemas)
        if entry.name
    }
    scheme_keys = {
        scheme.name: security_scheme_key(scheme.name, idx)
        for idx, scheme in enumerate(plan.security_schemes)
        if scheme.name
    }
    doc: dict = {"openapi": "3.1.0", "info": _build_info(plan)}
    servers = _build_servers(plan)
    if servers:
        doc["servers"] = servers
    root_tags = _root_tags(plan)
    if root_tags:
        doc["tags"] = root_tags
    doc["paths"] = _build_paths(plan, name_to_key, scheme_keys)
    webhooks = _build_webhooks(plan, name_to_key, scheme_keys)
    if webhooks:
        doc["webhooks"] = webhooks
    _assign_operation_ids(doc)
    components: dict = {}
    schemas = _build_schemas(plan, key_map, name_to_key)
    if schemas:
        components["schemas"] = schemas
    security_schemes = _build_security_schemes(plan)
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        doc["components"] = components
    return doc
