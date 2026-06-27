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
    # Two sources on purpose: these tests exercise the SUPPORTED vs UNVERIFIED
    # plumbing, so an item citing "api.pdf" must match while a null/unmatched
    # source stays UNVERIFIED. (Single-source attribution — where one lone source
    # makes every item SUPPORTED — is covered in tests/plan/test_classify.py.)
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return Manifest(
        sources_root="/src", generated_at=now,
        local_sources=[
            LocalSource(relative_path="api.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
                        scanned_at=now, supported=True, status=ProcessingStatus.PENDING),
            LocalSource(relative_path="extra.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="y",
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
                 '```json\n{"method": "GET", "path": "/u",'
                 f' "responses": [{{"status": "200"}}], "source": {src}}}\n```'),
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


def test_duplicate_method_path_endpoints_merged_with_unioned_details():
    # Two source endpoints share POST /c (e.g. distinct products on one gateway
    # URL). They must collapse into ONE plan endpoint, and the per-endpoint
    # details for both must union (not overwrite) — so no detail's params or
    # responses are lost and the validator sees a single complete endpoint.
    block05 = (
        '```json\n{"endpoints": ['
        '{"method":"POST","path":"/c","summary":"all","source":"api.pdf"},'
        '{"method":"POST","path":"/c","summary":"atm","source":"api.pdf"}]}\n```'
    )
    ep0 = ('```json\n{"method":"POST","path":"/c",'
           '"parameters":[{"name":"A","in":"body"}],"responses":[],'
           '"source":"api.pdf"}\n```')
    ep1 = ('```json\n{"method":"POST","path":"/c",'
           '"parameters":[{"name":"B","in":"body"}],'
           '"responses":[{"status":"200"}],"source":"api.pdf"}\n```')
    extraction = ExtractionResult(notebook_url="https://nb/x", artifacts=[
        _art("05", QueryKind.INITIAL, block05),
        AnswerArtifact(query_id="06-ep0", stage_id="06", kind=QueryKind.INITIAL,
                       answer=ep0, answer_path="answers/06-ep0.txt", returncode=0),
        AnswerArtifact(query_id="06-ep1", stage_id="06", kind=QueryKind.INITIAL,
                       answer=ep1, answer_path="answers/06-ep1.txt", returncode=0),
    ])
    plan = build_normalization_plan(extraction, _manifest())
    eps = [e for e in plan.endpoints if e.path == "/c"]
    assert len(eps) == 1
    ep = eps[0]
    assert {p.get("name") for p in ep.parameters} == {"A", "B"}
    assert any(r.get("status") == "200" for r in ep.responses)


def test_webhook_details_merge_by_source_not_collapsed():
    # Two webhooks share (POST, no path); their details must pair to the right
    # endpoint via the source they cite, so neither loses its responses.
    block05 = (
        '```json\n{"endpoints": ['
        '{"method":"POST","path":null,"summary":"notify A","source":"api.pdf"},'
        '{"method":"POST","path":null,"summary":"notify B","source":"extra.pdf"}]}\n```'
    )
    ep_a = ('```json\n{"method":"POST","path":null,'
            '"responses":[{"status":"200","description":"A ack"}],'
            '"source":"api.pdf"}\n```')
    ep_b = ('```json\n{"method":"POST","path":null,'
            '"responses":[{"status":"201","description":"B ack"}],'
            '"source":"extra.pdf"}\n```')
    extraction = ExtractionResult(notebook_url="https://nb/x", artifacts=[
        _art("05", QueryKind.INITIAL, block05),
        AnswerArtifact(query_id="06-a", stage_id="06", kind=QueryKind.INITIAL,
                       answer=ep_a, answer_path="answers/06-a.txt", returncode=0),
        AnswerArtifact(query_id="06-b", stage_id="06", kind=QueryKind.INITIAL,
                       answer=ep_b, answer_path="answers/06-b.txt", returncode=0),
    ])
    plan = build_normalization_plan(extraction, _manifest())
    hooks = [e for e in plan.endpoints if e.path is None]
    assert len(hooks) == 2
    by_summary = {e.summary: e for e in hooks}
    assert by_summary["notify A"].responses == [{"status": "200", "description": "A ack"}]
    assert by_summary["notify B"].responses == [{"status": "201", "description": "B ack"}]


def test_nested_scalar_wrong_type_in_inventory_does_not_raise():
    # `fields` must be a list[dict]; a bare string used to crash entry build.
    block = '```json\n{"schemas": [{"name": "U", "fields": "bad"}]}\n```'
    plan = build_normalization_plan(
        ExtractionResult(notebook_url="https://nb/x",
                         artifacts=[_art("07", QueryKind.INITIAL, block)]),
        _manifest(),
    )
    assert plan.schemas == []
    assert any(m.area == "07" for m in plan.missing_items)


def test_nested_scalar_wrong_type_in_enums_does_not_raise():
    block = '```json\n{"schemas": [{"name": "U", "enums": "bad"}]}\n```'
    plan = build_normalization_plan(
        ExtractionResult(notebook_url="https://nb/x",
                         artifacts=[_art("07", QueryKind.INITIAL, block)]),
        _manifest(),
    )
    assert plan.schemas == []
    assert any(m.area == "07" for m in plan.missing_items)


def test_title_from_stage00_populates_system_groups():
    extraction = ExtractionResult(notebook_url="https://nb/x", artifacts=[
        _art("00", QueryKind.INITIAL, "綠界全方位金流 API 技術文件"),
    ])
    plan = build_normalization_plan(extraction, _manifest())
    assert plan.system_groups[0].name == "綠界全方位金流 API 技術文件"


def test_blank_title_leaves_system_groups_empty():
    extraction = ExtractionResult(notebook_url="https://nb/x", artifacts=[
        _art("00", QueryKind.INITIAL, "  "),
    ])
    plan = build_normalization_plan(extraction, _manifest())
    assert plan.system_groups == []


def test_string_enums_in_schema_are_kept_not_dropped():
    # The SKILL contract documents schemas[].enums as ["str"]. Such a schema
    # must survive the plan build (it used to be silently dropped because the
    # SchemaEntry model required list[dict]).
    block = (
        '```json\n{"schemas": [{"name": "PaymentType", "fields": [], '
        '"enums": ["CREDIT=信用卡", "VACC=ATM"], "source": "api.pdf"}]}\n```'
    )
    plan = build_normalization_plan(
        ExtractionResult(notebook_url="https://nb/x",
                         artifacts=[_art("07", QueryKind.INITIAL, block)]),
        _manifest(),
    )
    assert len(plan.schemas) == 1
    assert plan.schemas[0].name == "PaymentType"
    assert plan.schemas[0].enums == ["CREDIT=信用卡", "VACC=ATM"]
    assert not any(
        m.area == "07" and "malformed" in m.detail for m in plan.missing_items
    )


def test_nested_scalar_wrong_type_in_new_endpoint_does_not_raise():
    # A stage-06 detail with no matching stage-05 endpoint becomes a new
    # endpoint; a scalar `parameters` must not crash construction.
    block = ('```json\n{"method": "GET", "path": "/u", "parameters": "bad"}\n```')
    plan = build_normalization_plan(
        ExtractionResult(notebook_url="https://nb/x",
                         artifacts=[_art("06", QueryKind.INITIAL, block)]),
        _manifest(),
    )
    assert plan.endpoints == []
    assert any(m.area == "06" for m in plan.missing_items)


def test_nested_scalar_wrong_type_in_merged_detail_does_not_raise():
    # A scalar `responses` in a detail that merges into an existing endpoint
    # must not crash; the existing endpoint is preserved unchanged.
    extraction = ExtractionResult(
        notebook_url="https://nb/x",
        artifacts=[
            _art("05", QueryKind.INITIAL,
                 '```json\n{"endpoints": [{"method": "GET", "path": "/u",'
                 ' "summary": "list", "source": "api.pdf"}]}\n```'),
            _art("06", QueryKind.INITIAL,
                 '```json\n{"method": "GET", "path": "/u",'
                 ' "responses": "bad", "source": "api.pdf"}\n```'),
        ],
    )
    plan = build_normalization_plan(extraction, _manifest())
    assert len(plan.endpoints) == 1
    ep = plan.endpoints[0]
    assert ep.path == "/u"
    assert ep.responses == []  # bad detail rejected, endpoint left intact
    assert any(m.area == "06" for m in plan.missing_items)
