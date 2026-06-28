from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse

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
    SystemGroup,
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


def _param_key(p: dict) -> tuple:
    return (p.get("name"), p.get("in") or p.get("location"))


def _union_list(base: list, extra, key) -> list:
    """Append `extra`'s items to `base`, skipping duplicates by `key`. Malformed
    input (a non-list `extra`, or a non-dict item) is passed through verbatim so
    the downstream EndpointEntry validation rejects it — preserving the existing
    "malformed detail is skipped, endpoint left intact" behaviour."""
    if not isinstance(extra, list):
        return extra
    out = list(base)
    seen = {key(x) for x in out if isinstance(x, dict)}
    for item in extra:
        if not isinstance(item, dict):
            out.append(item)  # let pydantic reject downstream
            continue
        k = key(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def _union_str(base: list, extra) -> list:
    """Union two string lists, preserving order and dropping duplicates. A
    non-list `extra` is passed through verbatim so validation rejects it."""
    if not isinstance(extra, list):
        return extra
    out = list(base)
    for item in extra:
        if item not in out:
            out.append(item)
    return out


def _union_endpoint_fields(existing: EndpointEntry, detail: dict) -> dict:
    """Union a detail's parameters/responses/examples into an endpoint's, instead
    of replacing them. For the usual single-detail-per-endpoint case the endpoint
    starts empty so the union equals the detail; when several details legitimately
    target one endpoint (multiple products on a shared method+path) their fields
    accumulate rather than the last one overwriting the rest."""
    examples = detail.get("examples")
    return {
        "parameters": _union_list(existing.parameters, detail.get("parameters"),
                                  _param_key),
        "responses": _union_list(existing.responses, detail.get("responses"),
                                 lambda r: r.get("status")),
        "examples": [*existing.examples, *examples] if isinstance(examples, list)
        else examples,
        "request": existing.request if existing.request is not None
        else detail.get("request"),
        "tags": _union_str(existing.tags, detail.get("tags")),
        "security": _union_str(existing.security, detail.get("security")),
    }


def _combine_endpoints(a: EndpointEntry, b: EndpointEntry) -> EndpointEntry:
    """Collapse two endpoints sharing method+path into one canonical entry."""
    fields = _union_endpoint_fields(a, {
        "parameters": list(b.parameters), "responses": list(b.responses),
        "examples": list(b.examples), "request": b.request,
        "tags": list(b.tags), "security": list(b.security),
    })
    summaries = [s for s in (a.summary, b.summary) if s]
    citations = list(a.citations)
    for c in b.citations:
        if c not in citations:
            citations.append(c)
    return EndpointEntry(
        status=_stricter(a.status, b.status), method=a.method, path=a.path,
        summary="；".join(dict.fromkeys(summaries)) or None,
        citations=citations, **fields,
    )


def _dedupe_endpoints(plan: NormalizationPlan) -> None:
    """OpenAPI allows one operation per method+path and the validator checks
    plan.endpoints, so several source endpoints sharing one method+path (e.g.
    multiple payment products posting to one gateway URL) must collapse into a
    single canonical endpoint. Endpoints missing method/path are left untouched."""
    out: list[EndpointEntry] = []
    index: dict[tuple, int] = {}
    for ep in plan.endpoints:
        key = (ep.method, ep.path) if ep.method and ep.path else None
        if key is not None and key in index:
            i = index[key]
            out[i] = _combine_endpoints(out[i], ep)
        else:
            if key is not None:
                index[key] = len(out)
            out.append(ep)
    plan.endpoints = out


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

    # Stage 00 carries the source-stated API/document title (and, when present,
    # the document version), feeding OpenAPI `info.title`/`info.version` and the
    # guide heading via system_groups. Plain text = title only (back-compat);
    # a JSON object = {"title", "version"}.
    raw = _note(extraction, "00").strip()
    title: str | None = None
    version: str | None = None
    block = extract_json_block(raw) if raw else None
    if isinstance(block, dict):
        title = str(block.get("title")).strip() if block.get("title") else None
        version = str(block.get("version")).strip() if block.get("version") else None
    elif raw:
        title = raw
    if title or version:
        plan.system_groups = [SystemGroup(name=title or "", version=version)]

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
    _dedupe_endpoints(plan)
    return plan


def _detail_path(item: dict) -> str | None:
    """Stage-06 answers carry the endpoint as `path` or as a full `url`; derive
    the path component so it can match a stage-05 endpoint."""
    path = item.get("path")
    if path:
        return path
    url = item.get("url")
    if isinstance(url, str) and "://" in url:
        return urlparse(url).path or None
    return url if isinstance(url, str) else None


def _webhook_locators(existing) -> set[str]:
    return {c.locator for c in existing.citations if getattr(c, "locator", None)}


def _match_index(plan: NormalizationPlan, method, path, detail_locator,
                 detail_source, consumed: set[int]) -> int | None:
    """Index of the stage-05 endpoint a stage-06 detail belongs to, or None.

    Path-bearing details join on (method, path); several may legitimately share
    one path (multi-product gateways), so these are NOT consumed — the duplicate
    endpoints collapse later in `_dedupe_endpoints`.

    Path-less webhook details join to a path-less endpoint with the same method.
    Because ONE source page can document MANY events (GitHub/Stripe list dozens
    on a single page), every such webhook reduces to the same manifest_source;
    source-only pairing would pile every detail onto the first webhook. So they
    pair FIRST by their distinct `locator` (the finer source string) and only
    then fall back to manifest_source — and each webhook endpoint is consumed
    once so details never collapse onto one."""
    if method is None:
        return None
    if path is not None:
        for idx, e in enumerate(plan.endpoints):
            if e.method == method and e.path == path:
                return idx
        return None
    candidates = [idx for idx, e in enumerate(plan.endpoints)
                  if idx not in consumed and e.method == method and e.path is None]
    if detail_locator:
        for idx in candidates:
            if detail_locator in _webhook_locators(plan.endpoints[idx]):
                return idx
    if detail_source is not None:
        for idx in candidates:
            if any(c.manifest_source == detail_source
                   for c in plan.endpoints[idx].citations):
                return idx
    return None


def _merge_one_detail(
    plan: NormalizationPlan, art, item: dict, manifest: Manifest,
    consumed: set[int],
) -> None:
    method = item.get("method")
    path = _detail_path(item)
    detail = {
        "parameters": item.get("parameters") or [],
        "request": item.get("request"),
        "responses": item.get("responses") or [],
        "examples": item.get("examples") or [],
        "tags": item.get("tags") or [],
        "security": item.get("security") or [],
    }
    status, citation = classify_item(
        item.get("source"), query_id=art.query_id,
        answer_path=art.answer_path, manifest=manifest,
    )
    idx = _match_index(plan, method, path, citation.locator,
                       citation.manifest_source, consumed)
    if idx is not None:
        existing = plan.endpoints[idx]
        # The detail is only as grounded as its own source; take the
        # strictest of the endpoint's and the detail's status.
        merged_status = _stricter(existing.status, status)
        merged = _build_entry(
            plan, "06", art.query_id, "endpoint_details", EndpointEntry,
            **{**existing.model_dump(),
               **_union_endpoint_fields(existing, detail),
               "status": merged_status,
               "citations": [*existing.citations, citation]},
        )
        if merged is None:
            return
        plan.endpoints[idx] = merged
        if path is None:
            consumed.add(idx)
        if (merged_status is not existing.status
                and merged_status in (PlanItemStatus.UNVERIFIED,
                                      PlanItemStatus.CONFLICTING)):
            plan.unverified_items.append(
                UnverifiedItem(area="06", detail=str(path or "endpoint"),
                               query_id=art.query_id))
        return
    # No stage-05 endpoint matched: add the detailed endpoint on its own.
    entry = _build_entry(
        plan, "06", art.query_id, "endpoint_details", EndpointEntry,
        method=method, path=path, summary=None,
        status=status, citations=[citation], **detail,
    )
    if entry is None:
        return
    plan.endpoints.append(entry)
    if status is PlanItemStatus.UNVERIFIED:
        plan.unverified_items.append(
            UnverifiedItem(area="06", detail=str(path or "endpoint"),
                           query_id=art.query_id))


def _merge_endpoint_details(
    plan: NormalizationPlan, extraction: ExtractionResult, manifest: Manifest
) -> None:
    """Stage 06 is fanned out per endpoint, so there are N artifacts, each a
    single endpoint-detail object. Merge each into its stage-05 endpoint."""
    arts = extraction.for_stage("06")
    if not arts:
        plan.missing_items.append(
            MissingItem(area="06", detail="no structured answer", query_id=None))
        return
    consumed: set[int] = set()  # path-less webhook endpoints matched at most once
    for art in arts:
        block = extract_json_block(art.answer)
        if not isinstance(block, dict):
            plan.missing_items.append(
                MissingItem(area="06", detail="malformed endpoint detail",
                            query_id=art.query_id))
            continue
        # A method with no path is a valid webhook detail; only a missing method
        # makes the detail unmergeable.
        if not block.get("method"):
            plan.missing_items.append(
                MissingItem(area="06", detail="endpoint detail missing method/path",
                            query_id=art.query_id))
            continue
        _merge_one_detail(plan, art, block, manifest, consumed)
        _add_missing_and_conflicts(plan, "06", art, block)
