from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.plan.models import NormalizationPlan, PlanItemStatus


def _entries(target: str, cited) -> list[ProvenanceEntry]:
    if not cited.citations:
        return [ProvenanceEntry(target=target, status=cited.status)]
    return [
        ProvenanceEntry(
            target=target,
            status=cited.status,
            manifest_source=c.manifest_source,
            query_id=c.query_id,
            answer_path=c.answer_path,
            locator=c.locator,
        )
        for c in cited.citations
    ]


def _info_entries(plan: NormalizationPlan) -> list[ProvenanceEntry]:
    title = plan.system_groups[0].name if plan.system_groups else None
    version = next((e.version for e in plan.environments if e.version), None)
    return [
        ProvenanceEntry(
            target="info.title",
            status=PlanItemStatus.SUPPORTED if title else PlanItemStatus.MISSING,
        ),
        ProvenanceEntry(
            target="info.version",
            status=PlanItemStatus.SUPPORTED if version else PlanItemStatus.MISSING,
        ),
    ]


def build_provenance(plan: NormalizationPlan) -> ProvenanceDocument:
    entries: list[ProvenanceEntry] = list(_info_entries(plan))

    server_idx = 0
    for env in plan.environments:
        if not env.base_url:
            continue
        entries.extend(_entries(f"servers[{server_idx}]", env))
        server_idx += 1

    for idx, scheme in enumerate(plan.security_schemes):
        name = scheme.name or f"scheme{idx}"
        entries.extend(_entries(f"components.securitySchemes.{name}", scheme))

    for endpoint in plan.endpoints:
        if not endpoint.path or not endpoint.method:
            continue
        entries.extend(_entries(f"paths.{endpoint.path}.{endpoint.method.lower()}", endpoint))

    for schema in plan.schemas:
        if schema.name:
            entries.extend(_entries(f"components.schemas.{schema.name}", schema))
        for enum in schema.enums:
            enum_name = enum.get("name")
            values = enum.get("values")
            if enum_name and values:
                entries.extend(_entries(f"components.schemas.{enum_name}", schema))

    for error in plan.errors:
        if error.code:
            entries.extend(_entries(f"errors.{error.code}", error))

    for op in plan.operational:
        if op.topic:
            entries.extend(_entries(f"operational.{op.topic}", op))

    for item in plan.missing_items:
        entries.append(ProvenanceEntry(
            target=f"missing.{item.area}", status=PlanItemStatus.MISSING,
            query_id=item.query_id))
    for item in plan.source_conflicts:
        entries.append(ProvenanceEntry(
            target=f"conflict.{item.area}", status=PlanItemStatus.CONFLICTING,
            query_id=item.query_id))
    for item in plan.unverified_items:
        entries.append(ProvenanceEntry(
            target=f"unverified.{item.area}", status=PlanItemStatus.UNVERIFIED,
            query_id=item.query_id))

    return ProvenanceDocument(notebook_url=plan.notebook_url, entries=entries)
