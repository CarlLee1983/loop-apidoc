from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.generate.naming import (
    component_key,
    schema_key_map,
    security_scheme_key,
    webhook_items,
)
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
    # Same resolution as OpenAPI info.{title,version} so provenance status and
    # the emitted spec never disagree (a mismatch trips SOURCE_UNVERIFIED).
    title = plan.resolved_title
    version = plan.resolved_version
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
        key = security_scheme_key(scheme.name, idx)
        entries.extend(_entries(f"components.securitySchemes.{key}", scheme))

    for endpoint in plan.endpoints:
        if not endpoint.path or not endpoint.method:
            continue
        entries.extend(_entries(f"paths.{endpoint.path}.{endpoint.method.lower()}", endpoint))

    for name, endpoint in webhook_items(plan):
        entries.extend(_entries(f"webhooks.{name}.{endpoint.method.lower()}", endpoint))

    key_map = schema_key_map(plan.schemas)
    for idx, schema in enumerate(plan.schemas):
        if schema.name:
            entries.extend(_entries(f"components.schemas.{key_map[idx]}", schema))
        for enum_idx, enum in enumerate(schema.enums):
            if not isinstance(enum, dict):
                continue  # string enums carry no separate provenance target
            enum_name = enum.get("name")
            values = enum.get("values")
            if enum_name and values:
                key = component_key(enum_name, enum_idx, prefix="enum")
                entries.extend(_entries(f"components.schemas.{key}", schema))

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

    if plan.integration is not None:
        from loop_apidoc.generate.integration import integration_provenance_entries

        entries += integration_provenance_entries(plan.integration)

    return ProvenanceDocument(notebook_url=plan.notebook_url, entries=entries)
