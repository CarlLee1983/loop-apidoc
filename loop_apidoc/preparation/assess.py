from __future__ import annotations

import json
from typing import Any

from loop_apidoc.manifest.models import Manifest, ProcessingStatus
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.preparation.models import (
    PreparationFinding,
    PreparationPhase,
    PreparationReport,
    PreparationSeverity,
    PreparationStatus,
)


def _finding(
    severity: PreparationSeverity,
    summary: str,
    suggested_action: str,
    *,
    evidence: str = "",
    target_file: str | None = None,
    field_path: str | None = None,
    requery_scope: str | None = None,
) -> PreparationFinding:
    return PreparationFinding(
        severity=severity,
        summary=summary,
        evidence=evidence,
        suggested_action=suggested_action,
        target_file=target_file,
        field_path=field_path,
        requery_scope=requery_scope,
    )


def _phase_status(findings: list[PreparationFinding]) -> PreparationStatus:
    if any(finding.severity is PreparationSeverity.ERROR for finding in findings):
        return PreparationStatus.BLOCKED
    if any(finding.severity is PreparationSeverity.WARNING for finding in findings):
        return PreparationStatus.NEEDS_ATTENTION
    return PreparationStatus.READY


def _phase(
    phase_id: str,
    label: str,
    metrics: dict[str, Any],
    findings: list[PreparationFinding],
) -> PreparationPhase:
    return PreparationPhase(
        id=phase_id,
        label=label,
        status=_phase_status(findings),
        metrics=metrics,
        findings=findings,
    )


def _overall_status(phases: list[PreparationPhase]) -> PreparationStatus:
    if any(phase.status is PreparationStatus.BLOCKED for phase in phases):
        return PreparationStatus.BLOCKED
    if any(phase.status is PreparationStatus.NEEDS_ATTENTION for phase in phases):
        return PreparationStatus.NEEDS_ATTENTION
    return PreparationStatus.READY


def _summary(phases: list[PreparationPhase]) -> dict[str, int]:
    counts = {status.value: 0 for status in PreparationStatus}
    for phase in phases:
        counts[phase.status.value] += 1
    return counts


def _successful_url_count(manifest: Manifest) -> int:
    return sum(
        1
        for source in manifest.url_sources
        if source.http_status is not None and 200 <= source.http_status < 400
    )


def _assess_sources(manifest: Manifest) -> PreparationPhase:
    supported_local = [
        source
        for source in manifest.local_sources
        if source.supported and source.status is ProcessingStatus.PENDING
    ]
    supported_urls = _successful_url_count(manifest)
    findings: list[PreparationFinding] = []
    if not supported_local and supported_urls == 0:
        findings.append(
            _finding(
                PreparationSeverity.ERROR,
                "no supported source available",
                "Add at least one readable supported source before generation.",
                target_file="manifest.json",
            )
        )
    if manifest.unsupported():
        findings.append(
            _finding(
                PreparationSeverity.WARNING,
                "unsupported sources present",
                "Convert unsupported inputs during preprocess or remove them from the run.",
                evidence=", ".join(s.relative_path for s in manifest.unsupported()),
                target_file="manifest.json",
            )
        )
    if manifest.unreadable():
        findings.append(
            _finding(
                PreparationSeverity.WARNING,
                "unreadable sources present",
                "Fix file permissions or replace unreadable source files.",
                evidence=", ".join(s.relative_path for s in manifest.unreadable()),
                target_file="manifest.json",
            )
        )
    return _phase(
        "sources",
        "Sources",
        {
            "local_sources": len(manifest.local_sources),
            "supported_local_sources": len(supported_local),
            "successful_urls": supported_urls,
            "unsupported_sources": len(manifest.unsupported()),
            "unreadable_sources": len(manifest.unreadable()),
        },
        findings,
    )


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _missing_detail(item: Any) -> str:
    if isinstance(item, dict):
        area = item.get("area")
        detail = item.get("detail")
        return ": ".join(str(part) for part in (area, detail) if part)
    return str(item)


