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


def build_openapi(plan: NormalizationPlan) -> dict:
    doc: dict = {"openapi": "3.1.0", "info": _build_info(plan)}
    servers = _build_servers(plan)
    if servers:
        doc["servers"] = servers
    doc["paths"] = {}
    components: dict = {}
    security_schemes = _build_security_schemes(plan)
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        doc["components"] = components
    return doc
