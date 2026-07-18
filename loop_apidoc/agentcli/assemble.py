from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.agentcli.extraction import _expand_methods, inventory_to_stage_answers
from loop_apidoc.agentcli.gate import check_extraction
from loop_apidoc.agentcli.input_schema import (
    EndpointDetailInput,
    IntegrationInput,
    InventoryInput,
    first_error,
    normalize_endpoint_method_fields,
)
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.generate.writer import generate_outputs
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.manifest.models import Manifest, UrlSource
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.plan.integration import build_integration_contract
from loop_apidoc.preparation import assess_preparation
from loop_apidoc.preparation import write_reports as write_preparation_reports
from loop_apidoc.preparation.coverage import (
    CoverageInputError,
    ResultStatus,
    UrlCoverage,
    load_coverage,
    normalize_url,
)
from loop_apidoc.run.models import RunDescriptor, RunResult, RunStatus
from loop_apidoc.run.persist import persist_plan, persist_run_descriptor
from loop_apidoc.run.toolchain import build_toolchain
from loop_apidoc.source_facts.collect import collect_facts
from loop_apidoc.source_quality.loader import (
    SourceQualityInputError,
    load_assessment_reports,
)
from loop_apidoc.source_quality.models import QualityVerdict
from loop_apidoc.source_quality.report import write_reports as write_source_quality_reports
from loop_apidoc.validate.report import write_reports as write_validation_reports
from loop_apidoc.validate.validator import validate_outputs


class AssembleInputError(ValueError):
    """agent 產出的擷取檔缺漏或格式錯誤時拋出(fail loudly)。"""


class RunDirectoryCollisionError(RuntimeError):
    """目標 run 目錄已存在時拋出,避免兩個 run 的輸出混在同一目錄(fail loudly)。"""


# 只有帶 file 且成功抓到/需登入(仍留了本地檔)的 result 提供 URL→本地檔映射。
_MAPPING_STATUSES = (
    ResultStatus.FETCHED,
    ResultStatus.FETCHED_RENDERED,
    ResultStatus.AUTH_REQUIRED,
)


def _ledger_file_matches(ledger_file: str, relative_path: str) -> bool:
    """帳本 file(相對 work dir,如 sources/overview.md)以 `/` 為界、
    以某本地來源 relative_path(相對 sources_root)結尾即命中。"""
    return ledger_file == relative_path or ledger_file.endswith("/" + relative_path)


def backfill_snapshot_files(manifest: Manifest, coverage: UrlCoverage) -> Manifest:
    """把 coverage 帳本 results[].file 的 URL→本地檔映射回填到
    manifest.url_sources[].snapshot_file,回傳新的 Manifest(純函式,不就地修改)。

    - URL 比對用 normalize_url(去 fragment/尾斜線)。
    - 只有帶 file 且 status ∈ fetched/fetched_rendered/auth_required 的 result 提供映射。
    - 帳本 file 對本地 relative_path 採路徑後綴匹配。
    - 須唯一命中才配對;零命中或多重命中(含多個 result 映到不同檔)→ 維持 None,不誤配。
    """
    local_paths = [s.relative_path for s in manifest.local_sources]
    updated: list[UrlSource] = []
    for url_source in manifest.url_sources:
        key = normalize_url(url_source.url)
        candidates: set[str] = set()
        for result in coverage.results:
            if result.file is None or result.status not in _MAPPING_STATUSES:
                continue
            if normalize_url(result.url) != key:
                continue
            for rel in local_paths:
                if _ledger_file_matches(result.file, rel):
                    candidates.add(rel)
        snapshot = next(iter(candidates)) if len(candidates) == 1 else None
        updated.append(url_source.model_copy(update={"snapshot_file": snapshot}))
    return manifest.model_copy(update={"url_sources": updated})


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
    for endpoint in inventory.get("endpoints") or []:
        if isinstance(endpoint, dict):
            normalize_endpoint_method_fields(endpoint)

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
            if isinstance(obj, dict):
                normalize_endpoint_method_fields(obj)
            endpoint_texts.append(json.dumps(obj, ensure_ascii=False))

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


