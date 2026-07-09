from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.agentcli.extraction import inventory_to_stage_answers
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.generate import build_result
from loop_apidoc.generate.openapi import build_openapi
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.plan.models import PlanItemStatus
from loop_apidoc.validate.completeness import check_completeness
from loop_apidoc.validate import validate_outputs
from loop_apidoc.validate.models import IssueCode, Severity

# 這個測試檔存在的理由:finding 1 指出 `server` 從沒真的走過真實管線
# (inventory → plan → OpenAPI),只有直接建構 EndpointEntry(server=...) 的
# unit test 會過。這裡刻意重現 assemble 真正會做的事:
#   inventory dict → inventory_to_stage_answers → build_normalization_plan
#   → build_openapi
# 任何一段把 server 弄丟,這個測試就要 RED。

_NOW = datetime(2026, 7, 9, tzinfo=timezone.utc)


def _manifest() -> Manifest:
    return Manifest(
        sources_root="/src", generated_at=_NOW,
        local_sources=[
            LocalSource(relative_path="api.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
                        scanned_at=_NOW, supported=True,
                        status=ProcessingStatus.PENDING),
        ],
    )


def _inventory_with_server() -> dict:
    return {
        "overview": "多主機付款 API",
        "environments": [
            {"name": "production", "base_url": "https://api.example.com",
             "version": None, "source": "api.pdf"},
            {"name": "reporting", "base_url": "https://report.example.com",
             "version": None, "source": "api.pdf"},
        ],
        "security_schemes": [],
        "endpoints": [
            {"method": "GET", "path": "/bets", "summary": "查詢投注",
             "server": "reporting", "source": "api.pdf"},
        ],
        "schemas": [],
        "errors": [],
        "operational": [],
        "missing": [],
    }


def _artifacts_from_inventory(inventory: dict) -> list[AnswerArtifact]:
    """把 inventory_to_stage_answers 的輸出包成 AnswerArtifact,重現
    build_extraction_from_files 的形狀(不落地檔案,維持這批測試的純函式風格,
    對齊 tests/plan/test_builder.py 的 `_art` 慣例)。"""
    artifacts = []
    for stage_id, answer in inventory_to_stage_answers(inventory).items():
        qid = f"{stage_id}-initial"
        artifacts.append(AnswerArtifact(
            query_id=qid, stage_id=stage_id, kind=QueryKind.INITIAL,
            answer=answer, answer_path=f"answers/{qid}.txt", returncode=0,
        ))
    return artifacts


def test_inventory_server_reaches_operation_level_openapi_servers():
    inventory = _inventory_with_server()
    extraction = ExtractionResult(
        notebook_url="", artifacts=_artifacts_from_inventory(inventory))

    plan = build_normalization_plan(extraction, _manifest())

    # 先確認 plan 這一關真的把 server 帶到 EndpointEntry —— 這正是原本
    # 被 "05" factory lambda 悄悄丟掉的欄位。
    assert len(plan.endpoints) == 1
    assert plan.endpoints[0].server == "reporting"

    doc = build_openapi(plan)
    op = doc["paths"]["/bets"]["get"]
    assert op["servers"] == [
        {"url": "https://report.example.com", "description": "reporting"}
    ]


def test_stage06_detail_merge_does_not_clobber_server():
    """server 只活在 stage 05(inventory);stage 06(endpoints/ep<N>.json)
    從不帶這個欄位。合併 detail 時不能把已設定的 server 蓋回 None。"""
    inventory = _inventory_with_server()
    artifacts = _artifacts_from_inventory(inventory)
    # 補一個 stage-06 endpoint detail,method+path 對得上 stage-05 那筆,
    # 讓 _merge_one_detail 真的把它併進去。
    artifacts.append(AnswerArtifact(
        query_id="06-ep0", stage_id="06", kind=QueryKind.INITIAL,
        answer=(
            '```json\n{"method": "GET", "path": "/bets", '
            '"responses": [{"status": "200"}], "source": "api.pdf"}\n```'
        ),
        answer_path="answers/06-ep0.txt", returncode=0,
    ))
    extraction = ExtractionResult(notebook_url="", artifacts=artifacts)

    plan = build_normalization_plan(extraction, _manifest())

    assert len(plan.endpoints) == 1
    ep = plan.endpoints[0]
    assert ep.responses == [{"status": "200"}]
    assert ep.server == "reporting"
    assert ep.status is PlanItemStatus.SUPPORTED

    doc = build_openapi(plan)
    op = doc["paths"]["/bets"]["get"]
    assert op["servers"] == [
        {"url": "https://report.example.com", "description": "reporting"}
    ]


