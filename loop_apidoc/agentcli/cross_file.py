"""Cross-file invariants between `endpoints/*.json` and `inventory.json`.

Endpoint subagents write their own file, so the orchestrator no longer sees each
endpoint's JSON pass through its context. What it loses in carriage it must regain
in verification: these invariants catch every failure mode that *loses data* —
a subagent that died, one that wrote an endpoint nobody asked for, two that wrote
the same endpoint, one that invented a schema/security name, or an operational
rule that points at a nonexistent operation/field.

Deliberately set-based, never index-based: generation keys on `method`/`path`(有
path 時)或 `summary`(webhook/callback 的 path 為 null 時)而從不看檔名,所以兩個
檔案的內容互換沒有下游後果,不得被判為違規。

Pure: no file I/O. Callers turn the returned messages into `AssembleInputError`.
"""

from __future__ import annotations

from typing import Any

from loop_apidoc.operation_identity import (
    endpoint_identity as _key,
    entries as _entries,
    expand_methods,
)


def _names(payload: dict, section: str) -> set[str]:
    return {
        e["name"] for e in _entries(payload, section)
        if isinstance(e.get("name"), str)
    }


def _count_violations(inventory: dict, endpoints: list[tuple[str, dict]]) -> list[str]:
    expected = len(expand_methods(_entries(inventory, "endpoints")))
    actual = sum(len(expand_methods([endpoint])) for _, endpoint in endpoints)
    if expected == actual:
        return []
    return [
        f"endpoints/*.json 檔數 {actual} 不等於 inventory.endpoints 筆數 {expected}"
        "(每個 inventory 端點恰好一個檔;可能有 subagent 未寫出檔案)"
    ]


def _identity_set_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    """Symmetric difference between the endpoint identities inventory declares and
    those the endpoint files carry. Deliberately set-based, not multiset: repeated
    identities are caught by `_duplicate_violations` and a file/entry count mismatch
    by `_count_violations`, so this only has to answer "which identity is on exactly
    one side"."""
    inventory_keys = {
        key for key in (_key(e) for e in expand_methods(_entries(inventory, "endpoints")))
        if key is not None
    }
    keyed_endpoints = [
        (name, ep) for name, endpoint in endpoints
        for ep in expand_methods([endpoint]) if _key(ep) is not None
    ]
    file_keys = {_key(ep) for _, ep in keyed_endpoints}

    out: list[str] = []
    for key in sorted(file_keys - inventory_keys):
        files = sorted(name for name, ep in keyed_endpoints if _key(ep) == key)
        out.append(
            f"{', '.join(files)}: 端點 {key} 不在 inventory.endpoints 中"
        )
    for key in sorted(inventory_keys - file_keys):
        out.append(
            f"inventory.json: 端點 {key} 沒有對應的 endpoints/*.json"
        )
    return out


def _duplicate_violations(endpoints: list[tuple[str, dict]]) -> list[str]:
    seen: dict[str, list[str]] = {}
    for name, endpoint in endpoints:
        for expanded in expand_methods([endpoint]):
            key = _key(expanded)
            if key is None:
                continue
            seen.setdefault(key, []).append(name)
    return [
        f"{', '.join(sorted(files))}: 同一端點 {key} 被寫進多個檔案"
        "(兩個 subagent 寫了同一個端點,另一個端點可能因此沒人寫)"
        ";若來源真的用同一個 method+path 描述多個情境(多錢包模式、多金流產品),"
        "OpenAPI 3.1 一個 path+method 只能有一個 operation —— 合併成單一檔案,"
        "用 request 欄位的 oneOf + discriminator 表達情境差異"
        for key, files in sorted(seen.items()) if len(files) > 1
    ]


def _identity_keys(entry: dict) -> frozenset[str]:
    return frozenset(
        key for key in (_key(expanded) for expanded in expand_methods([entry]))
        if key is not None
    )


def _shared_methods_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    """A shared inventory contract must remain one shared detail contract.

    Expanding to individual operations is a pipeline implementation detail; it
    must not let independently extracted method details masquerade as one source
    stated, identical contract.
    """
    out: list[str] = []
    for idx, entry in enumerate(_entries(inventory, "endpoints")):
        if not isinstance(entry.get("methods"), list):
            continue
        expected_keys = _identity_keys(entry)
        if not expected_keys:
            continue  # schema validation reports malformed methods before this gate.
        matched = [
            name for name, detail in endpoints
            if _identity_keys(detail) == expected_keys
        ]
        if len(matched) != 1:
            operations = ", ".join(sorted(expected_keys))
            out.append(
                f"inventory.json: endpoints[{idx}].methods ({operations}) 必須由一個 "
                "endpoints/*.json detail 以相同 methods 集合匹配 "
                "(same methods set;不可拆成不同 method 檔案)"
            )
    return out


def _schema_refs(endpoint: dict) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    request = endpoint.get("request")
    if isinstance(request, dict):
        out.append(("request.schema_ref", request.get("schema_ref")))
    responses = endpoint.get("responses")
    if isinstance(responses, list):
        for idx, response in enumerate(responses):
            if isinstance(response, dict):
                out.append((f"responses[{idx}].schema_ref",
                            response.get("schema_ref")))
    return out


def _reference_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    schema_names = _names(inventory, "schemas")
    scheme_names = _names(inventory, "security_schemes")

    out: list[str] = []
    for name, endpoint in endpoints:
        for field, ref in _schema_refs(endpoint):
            if isinstance(ref, str) and ref not in schema_names:
                out.append(
                    f"{name}: {field} 未指向任何 inventory.schemas[].name:{ref!r}"
                )
        security = endpoint.get("security")
        if isinstance(security, list):
            for idx, scheme in enumerate(security):
                if isinstance(scheme, str) and scheme not in scheme_names:
                    out.append(
                        f"{name}: security[{idx}] 未指向任何 "
                        f"inventory.security_schemes[].name:{scheme!r}"
                    )
    return out