def named_endpoints(
    extraction_dir: Path, endpoint_texts: list[str]
) -> list[tuple[str, dict]]:
    """Pair each endpoint text with its filename, for guard messages that name
    the file to fix. Same sorted order `load_extraction_inputs` read them in."""
    endpoints_dir = extraction_dir / "endpoints"
    names = (
        [p.name for p in sorted(endpoints_dir.glob("*.json"))]
        if endpoints_dir.is_dir() else []
    )
    return [(name, json.loads(text)) for name, text in zip(names, endpoint_texts)]


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
        detail = json.loads(text)
        expanded = _expand_methods([detail]) if isinstance(detail, dict) else []
        if isinstance(detail, dict) and "methods" in detail:
            answers = [json.dumps(entry, ensure_ascii=False)
                       for entry in (expanded or [detail])]
        else:
            answers = [text]
        for method_idx, answer in enumerate(answers):
            suffix = f"-{method_idx}" if len(answers) > 1 else ""
            artifacts.append(store.record(
                query_id=f"06-ep{idx}{suffix}", stage_id="06", kind=QueryKind.INITIAL,
                question="(agent endpoint detail)", answer=answer, returncode=0,
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
    source_quality_dir: Path | None = None,
    excludes: Sequence[str] = (),
    extractor_model: str | None = None,
) -> RunResult:
    """agent-native 組裝:manifest(原始來源)→ 由 agent 產出的擷取檔組 plan
    → generate → validate。不做擷取、不 spawn 任何 agent;
    為自成一體的擷取後 pipeline tail(plan→generate→validate)。"""
    # 先驗證 agent 產出的擷取輸入,失敗就在建立任何輸出前 fail loudly,
    # 不留下孤兒 run 目錄。
    inventory, endpoint_texts, integration = load_extraction_inputs(extraction_dir)
    source_quality_report = None
    source_diff_report = None
    if source_quality_dir is not None:
        try:
            source_quality_report, source_diff_report = load_assessment_reports(
                source_quality_dir
            )
        except SourceQualityInputError as exc:
            raise AssembleInputError(str(exc)) from exc
        if source_quality_report.verdict is QualityVerdict.REJECT:
            raise AssembleInputError(
                "source quality report verdict is reject; resolve blockers before assemble"
            )
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

    # manifest 必須先於 run 目錄建立:source 格式檢查要拿它比對,而檢查失敗時
    # 不該留下孤兒 run 目錄。build_manifest 只掃描與探測,不寫檔。
    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [], generated_at=generated_at,
        excludes=excludes)
    if url_coverage is not None:
        # 有帳本才回填 URL→快照檔映射;無帳本行為與現狀完全相同。
        manifest = backfill_snapshot_files(manifest, url_coverage)

    violations = check_extraction(
        inventory, named_endpoints(extraction_dir, endpoint_texts),
        integration, manifest, collect_facts(sources_root, manifest))
    if violations:
        raise AssembleInputError(
            "擷取輸入不符契約(修正後重跑 assemble):\n"
            + "\n".join(f"  - {v}" for v in violations))

    run_dir = output_root / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise RunDirectoryCollisionError(
            f"run 目錄已存在,拒絕覆寫:{run_dir}") from exc

    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8")
    if source_quality_report is not None and source_diff_report is not None:
        write_source_quality_reports(
            source_quality_report, source_diff_report, run_dir / "source-quality"
        )

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

    status = RunStatus.PASSED if report.ok else RunStatus.FAILED
    toolchain = build_toolchain(model=extractor_model)
    persist_run_descriptor(run_dir, RunDescriptor(
        run_id=run_id, status=status, generated_at=generated_at,
        toolchain=toolchain,
    ))

    return RunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        report=report,
        rounds=0,
        status=status,
        toolchain=toolchain,
    )
