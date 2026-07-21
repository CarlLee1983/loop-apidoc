from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.generate.openapi import MISSING_STATUS, X_LOOP_STATUS
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _is_placeholder(node) -> bool:
    return isinstance(node, dict) and node.get(X_LOOP_STATUS) == MISSING_STATUS


def _schema_property_targets(target: str, node: object) -> list[tuple[str, object]]:
    """Return asserted property targets below one schema or property node."""
    if not isinstance(node, dict):
        return []

    targets: list[tuple[str, object]] = []
    properties = node.get("properties")
    if isinstance(properties, dict):
        for name, property_node in properties.items():
            property_target = f"{target}.properties.{name}"
            targets.append((property_target, property_node))
            targets.extend(_schema_property_targets(property_target, property_node))

    items = node.get("items")
    if isinstance(items, dict):
        targets.extend(_schema_property_targets(f"{target}.items", items))
    return targets


def _asserted_targets(openapi: dict) -> list[tuple[str, object]]:
    """(target, openapi-node) for each field that asserts a fact."""
    targets: list[tuple[str, object]] = []
    info = openapi.get("info") or {}
    targets.append(("info.title", info))
    targets.append(("info.version", info))
    for idx, server in enumerate(openapi.get("servers") or []):
        targets.append((f"servers[{idx}]", server))
    schemes = (openapi.get("components") or {}).get("securitySchemes") or {}
    for name, node in schemes.items():
        targets.append((f"components.securitySchemes.{name}", node))
    for path, item in (openapi.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, node in item.items():
            if method.lower() in _HTTP_METHODS:
                targets.append((f"paths.{path}.{method.lower()}", node))
    schemas = (openapi.get("components") or {}).get("schemas") or {}
    for name, node in schemas.items():
        target = f"components.schemas.{name}"
        targets.append((target, node))
        targets.extend(_schema_property_targets(target, node))
    return targets


def _issue(code: IssueCode, location: str, evidence: str, fix: str) -> Issue:
    return Issue(code=code, severity=Severity.ERROR, location=location,
                 evidence=evidence, suggested_fix=fix)


def check_speculation(openapi: dict, provenance: ProvenanceDocument) -> list[Issue]:
    by_target: dict[str, list[PlanItemStatus]] = {}
    for entry in provenance.entries:
        by_target.setdefault(entry.target, []).append(entry.status)

    issues: list[Issue] = []
    for target, node in _asserted_targets(openapi):
        if _is_placeholder(node):
            continue
        statuses = by_target.get(target, [])
        if not statuses and ".properties." in target:
            parent_schema_target = target.split(".properties.", 1)[0]
            statuses = by_target.get(parent_schema_target, [])
        if not statuses:
            issues.append(_issue(
                IssueCode.UNSUPPORTED_ASSERTION, target,
                "規格欄位無任何 provenance 映射", "為此欄位補上來源引用或移除"))
        elif PlanItemStatus.CONFLICTING in statuses:
            issues.append(_issue(
                IssueCode.SOURCE_CONFLICT, target,
                "規格欄位的來源彼此衝突", "揭露衝突並由來源澄清"))
        elif PlanItemStatus.SUPPORTED in statuses:
            continue
        else:
            issues.append(_issue(
                IssueCode.SOURCE_UNVERIFIED, target,
                "規格欄位僅有 unverified 來源，缺 supported 依據", "確認來源以取得 supported 引用"))
    return issues
