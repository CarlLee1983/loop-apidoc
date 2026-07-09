"""Cross-file invariants between `endpoints/*.json` and `inventory.json`.

Endpoint subagents write their own file, so the orchestrator no longer sees each
endpoint's JSON pass through its context. What it loses in carriage it must regain
in verification: these five invariants catch every failure mode that *loses data* —
a subagent that died, one that wrote an endpoint nobody asked for, two that wrote
the same endpoint, or one that invented a schema/security name.

Deliberately set-based, never index-based: generation keys on `method`/`path` and
never on the filename, so two files' contents being swapped has no downstream
consequence and must not be rejected.

Pure: no file I/O. Callers turn the returned messages into `AssembleInputError`.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def _entries(payload: dict | None, section: str) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    return [e for e in (payload.get(section) or []) if isinstance(e, dict)]


def _key(entry: dict) -> str:
    """`(method, path)` 正規化為一個可讀的比對鍵;method 大小寫不敏感。"""
    method = entry.get("method")
    method = method.upper() if isinstance(method, str) else "?"
    path = entry.get("path")
    path = path if isinstance(path, str) else "?"
    return f"{method} {path}"


def _names(payload: dict, section: str) -> set[str]:
    return {
        e["name"] for e in _entries(payload, section)
        if isinstance(e.get("name"), str)
    }


def _count_violations(inventory: dict, endpoints: list[tuple[str, dict]]) -> list[str]:
    expected = len(_entries(inventory, "endpoints"))
    actual = len(endpoints)
    if expected == actual:
        return []
    return [
        f"endpoints/*.json 檔數 {actual} 不等於 inventory.endpoints 筆數 {expected}"
        "(每個 inventory 端點恰好一個檔;可能有 subagent 未寫出檔案)"
    ]


def _multiset_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    inventory_keys = Counter(_key(e) for e in _entries(inventory, "endpoints"))
    file_keys = Counter(_key(ep) for _, ep in endpoints)

    out: list[str] = []
    for key in sorted(file_keys - inventory_keys):
        files = sorted(name for name, ep in endpoints if _key(ep) == key)
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
        seen.setdefault(_key(endpoint), []).append(name)
    return [
        f"{', '.join(sorted(files))}: 同一端點 {key} 被寫進多個檔案"
        "(兩個 subagent 寫了同一個端點,另一個端點可能因此沒人寫)"
        for key, files in sorted(seen.items()) if len(files) > 1
    ]


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


def cross_file_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    """一次列出所有跨檔違規——修正是一次重寫擷取 JSON,不是逐筆往返。"""
    return (
        _count_violations(inventory, endpoints)
        + _multiset_violations(inventory, endpoints)
        + _duplicate_violations(endpoints)
        + _reference_violations(inventory, endpoints)
    )