def test_dedupe_of_shared_path_endpoints_does_not_clobber_server():
    """兩筆 stage-05 endpoint 共用 method+path(多產品共用同一路徑),
    _dedupe_endpoints 會呼叫 _combine_endpoints 把它們合而為一 ——
    這條路徑一樣不能把 server 蓋掉。"""
    inventory = _inventory_with_server()
    inventory["endpoints"].append(
        {"method": "GET", "path": "/bets", "summary": "查詢投注(別名)",
         "source": "api.pdf"},
    )
    extraction = ExtractionResult(
        notebook_url="", artifacts=_artifacts_from_inventory(inventory))

    plan = build_normalization_plan(extraction, _manifest())

    assert len(plan.endpoints) == 1
    assert plan.endpoints[0].server == "reporting"

    doc = build_openapi(plan)
    op = doc["paths"]["/bets"]["get"]
    assert op["servers"] == [
        {"url": "https://report.example.com", "description": "reporting"}
    ]

def test_conflicting_servers_on_shared_path_fail_validation():
    """同一 method+path 被兩個來源指到不同主機 —— 一個 operation 不可能同時
    住在兩台主機上。合併時不得靜默選一個:端點降為 CONFLICTING,並經
    check_completeness 以 SOURCE_CONFLICT ERROR 浮出來(fail-closed)。"""
    inventory = _inventory_with_server()
    inventory["endpoints"].append(
        {"method": "GET", "path": "/bets", "summary": "查詢投注(正式站)",
         "server": "production", "source": "api.pdf"},
    )
    extraction = ExtractionResult(
        notebook_url="", artifacts=_artifacts_from_inventory(inventory))

    plan = build_normalization_plan(extraction, _manifest())

    assert len(plan.endpoints) == 1
    assert plan.endpoints[0].status is PlanItemStatus.CONFLICTING

    issues = check_completeness(plan)
    conflicts = [i for i in issues if i.code is IssueCode.SOURCE_CONFLICT]
    assert len(conflicts) == 1
    assert conflicts[0].severity is Severity.ERROR
    assert "reporting" in conflicts[0].evidence
    assert "production" in conflicts[0].evidence


def test_conflicting_servers_surface_through_the_whole_validate_pipeline():
    """Pins the full-pipeline shape of a server conflict: generation still emits a
    valid OpenAPI operation carrying the deterministically-retained server, and
    validation fails closed with SOURCE_CONFLICT reported from BOTH emitters —
    completeness (from plan.source_conflicts) and speculation (from the endpoint's
    CONFLICTING provenance status). Two rows, one root cause: intentional, not noise."""
    inventory = _inventory_with_server()
    inventory["endpoints"].append(
        {"method": "GET", "path": "/bets", "summary": "查詢投注(正式站)",
         "server": "production", "source": "api.pdf"},
    )
    extraction = ExtractionResult(
        notebook_url="", artifacts=_artifacts_from_inventory(inventory))
    manifest = _manifest()

    plan = build_normalization_plan(extraction, manifest)
    result = build_result(plan, manifest)

    # The operation is still generated, on the retained (first) server.
    op = result.openapi["paths"]["/bets"]["get"]
    assert op["servers"] == [
        {"url": "https://report.example.com", "description": "reporting"}
    ]

    report = validate_outputs(plan, result, manifest)
    assert not report.ok
    conflicts = [i for i in report.issues if i.code is IssueCode.SOURCE_CONFLICT]
    locations = {i.location for i in conflicts}
    assert locations == {"conflict.endpoints.GET /bets.server", "paths./bets.get"}
    assert all(i.severity is Severity.ERROR for i in conflicts)
