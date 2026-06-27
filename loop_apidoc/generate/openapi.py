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
    # Unmapped source type: minimal legal apiKey placeholder, never a guess.
    location = scheme.location if scheme.location in _APIKEY_LOCATIONS else "header"
    out = {
        "type": "apiKey",
        "in": location,
        "name": scheme.details or "Authorization",
        X_LOOP_STATUS: MISSING_STATUS,
    }
    if raw:
        out["description"] = raw
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


def _property_schema(field: dict) -> dict:
    """One object property fragment from a source field/param dict.
    Field `description` wins over the raw type hint; `enum` is preserved."""
    prop = _schema_from_type(
        field.get("type") if "type" in field else field.get("schema")
    ) or {}
    if field.get("description"):
        prop["description"] = field["description"]
    if field.get("enum"):
        prop["enum"] = field["enum"]
    return prop


def _build_request_body(request: dict | None, body_params: list[dict]) -> dict:
    """Assemble requestBody from the prose `request` blob and/or `in:body` fields.

    OpenAPI 3.x has no `in: body` parameter — body fields belong here as an
    object schema. When body fields exist they drive `properties`/`required`;
    any prose `request.schema`/`description` text is preserved (non-speculative)
    rather than dropped. With no body fields the legacy single-schema mapping is
    kept intact."""
    request = request or {}
    content_type = _normalize_media_type(request.get("content_type"))
    if body_params:
        properties: dict = {}
        required: list[str] = []
        for raw in body_params:
            name = raw.get("name")
            if not name:
                continue
            properties[name] = _property_schema(raw)
            if raw.get("required"):
                required.append(name)
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


def _build_operation(endpoints: list, name_to_key: dict[str, str] | None = None) -> dict:
    """Build one OpenAPI operation from one or more source endpoints that share
    the same method+path. OpenAPI permits only a single operation per path+method,
    so when a source lists the same URL more than once (e.g. several payment
    products posting to one gateway endpoint, selected by a parameter) their
    parameters and responses are unioned rather than one overwriting the other."""
    op: dict = {}
    summaries: list[str] = []
    for endpoint in endpoints:
        if endpoint.summary and endpoint.summary not in summaries:
            summaries.append(endpoint.summary)
    if summaries:
        op["summary"] = "；".join(summaries)
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
        op["requestBody"] = _build_request_body(request, body_params)
    responses: list[dict] = []
    for endpoint in endpoints:
        responses.extend(endpoint.responses)
    op["responses"] = _build_responses(responses, name_to_key)
    return op


def _build_paths(plan: NormalizationPlan, name_to_key: dict[str, str]) -> dict:
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
        paths.setdefault(path, {})[method] = _build_operation(endpoints, name_to_key)
    return paths


def _build_webhooks(plan: NormalizationPlan, name_to_key: dict[str, str]) -> dict:
    """OpenAPI 3.1 top-level `webhooks`: endpoints with a method but no path are
    async callbacks (delivered to a caller-defined URL), not server paths."""
    out: dict = {}
    for name, endpoint in webhook_items(plan):
        out[name] = {endpoint.method.lower(): _build_operation([endpoint], name_to_key)}
    return out


def _build_object_schema(entry) -> dict:
    properties: dict = {}
    required: list[str] = []
    for field in entry.fields:
        name = field.get("name")
        if not name:
            continue
        properties[name] = _property_schema(field)
        if field.get("required"):
            required.append(name)
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


def _build_schemas(plan: NormalizationPlan, key_map: dict[int, str]) -> dict:
    out: dict = {}
    for idx, entry in enumerate(plan.schemas):
        if entry.name:
            key = key_map[idx]
            obj = _build_object_schema(entry)
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
    doc: dict = {"openapi": "3.1.0", "info": _build_info(plan)}
    servers = _build_servers(plan)
    if servers:
        doc["servers"] = servers
    doc["paths"] = _build_paths(plan, name_to_key)
    webhooks = _build_webhooks(plan, name_to_key)
    if webhooks:
        doc["webhooks"] = webhooks
    components: dict = {}
    schemas = _build_schemas(plan, key_map)
    if schemas:
        components["schemas"] = schemas
    security_schemes = _build_security_schemes(plan)
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        doc["components"] = components
    return doc
