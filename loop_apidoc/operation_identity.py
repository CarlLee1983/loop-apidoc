"""Neutral operation shape and identity helpers.

Extraction gates, source-fact coverage, and focus directives all need the same
representation of an operation. This module deliberately has no dependency on
the CLI adapter so those consumers can share that representation directly.
"""

from __future__ import annotations

from typing import Any


def entries(payload: dict | None, section: str) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    return [entry for entry in (payload.get(section) or []) if isinstance(entry, dict)]


def expand_methods(entries: list[dict]) -> list[dict]:
    """Emit one canonical operation entry for each additive ``methods`` value."""
    expanded: list[dict] = []
    for entry in entries:
        raw_methods = entry.get("methods")
        if isinstance(raw_methods, list):
            methods = [
                value.upper()
                for value in raw_methods
                if isinstance(value, str) and value.strip()
            ]
        else:
            method = entry.get("method")
            methods = [method] if isinstance(method, str) and method.strip() else []
        for method in methods:
            expanded.append(
                {key: value for key, value in entry.items() if key != "methods"}
                | {"method": method}
            )
    return expanded


def normalized_summary(value: Any) -> str | None:
    """Normalize whitespace while retaining an otherwise exact webhook summary."""
    if not isinstance(value, str):
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def endpoint_identity(entry: dict) -> str | None:
    """Return an extraction operation's stable cross-file identity string."""
    method = entry.get("method")
    method = method.upper() if isinstance(method, str) else "?"
    path = entry.get("path")
    if isinstance(path, str):
        return f"{method} {path}"
    summary = normalized_summary(entry.get("summary"))
    if summary is None:
        return None
    return f"{method} (webhook) {summary}"


def extraction_identities(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> set[str]:
    """Return the union of operation identities declared by extraction inputs."""
    declared = expand_methods(entries(inventory, "endpoints"))
    declared += [
        expanded
        for _, endpoint in endpoints
        for expanded in expand_methods([endpoint])
    ]
    return {
        key for key in (endpoint_identity(entry) for entry in declared)
        if key is not None
    }
