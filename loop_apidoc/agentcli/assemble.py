from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.agentcli.extraction import inventory_to_stage_answers
from loop_apidoc.agentcli.input_schema import (
    EndpointDetailInput,
    IntegrationInput,
    InventoryInput,
    first_error,
)
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.generate.writer import generate_outputs
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.plan.integration import build_integration_contract
from loop_apidoc.preparation import assess_preparation
from loop_apidoc.preparation import write_reports as write_preparation_reports
from loop_apidoc.preparation.coverage import CoverageInputError, load_coverage
from loop_apidoc.run.models import RunResult, RunStatus
from loop_apidoc.run.persist import persist_plan
from loop_apidoc.validate.report import write_reports as write_validation_reports
from loop_apidoc.validate.validator import validate_outputs


class AssembleInputError(ValueError):
    """agent 產出的擷取檔缺漏或格式錯誤時拋出(fail loudly)。"""


class RunDirectoryCollisionError(RuntimeError):
    """目標 run 目錄已存在時拋出,避免兩個 run 的輸出混在同一目錄(fail loudly)。"""


def load_extraction_inputs(
    extraction_dir: Path,
) -> tuple[dict, list[str], dict | None]:
    """讀 inventory.json(物件)與 endpoints/*.json(原始文字,依檔名排序),
    以及選填的 integration.json(absent → None)。"""
    inv_path = extraction_dir / "inventory.json"
    if not inv_path.is_file():
        raise AssembleInputError(f"找不到 inventory.json:{inv_path}")
    try:
        inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssembleInputError(f"inventory.json 不是合法 JSON:{exc}") from exc
    if not isinstance(inventory, dict):
        raise AssembleInputError("inventory.json 必須是一個 JSON 物件")
    try:
        InventoryInput.model_validate(inventory)
    except ValidationError as exc:
        raise AssembleInputError(
            f"inventory.json 欄位 {first_error(exc)}") from exc

    endpoint_texts: list[str] = []
    endpoints_dir = extraction_dir / "endpoints"
    if endpoints_dir.is_dir():
        for path in sorted(endpoints_dir.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                raise AssembleInputError(
                    f"{path.name} 不是合法 JSON:{exc}") from exc
            try:
                EndpointDetailInput.model_validate(obj)
            except ValidationError as exc:
                raise AssembleInputError(
                    f"{path.name} 欄位 {first_error(exc)}") from exc
            endpoint_texts.append(text)

    integration: dict | None = None
    integration_path = extraction_dir / "integration.json"
    if integration_path.exists():
        try:
            integration = json.loads(integration_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AssembleInputError(
                f"integration.json 不是合法 JSON:{exc}"
            ) from exc
        if not isinstance(integration, dict):
            raise AssembleInputError("integration.json 必須是 JSON 物件")
        try:
            IntegrationInput.model_validate(integration)
        except ValidationError as exc:
            raise AssembleInputError(
                f"integration.json 欄位 {first_error(exc)}") from exc

    return inventory, endpoint_texts, integration


def build_extraction_from_files(
    inventory: dict, endpoint_texts: list[str], store: ExtractionStore
) -> ExtractionResult:
    """把 agent 產出的 inventory + per-endpoint JSON 組成 ExtractionResult,
    產出與 `claude -p` 後端相同的 artifact 形狀,讓 plan 不需改動。"""
    artifacts: list[AnswerArtifact] = []
    for stage_id, answer in inventory_to_stage_answers(inventory).items():
        artifacts.append(store.record(
            query_id=f"{stage_id}-initial", stage_id=stage_id,
            kind=QueryKind.INITIAL, question="(agent inventory)",
            answer=answer, returncode=0,
        ))
    for idx, text in enumerate(endpoint_texts):
        artifacts.append(store.record(
            query_id=f"06-ep{idx}", stage_id="06", kind=QueryKind.INITIAL,
            question="(agent endpoint detail)", answer=text, returncode=0,
        ))
    return ExtractionResult(notebook_url="", artifacts=artifacts)


def run_assemble_pipeline(
    *,
    sources_root: Path,
    extraction_dir: Path,
    output_root: Path,
    run_id: str,
    generated_at: datetime,
    urls: list[str] | None = None,
    url_coverage_path: Path | None = None,
) -> RunResult:
    """agent-native 組裝:manifest(原始來源)→ 由 agent 產出的擷取檔組 plan
    → generate → validate。不做擷取、不 spawn 任何 agent;
    為自成一體的擷取後 pipeline tail(plan→generate→validate)。"""
    # 先驗證 agent 產出的擷取輸入,失敗就在建立任何輸出前 fail loudly,
    # 不留下孤兒 run 目錄。
    inventory, endpoint_texts, integration = load_extraction_inputs(extraction_dir)
    url_coverage = None
    if url_coverage_path is not None:
        # 沒有 URL 來源時 coverage phase 不會產生,明確傳入的帳本會被
        # 靜默丟棄——違反 fail-loud,直接拒絕。
        if not urls:
            raise AssembleInputError(
                "--url-coverage 需要搭配至少一個 --url 來源;"
                "沒有 URL 來源的 run 不會產生 url_coverage phase,"
                "傳入的 coverage 檔會被忽略")
        try:
            url_coverage = load_coverage(url_coverage_path)
        except CoverageInputError as exc:
            raise AssembleInputError(str(exc)) from exc

    run_dir = output_root / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise RunDirectoryCollisionError(
            f"run 目錄已存在,拒絕覆寫:{run_dir}") from exc

    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [], generated_at=generated_at)
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8")

    store = ExtractionStore(run_dir / "extraction")
    extraction = build_extraction_from_files(inventory, endpoint_texts, store)

    plan = build_normalization_plan(extraction, manifest)
    contract = build_integration_contract(integration, plan, manifest)
    plan = plan.model_copy(update={"integration": contract})
    persist_plan(run_dir, plan)
    preparation_report = assess_preparation(
        manifest=manifest,
        inventory=inventory,
        endpoint_texts=endpoint_texts,
        plan=plan,
        url_coverage=url_coverage,
    )
    write_preparation_reports(preparation_report, run_dir)
    result = generate_outputs(plan, manifest, run_dir)
    report = validate_outputs(plan, result, manifest)
    write_validation_reports(report, run_dir / "validation")

    return RunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        report=report,
        rounds=0,
        status=RunStatus.PASSED if report.ok else RunStatus.FAILED,
    )
