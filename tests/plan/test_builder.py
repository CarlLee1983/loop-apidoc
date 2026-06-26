from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.plan.models import PlanItemStatus


def _manifest() -> Manifest:
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return Manifest(
        sources_root="/src", generated_at=now,
        local_sources=[
            LocalSource(relative_path="api.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
                        scanned_at=now, supported=True, status=ProcessingStatus.PENDING),
        ],
    )


def _art(stage_id: str, kind: QueryKind, answer: str) -> AnswerArtifact:
    qid = f"{stage_id}-{kind.value}"
    return AnswerArtifact(query_id=qid, stage_id=stage_id, kind=kind, answer=answer,
                          answer_path=f"answers/{qid}.txt", returncode=0)


def _extraction() -> ExtractionResult:
    return ExtractionResult(
        notebook_url="https://nb/x",
        artifacts=[
            _art("01", QueryKind.INITIAL, "Two sources: api.pdf and a URL."),
            _art("02", QueryKind.INITIAL, "It is a payments API."),
            _art("05", QueryKind.INITIAL,
                 '```json\n{"endpoints": ['
                 '{"method": "GET", "path": "/u", "summary": "list", "source": "api.pdf"},'
                 '{"method": "POST", "path": "/u", "summary": "create", "source": null}],'
                 ' "missing": ["pagination"]}\n```'),
            _art("10", QueryKind.INITIAL, "No conflicts found."),
        ],
    )


def test_builds_notes():
    plan = build_normalization_plan(_extraction(), _manifest())
    assert plan.source_inventory_note.startswith("Two sources")
    assert plan.overview_note == "It is a payments API."
    assert plan.conflicts_note == "No conflicts found."
    assert plan.notebook_url == "https://nb/x"


def test_endpoints_classified():
    plan = build_normalization_plan(_extraction(), _manifest())
    assert len(plan.endpoints) == 2
    supported = [e for e in plan.endpoints if e.status is PlanItemStatus.SUPPORTED]
    unverified = [e for e in plan.endpoints if e.status is PlanItemStatus.UNVERIFIED]
    assert supported[0].path == "/u" and supported[0].method == "GET"
    assert supported[0].citations[0].manifest_source == "api.pdf"
    assert len(unverified) == 1


def test_missing_and_unverified_aggregated():
    plan = build_normalization_plan(_extraction(), _manifest())
    assert any(m.detail == "pagination" and m.area == "05" for m in plan.missing_items)
    assert any(u.area == "05" for u in plan.unverified_items)


def test_absent_structured_stage_records_missing():
    plan = build_normalization_plan(_extraction(), _manifest())
    # stages 03,04,06,07,08,09 had no artifacts -> each contributes a missing item
    areas = {m.area for m in plan.missing_items}
    assert {"03", "04", "06", "07", "08", "09"}.issubset(areas)
    assert plan.environments == []


def _merge_extraction(detail_source: str | None) -> ExtractionResult:
    src = "null" if detail_source is None else f'"{detail_source}"'
    return ExtractionResult(
        notebook_url="https://nb/x",
        artifacts=[
            _art("05", QueryKind.INITIAL,
                 '```json\n{"endpoints": ['
                 '{"method": "GET", "path": "/u", "summary": "list", "source": "api.pdf"}]}\n```'),
            _art("06", QueryKind.INITIAL,
                 '```json\n{"endpoint_details": [{"method": "GET", "path": "/u",'
                 f' "responses": [{{"status": "200"}}], "source": {src}}}]}}\n```'),
        ],
    )


def test_merge_unverified_detail_downgrades_endpoint_status():
    # stage 05 endpoint is SUPPORTED (api.pdf); stage 06 detail source is unverified.
    plan = build_normalization_plan(_merge_extraction(None), _manifest())
    assert len(plan.endpoints) == 1
    ep = plan.endpoints[0]
    assert ep.responses == [{"status": "200"}]
    # the merged endpoint must NOT stay SUPPORTED while carrying unverified detail
    assert ep.status is PlanItemStatus.UNVERIFIED
    # ... and the downgrade is surfaced as an unverified item
    assert any(u.area == "06" for u in plan.unverified_items)
    # both citations retained
    assert len(ep.citations) == 2


def test_merge_supported_detail_keeps_supported():
    plan = build_normalization_plan(_merge_extraction("api.pdf"), _manifest())
    ep = plan.endpoints[0]
    assert ep.status is PlanItemStatus.SUPPORTED
    assert ep.responses == [{"status": "200"}]


def _malformed_extraction(stage_block: str) -> ExtractionResult:
    return ExtractionResult(
        notebook_url="https://nb/x",
        artifacts=[_art("05", QueryKind.INITIAL, stage_block)],
    )


def test_malformed_collection_shape_does_not_raise():
    # NotebookLM returns valid JSON but `endpoints` is a dict, not a list.
    plan = build_normalization_plan(
        _malformed_extraction('```json\n{"endpoints": {"GET /u": {"x": 1}}}\n```'),
        _manifest(),
    )
    assert plan.endpoints == []
    assert any(m.area == "05" for m in plan.missing_items)


def test_malformed_items_are_skipped_not_fatal():
    # `endpoints` is a list but items are bare strings, not dicts.
    plan = build_normalization_plan(
        _malformed_extraction('```json\n{"endpoints": ["GET /u", "POST /u"]}\n```'),
        _manifest(),
    )
    assert plan.endpoints == []
    assert any(m.area == "05" for m in plan.missing_items)


def test_malformed_endpoint_details_shape_does_not_raise():
    block = '```json\n{"endpoint_details": "not-a-list"}\n```'
    plan = build_normalization_plan(
        ExtractionResult(notebook_url="https://nb/x",
                         artifacts=[_art("06", QueryKind.INITIAL, block)]),
        _manifest(),
    )
    assert plan.endpoints == []
    assert any(m.area == "06" for m in plan.missing_items)
