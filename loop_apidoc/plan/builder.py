from __future__ import annotations

from typing import Callable

from pydantic import ValidationError

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

# Status strictness for merging: a merged endpoint is only as trustworthy as
# its least-grounded source, so merging picks the worst (highest rank).
_STATUS_RANK = {
    PlanItemStatus.SUPPORTED: 0,
    PlanItemStatus.MISSING: 1,
    PlanItemStatus.UNVERIFIED: 2,
    PlanItemStatus.CONFLICTING: 3,
}


def _stricter(a: PlanItemStatus, b: PlanItemStatus) -> PlanItemStatus:
    return a if _STATUS_RANK[a] >= _STATUS_RANK[b] else b


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


def _dict_items(
    plan: NormalizationPlan, stage_id: str, query_id: str | None,
    raw: object, json_key: str,
) -> list[dict]:
    """Coerce a structured collection into a list of dict items.

    NotebookLM may return valid JSON whose shape is wrong (a dict where a list
    is expected, or scalar items). Rather than crash at the extraction→plan
    boundary, record the malformed shape as a MissingItem and skip the bad
    parts so the rest of the plan still builds.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        plan.missing_items.append(
            MissingItem(area=stage_id, detail=f"malformed shape for {json_key}",
                        query_id=query_id)
        )
        return []
    items: list[dict] = []
    for entry in raw:
        if isinstance(entry, dict):
            items.append(entry)
        else:
            plan.missing_items.append(
                MissingItem(area=stage_id, detail=f"malformed item in {json_key}",
                            query_id=query_id)
            )
    return items


def _build_entry(
    plan: NormalizationPlan, stage_id: str, query_id: str | None,
    json_key: str, entry_class: type, **kwargs,
):
    """Construct an entry, tolerating malformed nested fields.

    `_dict_items` only guards the outer collection shape; a NotebookLM item can
    still carry a wrong-typed nested field (e.g. a scalar where list[dict] is
    expected) that fails pydantic validation. Catch that here, record a
    MissingItem, and skip the item rather than crashing the whole plan build."""
    try:
        return entry_class(**kwargs)
    except ValidationError:
        plan.missing_items.append(
            MissingItem(area=stage_id, detail=f"malformed item in {json_key}",
                        query_id=query_id)
        )
        return None


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
    raw_missing = block.get("missing")
    for miss in raw_missing if isinstance(raw_missing, list) else []:
        plan.missing_items.append(
            MissingItem(area=stage_id, detail=str(miss), query_id=art.query_id)
        )
    # forward-wiring: no current stage emits `conflicts`; populated by Plan 5 conflict detection
    raw_conflicts = block.get("conflicts")
    for conflict in raw_conflicts if isinstance(raw_conflicts, list) else []:
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
        for item in _dict_items(plan, stage_id, art.query_id, block.get(json_key), json_key):
            status, citation = classify_item(
                item.get("source"), query_id=art.query_id,
                answer_path=art.answer_path, manifest=manifest,
            )
            entry = _build_entry(plan, stage_id, art.query_id, json_key, entry_class,
                                 status=status, citations=[citation], **factory(item))
            if entry is None:
                continue
            target.append(entry)
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

    for item in _dict_items(plan, "06", art.query_id,
                            block.get("endpoint_details"), "endpoint_details"):
        detail = {
            "parameters": item.get("parameters") or [],
            "request": item.get("request"),
            "responses": item.get("responses") or [],
            "examples": item.get("examples") or [],
        }
        matched = False
        for idx, existing in enumerate(plan.endpoints):
            if existing.method == item.get("method") and existing.path == item.get("path"):
                detail_status, citation = classify_item(
                    item.get("source"), query_id=art.query_id,
                    answer_path=art.answer_path, manifest=manifest,
                )
                # The detail (parameters/responses/...) is only as grounded as
                # its own source; merging must not let it ride on the endpoint's
                # existing SUPPORTED status. Take the strictest of the two.
                merged_status = _stricter(existing.status, detail_status)
                # model_copy does not re-validate; build a fresh entry so a
                # malformed nested detail is rejected instead of silently
                # stored. On failure the existing endpoint is left intact.
                merged = _build_entry(
                    plan, "06", art.query_id, "endpoint_details", EndpointEntry,
                    **{**existing.model_dump(), **detail, "status": merged_status,
                       "citations": [*existing.citations, citation]},
                )
                matched = True
                if merged is None:
                    break
                plan.endpoints[idx] = merged
                if (merged_status is not existing.status
                        and merged_status in (PlanItemStatus.UNVERIFIED,
                                              PlanItemStatus.CONFLICTING)):
                    plan.unverified_items.append(
                        UnverifiedItem(area="06",
                                       detail=str(item.get("path") or "endpoint"),
                                       query_id=art.query_id)
                    )
                break
        if matched:
            continue
        status, citation = classify_item(
            item.get("source"), query_id=art.query_id,
            answer_path=art.answer_path, manifest=manifest,
        )
        entry = _build_entry(
            plan, "06", art.query_id, "endpoint_details", EndpointEntry,
            method=item.get("method"), path=item.get("path"), summary=None,
            status=status, citations=[citation], **detail,
        )
        if entry is None:
            continue
        plan.endpoints.append(entry)
        if status is PlanItemStatus.UNVERIFIED:
            plan.unverified_items.append(
                UnverifiedItem(area="06", detail=str(item.get("path") or "endpoint"),
                               query_id=art.query_id)
            )
    _add_missing_and_conflicts(plan, "06", art, block)
