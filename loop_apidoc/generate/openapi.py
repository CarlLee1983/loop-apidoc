from __future__ import annotations

import re

from loop_apidoc.generate.naming import component_key, security_scheme_key
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
    title = plan.system_groups[0].name if plan.system_groups else None
    version = next((e.version for e in plan.environments if e.version), None)
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


def _build_request_body(raw: dict) -> dict:
    content_type = raw.get("content_type") or "application/json"
    schema = _schema_from_type(raw.get("schema")) or {}
    body: dict = {"content": {content_type: {"schema": schema}}}
    if raw.get("required") is not None:
        body["required"] = bool(raw["required"])
    if raw.get("description"):
        body["description"] = raw["description"]
    return body


def _build_responses(responses: list[dict]) -> dict:
    out: dict = {}
    folded: list[str] = []  # business-status responses with no HTTP code
    for raw in responses:
        status = str(raw.get("status") or "").strip()
        if not status:
            continue
        key = _status_key(status)
        if key is None:
            # e.g. "SUCCESS" or a Chinese label: keep it in the description so
            # the information survives, and fold under a single 200 below.
            desc = raw.get("description") or ""
            folded.append(f"{status}：{desc}".rstrip("：") if desc else status)
            continue
        resp: dict = {"description": raw.get("description") or ""}
        schema = _schema_from_type(raw.get("schema"))
        if schema:
            content_type = raw.get("content_type") or "application/json"
            resp["content"] = {content_type: {"schema": schema}}
        out[key] = resp
    if folded:
        key = "200" if "200" not in out else "default"
        out.setdefault(key, {"description": "；".join(d for d in folded if d) or "回應"})
    if not out:
        out["default"] = {
            "description": "來源未提供回應定義",
            X_LOOP_STATUS: MISSING_STATUS,
        }
    return out


def _build_operation(endpoints: list) -> dict:
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
    params = []
    seen: set[tuple[str, str]] = set()
    for endpoint in endpoints:
        for raw in endpoint.parameters:
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
    for endpoint in endpoints:
        if endpoint.request:
            op["requestBody"] = _build_request_body(endpoint.request)
            break
    responses: list[dict] = []
    for endpoint in endpoints:
        responses.extend(endpoint.responses)
    op["responses"] = _build_responses(responses)
    return op


def _build_paths(plan: NormalizationPlan) -> dict:
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
        paths.setdefault(path, {})[method] = _build_operation(endpoints)
    return paths


def _build_object_schema(entry) -> dict:
    properties: dict = {}
    required: list[str] = []
    for field in entry.fields:
        name = field.get("name")
        if not name:
            continue
        prop = _schema_from_type(field.get("type") if "type" in field else field.get("schema")) or {}
        if field.get("description"):
            prop["description"] = field["description"]
        if field.get("enum"):
            prop["enum"] = field["enum"]
        properties[name] = prop
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


def _build_schemas(plan: NormalizationPlan) -> dict:
    out: dict = {}
    for idx, entry in enumerate(plan.schemas):
        if entry.name:
            key = component_key(entry.name, idx, prefix="schema")
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
    doc: dict = {"openapi": "3.1.0", "info": _build_info(plan)}
    servers = _build_servers(plan)
    if servers:
        doc["servers"] = servers
    doc["paths"] = _build_paths(plan)
    components: dict = {}
    schemas = _build_schemas(plan)
    if schemas:
        components["schemas"] = schemas
    security_schemes = _build_security_schemes(plan)
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        doc["components"] = components
    return doc
