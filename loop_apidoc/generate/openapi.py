from __future__ import annotations

from loop_apidoc.plan.models import NormalizationPlan

MISSING_STATUS = "missing-source"
X_LOOP_STATUS = "x-loop-status"

_OPENAPI_SECURITY_TYPES = {"apiKey", "http", "oauth2", "openIdConnect", "mutualTLS"}
_APIKEY_LOCATIONS = {"header", "query", "cookie"}


def _schema_from_type(value) -> dict | None:
    """Tolerant mapping of a free-form type hint to a JSON-Schema fragment."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        return {"type": value}
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
        name = scheme.name or f"scheme{idx}"
        out[name] = _build_security_scheme(scheme)
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
    schema = _schema_from_type(raw.get("type") if "type" in raw else raw.get("schema"))
    if schema:
        param["schema"] = schema
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
    for raw in responses:
        status = str(raw.get("status") or "").strip()
        if not status:
            continue
        resp: dict = {"description": raw.get("description") or ""}
        schema = _schema_from_type(raw.get("schema"))
        if schema:
            content_type = raw.get("content_type") or "application/json"
            resp["content"] = {content_type: {"schema": schema}}
        out[status] = resp
    if not out:
        out["default"] = {
            "description": "來源未提供回應定義",
            X_LOOP_STATUS: MISSING_STATUS,
        }
    return out


def _build_operation(endpoint) -> dict:
    op: dict = {}
    if endpoint.summary:
        op["summary"] = endpoint.summary
    params = [p for p in (_build_parameter(r) for r in endpoint.parameters) if p]
    if params:
        op["parameters"] = params
    if endpoint.request:
        op["requestBody"] = _build_request_body(endpoint.request)
    op["responses"] = _build_responses(endpoint.responses)
    return op


def _build_paths(plan: NormalizationPlan) -> dict:
    paths: dict = {}
    for endpoint in plan.endpoints:
        if not endpoint.path or not endpoint.method:
            continue
        method = endpoint.method.lower()
        paths.setdefault(endpoint.path, {})[method] = _build_operation(endpoint)
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
    return schema


def _build_schemas(plan: NormalizationPlan) -> dict:
    out: dict = {}
    for entry in plan.schemas:
        if entry.name:
            out[entry.name] = _build_object_schema(entry)
        for enum in entry.enums:
            enum_name = enum.get("name")
            values = enum.get("values")
            if enum_name and values:
                out[enum_name] = {"type": "string", "enum": values}
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