def _assess_extraction(inventory: dict, endpoint_texts: list[str]) -> PreparationPhase:
    findings: list[PreparationFinding] = []
    inventory_endpoints = _as_list(inventory.get("endpoints"))
    inventory_missing = _as_list(inventory.get("missing"))
    endpoint_missing_count = 0

    if not inventory_endpoints and not endpoint_texts:
        findings.append(
            _finding(
                PreparationSeverity.ERROR,
                "no endpoint inventory or endpoint detail files available",
                "Re-run extraction and write endpoints into inventory.json plus endpoints/*.json.",
                target_file="inventory.json",
                field_path="/endpoints",
            )
        )
    elif not endpoint_texts:
        findings.append(
            _finding(
                PreparationSeverity.ERROR,
                "no endpoint detail files available",
                "Re-run endpoint extraction and write one endpoints/epN.json per operation.",
                target_file="endpoints/",
            )
        )

    for idx, item in enumerate(inventory_missing):
        findings.append(
            _finding(
                PreparationSeverity.WARNING,
                f"inventory missing item: {_missing_detail(item)}",
                "re-read source material and fill or justify this inventory gap.",
                target_file="inventory.json",
                field_path=f"/missing/{idx}",
                requery_scope=_missing_detail(item),
            )
        )

    for idx, text in enumerate(endpoint_texts):
        try:
            endpoint = json.loads(text)
        except json.JSONDecodeError as exc:
            findings.append(
                _finding(
                    PreparationSeverity.ERROR,
                    "endpoint detail JSON cannot be parsed",
                    "Regenerate the endpoint detail file as a JSON object.",
                    evidence=str(exc),
                    target_file=f"endpoints/ep{idx}.json",
                )
            )
            continue
        missing_items = _as_list(endpoint.get("missing")) if isinstance(endpoint, dict) else []
        endpoint_missing_count += len(missing_items)
        for miss_idx, item in enumerate(missing_items):
            findings.append(
                _finding(
                    PreparationSeverity.WARNING,
                    f"endpoint missing item: {_missing_detail(item)}",
                    "re-read source material for this endpoint and fill the missing field.",
                    target_file=f"endpoints/ep{idx}.json",
                    field_path=f"/missing/{miss_idx}",
                    requery_scope=_missing_detail(item),
                )
            )

    return _phase(
        "extraction",
        "Extraction",
        {
            "inventory_endpoints": len(inventory_endpoints),
            "endpoint_detail_files": len(endpoint_texts),
            "inventory_missing_items": len(inventory_missing),
            "endpoint_missing_items": endpoint_missing_count,
        },
        findings,
    )


def _assess_plan(plan: NormalizationPlan) -> PreparationPhase:
    findings: list[PreparationFinding] = []
    for item in plan.missing_items:
        findings.append(
            _finding(
                PreparationSeverity.WARNING,
                f"plan missing item: {item.area}: {item.detail}",
                "re-read source material and update the extracted answer that feeds this plan field.",
                target_file="inventory.json",
                requery_scope=item.query_id or item.area,
            )
        )
    for item in plan.source_conflicts:
        findings.append(
            _finding(
                PreparationSeverity.ERROR,
                f"source conflict: {item.area}: {item.detail}",
                "Resolve the conflicting source evidence before generating a release artifact.",
                target_file="inventory.json",
                requery_scope=item.query_id or item.area,
            )
        )
    for item in plan.unverified_items:
        findings.append(
            _finding(
                PreparationSeverity.WARNING,
                f"unverified plan item: {item.area}: {item.detail}",
                "Find source evidence or remove the unsupported assertion.",
                target_file="inventory.json",
                requery_scope=item.query_id or item.area,
            )
        )
    return _phase(
        "normalization_plan",
        "Normalization Plan",
        {
            "missing_items": len(plan.missing_items),
            "source_conflicts": len(plan.source_conflicts),
            "unverified_items": len(plan.unverified_items),
        },
        findings,
    )


def _assess_integration(plan: NormalizationPlan) -> PreparationPhase:
    contract = plan.integration
    findings: list[PreparationFinding] = []
    missing = list(contract.missing) if contract is not None else []
    for idx, item in enumerate(missing):
        findings.append(
            _finding(
                PreparationSeverity.WARNING,
                f"integration contract missing item: {item.area}: {item.detail}",
                "re-read source material and complete integration.json or record why it is absent.",
                target_file="integration.json",
                field_path=f"/missing/{idx}",
                requery_scope=item.area,
            )
        )
    return _phase(
        "integration_contract",
        "Integration Contract",
        {
            "crypto": len(contract.crypto) if contract is not None else 0,
            "callbacks": len(contract.callbacks) if contract is not None else 0,
            "field_conditions": len(contract.field_conditions)
            if contract is not None
            else 0,
            "test_cases": len(contract.test_cases) if contract is not None else 0,
            "missing_items": len(missing),
        },
        findings,
    )


def assess_preparation(
    *,
    manifest: Manifest,
    inventory: dict,
    endpoint_texts: list[str],
    plan: NormalizationPlan,
) -> PreparationReport:
    phases = [
        _assess_sources(manifest),
        _assess_extraction(inventory, endpoint_texts),
        _assess_plan(plan),
        _assess_integration(plan),
    ]
    return PreparationReport(
        status=_overall_status(phases),
        summary=_summary(phases),
        phases=phases,
    )