def _server_violations(inventory: dict) -> list[str]:
    """不變式 6:`endpoints[].server` 若存在,必須指向某個 environments[].name。

    迭代對象是 inventory 而非端點檔 —— `server` 住在 inventory 側,
    是「這支端點在哪個主機」的事實,由 generator 翻成 operation-level servers。
    """
    env_names = _names(inventory, "environments")
    out: list[str] = []
    for idx, entry in enumerate(_entries(inventory, "endpoints")):
        server = entry.get("server")
        if isinstance(server, str) and server not in env_names:
            out.append(
                f"inventory.json: endpoints[{idx}].server 未指向任何 "
                f"environments[].name:{server!r}"
            )
    return out


def _operation_reference_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    method, separator, locator = value.strip().partition(" ")
    if not separator or not locator:
        return None
    if locator.startswith("/"):
        return _key({"method": method, "path": locator})
    return _key({"method": method, "path": None, "summary": locator})


def _schema_field_names(inventory: dict, schema_name: Any) -> set[str]:
    for schema in _entries(inventory, "schemas"):
        if schema.get("name") != schema_name:
            continue
        fields = schema.get("fields")
        if not isinstance(fields, list):
            return set()
        return {
            field["name"]
            for field in fields
            if isinstance(field, dict) and isinstance(field.get("name"), str)
        }
    return set()


def _field_resolves(inventory: dict, endpoint: dict, value: Any) -> bool:
    if not isinstance(value, str):
        return False
    area, separator, name = value.partition(".")
    if not separator or not name:
        return False
    parameters = endpoint.get("parameters")
    for parameter in parameters if isinstance(parameters, list) else []:
        if not isinstance(parameter, dict) or parameter.get("name") != name:
            continue
        location = parameter.get("in") or parameter.get("location")
        if area == "request" and location == "body":
            return True
        if area == "parameter" and location != "body":
            return True
        if area in {"query", "path", "header", "cookie"} and location == area:
            return True
    if area == "request":
        request = endpoint.get("request")
        if isinstance(request, dict) and name in _schema_field_names(
            inventory, request.get("schema_ref")
        ):
            return True
    if area == "response":
        responses = endpoint.get("responses")
        if isinstance(responses, list):
            return any(
                name in _schema_field_names(inventory, response.get("schema_ref"))
                for response in responses
                if isinstance(response, dict)
            )
    return False


def _operational_reference_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    endpoint_keys = {
        key
        for _, endpoint in endpoints
        for expanded in expand_methods([endpoint])
        if (key := _key(expanded)) is not None
    }
    endpoints_by_key = {
        key: expanded
        for _, endpoint in endpoints
        for expanded in expand_methods([endpoint])
        if (key := _key(expanded)) is not None
    }
    out: list[str] = []
    for op_index, entry in enumerate(_entries(inventory, "operational")):
        applies_to = entry.get("applies_to")
        if not isinstance(applies_to, list):
            continue
        for scope_index, scope in enumerate(applies_to):
            if not isinstance(scope, dict):
                continue
            operation = scope.get("operation")
            operation_key = _operation_reference_key(operation)
            if operation_key not in endpoint_keys:
                out.append(
                    "inventory.json: "
                    f"operational[{op_index}].applies_to[{scope_index}].operation "
                    "未指向任何 inventory.endpoints identity:"
                    f"{operation!r}"
                )
                continue
            field = scope.get("field")
            if field is not None and not _field_resolves(
                inventory, endpoints_by_key[operation_key], field
            ):
                out.append(
                    "inventory.json: "
                    f"operational[{op_index}].applies_to[{scope_index}].field "
                    f"未指向 {operation} 的任何 request/response/parameter field:{field!r}"
                )
    return out


def _integration_operation_reference_violations(
    endpoints: list[tuple[str, dict]], integration: dict | None
) -> list[str]:
    endpoint_keys = {
        key
        for _, endpoint in endpoints
        for expanded in expand_methods([endpoint])
        if (key := _key(expanded)) is not None
    }
    section_fields = {
        "transport": "operation_refs",
        "amount_direction": "operation_ref",
        "idempotency": "operation_refs",
        "line_currency_policy": "operation_refs",
    }
    out: list[str] = []
    for section, field in section_fields.items():
        for entry_index, entry in enumerate(_entries(integration, section)):
            raw = entry.get(field)
            references = raw if isinstance(raw, list) else [raw]
            for ref_index, reference in enumerate(references):
                if reference is None:
                    continue
                if _operation_reference_key(reference) in endpoint_keys:
                    continue
                location = f"{section}[{entry_index}].{field}"
                if isinstance(raw, list):
                    location += f"[{ref_index}]"
                out.append(
                    f"integration.json: {location} 未指向任何 "
                    f"inventory.endpoints identity:{reference!r}"
                )
    return out


def cross_file_violations(
    inventory: dict,
    endpoints: list[tuple[str, dict]],
    integration: dict | None = None,
) -> list[str]:
    """一次列出所有跨檔違規——修正是一次重寫擷取 JSON,不是逐筆往返。"""
    return (
        _count_violations(inventory, endpoints)
        + _identity_set_violations(inventory, endpoints)
        + _duplicate_violations(endpoints)
        + _shared_methods_violations(inventory, endpoints)
        + _reference_violations(inventory, endpoints)
        + _server_violations(inventory)
        + _operational_reference_violations(inventory, endpoints)
        + _integration_operation_reference_violations(endpoints, integration)
    )
