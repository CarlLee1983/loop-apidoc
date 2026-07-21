"""Input-boundary guards for the three extraction-schema contracts a subagent can
only satisfy if we state them: `source` citation format, `path` rooting, and
`summary` on null-path (webhook/callback) endpoints.

All three are structural properties of agent-written JSON, checkable before any
run directory exists. Left unchecked they surface far downstream — a malformed
`source` becomes a wall of `SOURCE_UNVERIFIED` at validate time, an unrooted
`path` becomes an opaque `OPENAPI_INVALID` after plan and generate have already
run, and a missing `summary` silently disables cross_file's null-path identity
key (issue #7). Failing here costs one message instead of a correction loop.

Pure: no file I/O. Callers turn the returned messages into `AssembleInputError`.
"""

from __future__ import annotations

from typing import Any

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.classify import match_manifest_source, sole_source

# Inventory sections whose entries each carry a `source`, per
# reference/extraction-schemas.md.
_SOURCE_SECTIONS = (
    "environments",
    "security_schemes",
    "endpoints",
    "schemas",
    "errors",
    "operational",
)
_INTEGRATION_SECTIONS = ("crypto", "callbacks", "field_conditions", "test_cases")


def _entries(payload: dict | None, section: str) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    return [e for e in (payload.get(section) or []) if isinstance(e, dict)]


def _path_violation(label: str, field: str, value: Any) -> str | None:
    # `null` is the documented shape for a callback/webhook with no path.
    if value is None or not isinstance(value, str):
        return None
    if value.startswith("/"):
        return None
    return (
        f"{label}: {field} 必須以 '/' 開頭（base URL 屬於 inventory.environments，"
        f"不可併入 path）：{value!r}"
    )


def path_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    """OpenAPI 3.1 要求 `paths` 的 key 以 `/` 開頭；主機屬於 `servers`。"""
    out: list[str] = []
    for idx, entry in enumerate(_entries(inventory, "endpoints")):
        violation = _path_violation(
            "inventory.json", f"endpoints[{idx}].path", entry.get("path")
        )
        if violation:
            out.append(violation)
    for name, endpoint in endpoints:
        violation = _path_violation(name, "path", endpoint.get("path"))
        if violation:
            out.append(violation)
    return out


def _has_summary(entry: dict) -> bool:
    value = entry.get("summary")
    return isinstance(value, str) and bool(value.strip())


def summary_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    """path 為 null 的 webhook/callback 端點，`summary` 是它唯一的身份。

    沒有它，cross_file 的多重集合與重複檢查無法區分兩個 webhook，
    subagent 把同一個 webhook 寫進兩個檔、另一個從沒被寫出，會靜默通過(issue #7)。
    """
    out: list[str] = []
    for idx, entry in enumerate(_entries(inventory, "endpoints")):
        if entry.get("path") is None and not _has_summary(entry):
            out.append(
                f"inventory.json: endpoints[{idx}].summary 為必填 —— "
                "path 為 null 的 webhook/callback 端點以 summary 為身份鍵"
            )
    for name, endpoint in endpoints:
        if endpoint.get("path") is None and not _has_summary(endpoint):
            out.append(
                f"{name}: summary 為必填 —— "
                "path 為 null 的 webhook/callback 端點以 summary 為身份鍵，"
                "且必須與 inventory.json 對應條目逐字相符"
            )
    return out


def _cited(value: Any) -> bool:
    # An absent source is a fail-closed gap, not a format error — validation
    # reports it as SOURCE_UNVERIFIED. Only non-empty strings are format-checked.
    return isinstance(value, str) and bool(value.strip())


def _scope_violations(
    citations: list[tuple[str, str, str]], manifest: Manifest
) -> list[str]:
    """`citations` is one scope's (label, field, value) triples.

    A scope fails only when it carries citations and **none** of them names a
    manifest source: that is the whole file ignoring the format contract, and
    the fix is one rewrite. A scope where some citations resolve and others do
    not is a *content* problem — an entry citing a document outside the corpus —
    which validation must report per-entry as SOURCE_UNVERIFIED rather than the
    boundary rejecting wholesale. A string matcher cannot tell the two apart on
    a single citation; scope is the signal that can.
    """
    if not citations:
        return []
    if any(match_manifest_source(value, manifest) for _, _, value in citations):
        return []
    return [
        f"{label}: {field} 未指向任何 manifest 來源，"
        f"格式應為 '<relative_path> p.<N>' 或 '<relative_path>#<anchor>'：{value!r}"
        for label, field, value in citations
    ]


def source_violations(
    inventory: dict,
    endpoints: list[tuple[str, dict]],
    integration: dict | None,
    manifest: Manifest,
) -> list[str]:
    """Each extraction file must cite manifest sources by name.

    Skipped entirely when the manifest collapses to a single usable document:
    attribution is then unambiguous whatever the locator says, and
    `plan.classify.classify_item` already treats such citations as supported.
    Checking here would reject inputs the pipeline accepts.
    """
    if sole_source(manifest) is not None:
        return []

    inventory_scope = [
        ("inventory.json", f"{section}[{idx}].source", entry["source"])
        for section in _SOURCE_SECTIONS
        for idx, entry in enumerate(_entries(inventory, section))
        if _cited(entry.get("source"))
    ]
    field_scope = [
        ("inventory.json", f"schemas[{schema_idx}].fields[{field_idx}].source", field["source"])
        for schema_idx, schema in enumerate(_entries(inventory, "schemas"))
        for field_idx, field in enumerate(schema.get("fields") or [])
        if isinstance(field, dict) and _cited(field.get("source"))
    ]
    inventory_scope = [*inventory_scope, *field_scope]
    # endpoints/*.json share one scope: one file citing correctly proves the
    # contract was understood, so a sibling's odd citation is content, not format.
    endpoint_scope = [
        (name, "source", endpoint["source"])
        for name, endpoint in endpoints
        if _cited(endpoint.get("source"))
    ]
    integration_scope = [
        ("integration.json", f"{section}[{idx}].source", entry["source"])
        for section in _INTEGRATION_SECTIONS
        for idx, entry in enumerate(_entries(integration, section))
        if _cited(entry.get("source"))
    ]

    return [
        violation
        for scope in (inventory_scope, endpoint_scope, integration_scope)
        for violation in _scope_violations(scope, manifest)
    ]


def check_extraction_inputs(
    inventory: dict,
    endpoints: list[tuple[str, dict]],
    integration: dict | None,
    manifest: Manifest,
) -> list[str]:
    """All violations at once — the fix is one rewrite of the extraction JSON,
    so reporting only the first would force a needless round trip."""
    return (
        path_violations(inventory, endpoints)
        + summary_violations(inventory, endpoints)
        + source_violations(inventory, endpoints, integration, manifest)
    )
