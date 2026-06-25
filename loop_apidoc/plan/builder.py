from __future__ import annotations

from typing import Callable

from loop_apidoc.extraction.jsonblock import extract_json_block
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.classify import classify_item
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    ErrorEntry,
    MissingItem,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SchemaEntry,
    SecuritySchemeEntry,
    SourceConflict,
    UnverifiedItem,
)

# inventory stage_id -> (json_key, plan_field, entry_class, field factory). Stage 06
# is handled separately (merged into endpoints), so it is intentionally absent here.
_INVENTORY: dict[str, tuple[str, str, type, Callable[[dict], dict]]] = {
    "03": ("environments", "environments", EnvironmentEntry,
           lambda i: {"name": i.get("name"), "base_url": i.get("base_url"),
                      "version": i.get("version")}),
    "04": ("security_schemes", "security_schemes", SecuritySchemeEntry,
           lambda i: {"name": i.get("name"), "type": i.get("type"),
                      "location": i.get("location"), "details": i.get("details")}),
    "05": ("endpoints", "endpoints", EndpointEntry,
           lambda i: {"method": i.get("method"), "path": i.get("path"),
                      "summary": i.get("summary")}),
    "07": ("schemas", "schemas", SchemaEntry,
           lambda i: {"name": i.get("name"), "fields": i.get("fields") or [],
                      "enums": i.get("enums") or [], "constraints": i.get("constraints")}),
    "08": ("errors", "errors", ErrorEntry,
           lambda i: {"code": i.get("code"), "meaning": i.get("meaning"),
                      "http_status": i.get("http_status")}),
    "09": ("operational", "operational", OperationalEntry,
           lambda i: {"topic": i.get("topic"), "detail": i.get("detail")}),
}


def _note(extraction: ExtractionResult, stage_id: str) -> str:
    art = extraction.initial(stage_id)
    return art.answer if art else ""


def _structured_block(
    extraction: ExtractionResult, stage_id: str
) -> tuple[AnswerArtifact | None, dict | None]:
    art = extraction.latest_structured(stage_id)
    block = extract_json_block(art.answer) if art is not None else None
    return art, block


def _add_missing_and_conflicts(plan: NormalizationPlan, stage_id: str,
                               art: AnswerArtifact, block: dict) -> None:
    for miss in block.get("missing") or []:
        plan.missing_items.append(
            MissingItem(area=stage_id, detail=str(miss), query_id=art.query_id)
        )
    for conflict in block.get("conflicts") or []:
        plan.source_conflicts.append(
            SourceConflict(area=stage_id, detail=str(conflict), query_id=art.query_id)
        )


def build_normalization_plan(
    extraction: ExtractionResult, manifest: Manifest
) -> NormalizationPlan:
    plan = NormalizationPlan(
        notebook_url=extraction.notebook_url,
        source_inventory_note=_note(extraction, "01"),
        overview_note=_note(extraction, "02"),
        conflicts_note=_note(extraction, "10"),
    )

    for stage_id, (json_key, plan_field, entry_class, factory) in _INVENTORY.items():
        art, block = _structured_block(extraction, stage_id)
        if block is None:
            plan.missing_items.append(
                MissingItem(area=stage_id, detail="no structured answer",
                            query_id=art.query_id if art else None)
            )
            continue

        target = getattr(plan, plan_field)
        for item in block.get(json_key) or []:
            status, citation = classify_item(
                item.get("source"), query_id=art.query_id,
                answer_path=art.answer_path, manifest=manifest,
            )
            target.append(entry_class(status=status, citations=[citation], **factory(item)))
            if status is PlanItemStatus.UNVERIFIED:
                label = item.get("path") or item.get("name") or item.get("code") or json_key
                plan.unverified_items.append(
                    UnverifiedItem(area=stage_id, detail=str(label), query_id=art.query_id)
                )
        _add_missing_and_conflicts(plan, stage_id, art, block)

    _merge_endpoint_details(plan, extraction, manifest)
    return plan


def _merge_endpoint_details(
    plan: NormalizationPlan, extraction: ExtractionResult, manifest: Manifest
) -> None:
    art, block = _structured_block(extraction, "06")
    if block is None:
        plan.missing_items.append(
            MissingItem(area="06", detail="no structured answer",
                        query_id=art.query_id if art else None)
        )
        return

    for item in block.get("endpoint_details") or []:
        detail = {
            "parameters": item.get("parameters") or [],
            "request": item.get("request"),
            "responses": item.get("responses") or [],
            "examples": item.get("examples") or [],
        }
        match = next(
            (e for e in plan.endpoints
             if e.method == item.get("method") and e.path == item.get("path")),
            None,
        )
        if match is not None:
            match.parameters = detail["parameters"]
            match.request = detail["request"]
            match.responses = detail["responses"]
            match.examples = detail["examples"]
            continue
        status, citation = classify_item(
            item.get("source"), query_id=art.query_id,
            answer_path=art.answer_path, manifest=manifest,
        )
        plan.endpoints.append(
            EndpointEntry(method=item.get("method"), path=item.get("path"), summary=None,
                          status=status, citations=[citation], **detail)
        )
        if status is PlanItemStatus.UNVERIFIED:
            plan.unverified_items.append(
                UnverifiedItem(area="06", detail=str(item.get("path") or "endpoint"),
                               query_id=art.query_id)
            )
    _add_missing_and_conflicts(plan, "06", art, block)
