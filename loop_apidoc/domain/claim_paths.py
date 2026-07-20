from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ClaimPathError(ValueError):
    pass


def escape_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _put(paths: dict[str, Any], path: str, value: Any) -> None:
    if value is not None:
        paths[path] = value


def _operation_paths(value: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for name in ("method", "path", "summary", "server", "request_schema_ref"):
        _put(paths, f"/{name}", value.get(name))
    for parameter in value.get("parameters") or ():
        if not isinstance(parameter, dict):
            continue
        name = parameter.get("name")
        location = parameter.get("location")
        if name is None or location is None:
            continue
        prefix = (
            f"/parameters/{escape_segment(str(location))}/{escape_segment(str(name))}"
        )
        _put(paths, f"{prefix}/name", name)
        for field in ("required", "schema_ref"):
            _put(paths, f"{prefix}/{field}", parameter.get(field))
    for response in value.get("responses") or ():
        if not isinstance(response, dict):
            continue
        status = response.get("status_code")
        if status is None:
            continue
        prefix = f"/responses/{escape_segment(str(status))}"
        _put(paths, f"{prefix}/status_code", status)
        for field in ("description", "schema_ref"):
            _put(paths, f"{prefix}/{field}", response.get(field))
    for scheme in value.get("security") or ():
        _put(
            paths,
            f"/security/{escape_segment(str(scheme))}",
            scheme,
        )
    return paths


def _environment_paths(value: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    _put(paths, "/name", value.get("name"))
    for server in value.get("servers") or ():
        _put(paths, f"/servers/{escape_segment(str(server))}", server)
    return paths


def _webhook_paths(value: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for name in ("name", "callback_path", "verification", "expected_response"):
        _put(paths, f"/{name}", value.get(name))
    return paths


def _schema_paths(value: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    _put(paths, "/name", value.get("name"))
    for field in value.get("fields") or ():
        if not isinstance(field, dict) or field.get("name") is None:
            continue
        name = field["name"]
        prefix = f"/fields/{escape_segment(str(name))}"
        _put(paths, f"{prefix}/name", name)
        for attribute in ("type", "schema_ref", "required", "condition"):
            _put(paths, f"{prefix}/{attribute}", field.get(attribute))
    return paths


def _security_paths(value: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for name in ("name", "type"):
        _put(paths, f"/{name}", value.get(name))
    return paths


def _error_paths(value: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for name in ("code", "description"):
        _put(paths, f"/{name}", value.get(name))
    for operation in value.get("applicable_to") or ():
        _put(
            paths,
            f"/applicable_to/{escape_segment(str(operation))}",
            operation,
        )
    return paths


def _integration_paths(value: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for name in ("name", "kind"):
        _put(paths, f"/{name}", value.get(name))
    for operation in value.get("operation_refs") or ():
        _put(
            paths,
            f"/operation_refs/{escape_segment(str(operation))}",
            operation,
        )
    for step in value.get("steps") or ():
        _put(paths, f"/steps/{escape_segment(str(step))}", step)
    return paths


def _operational_paths(value: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for name in ("topic", "detail"):
        _put(paths, f"/{name}", value.get(name))
    return paths


_PATH_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "operation": _operation_paths,
    "schema": _schema_paths,
    "environment": _environment_paths,
    "security": _security_paths,
    "error": _error_paths,
    "webhook": _webhook_paths,
    "integration_mechanic": _integration_paths,
    "operational_constraint": _operational_paths,
}


def material_claim_paths(claim_kind: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, dict) or claim_kind not in _PATH_HANDLERS:
        return ("",)
    return tuple(sorted(_PATH_HANDLERS[claim_kind](value)))


def claim_value_at(claim_kind: str, value: Any, path: str) -> Any:
    values = {"": value}
    if isinstance(value, dict) and claim_kind in _PATH_HANDLERS:
        values.update(_PATH_HANDLERS[claim_kind](value))
    if path not in values:
        raise ClaimPathError(f"unknown material claim path: {path}")
    return values[path]

