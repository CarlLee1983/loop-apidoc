from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.atomic_publish import (
    DirectoryPublicationCollisionError,
    DirectoryPublicationError,
    publish_directory_noreplace,
)
from loop_apidoc.agentcli.extraction import inventory_to_stage_answers
from loop_apidoc.agentcli.strict import (
    run_strict_core_safely,
    write_strict_blocked_marker,
)
from loop_apidoc.agentcli.evidence import (
    verify_evidence_claim_paths,
    verify_extraction_evidence,
)
from loop_apidoc.agentcli.gate import check_extraction
from loop_apidoc.focus.gate import focus_evidence_references
from loop_apidoc.focus.loader import load_focus_package
from loop_apidoc.focus.report import write_reports as write_focus_reports
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
from loop_apidoc.manifest.scanner import ManifestScanError
from loop_apidoc.manifest.models import Manifest, UrlSource
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.plan.integration import build_integration_contract
from loop_apidoc.preparation import assess_preparation
from loop_apidoc.preparation import write_reports as write_preparation_reports
from loop_apidoc.url_coverage import (
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
from loop_apidoc.shadow.models import ArchitectureMode
from loop_apidoc.shadow.report import run_shadow_safely
from loop_apidoc.agentcli.fact_coverage import build_fact_coverage
from loop_apidoc.operation_identity import expand_methods, extraction_identities
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
    inventory: dict,
    endpoint_texts: list[str],
    store: ExtractionStore | None,
) -> ExtractionResult:
    """把 agent 產出的 inventory + per-endpoint JSON 組成 ExtractionResult,
    產出與 `claude -p` 後端相同的 artifact 形狀,讓 plan 不需改動。"""
    artifacts: list[AnswerArtifact] = []

    def record(
        *,
        query_id: str,
        stage_id: str,
        answer: str,
    ) -> AnswerArtifact:
        if store is not None:
            return store.record(
                query_id=query_id,
                stage_id=stage_id,
                kind=QueryKind.INITIAL,
                question="(agent inventory)" if stage_id != "06"
                else "(agent endpoint detail)",
                answer=answer,
                returncode=0,
            )
        # Claim-path verification must happen before a run directory exists.
        # Preserve the persisted artifact's stable first-attempt shape without
        # writing the compatibility answer files.
        return AnswerArtifact(
            query_id=query_id,
            stage_id=stage_id,
            kind=QueryKind.INITIAL,
            answer=answer,
            answer_path=f"answers/{query_id}.txt",
            returncode=0,
        )

    for stage_id, answer in inventory_to_stage_answers(inventory).items():
        artifacts.append(record(
            query_id=f"{stage_id}-initial", stage_id=stage_id, answer=answer,
        ))
    for idx, text in enumerate(endpoint_texts):
        detail = json.loads(text)
        expanded = expand_methods([detail]) if isinstance(detail, dict) else []
        if isinstance(detail, dict) and "methods" in detail:
            answers = [json.dumps(entry, ensure_ascii=False)
                       for entry in (expanded or [detail])]
        else:
            answers = [text]
        for method_idx, answer in enumerate(answers):
            suffix = f"-{method_idx}" if len(answers) > 1 else ""
            artifacts.append(record(
                query_id=f"06-ep{idx}{suffix}", stage_id="06", answer=answer,
            ))
    return ExtractionResult(notebook_url="", artifacts=artifacts)


def run_assemble_pipeline(
    *,
    sources_root: Path,
    extraction_dir: Path,
    output_root: Path,
    run_id: str,
    generated_at: datetime,
    source_quality_dir: Path,
    urls: list[str] | None = None,
    url_coverage_path: Path | None = None,
    excludes: Sequence[str] = (),
    extractor_model: str | None = None,
    architecture_mode: ArchitectureMode = ArchitectureMode.LEGACY,
    focus_file: Path | None = None,
) -> RunResult:
    """agent-native 組裝:manifest(原始來源)→ 由 agent 產出的擷取檔組 plan
    → generate → validate。不做擷取、不 spawn 任何 agent;
    為自成一體的擷取後 pipeline tail(plan→generate→validate)。"""
    # 先驗證 agent 產出的擷取輸入,失敗就在建立任何輸出前 fail loudly,
    # 不留下孤兒 run 目錄。
    inventory, endpoint_texts, integration = load_extraction_inputs(extraction_dir)
    focus = (
        load_focus_package(focus_file, extraction_dir)
        if focus_file is not None else None
    )
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
    try:
        manifest = build_manifest(
            sources_root=sources_root,
            urls=urls or [],
            generated_at=generated_at,
            excludes=excludes,
            url_coverage=url_coverage,
        )
    except ManifestScanError as exc:
        raise AssembleInputError(str(exc)) from exc
    from loop_apidoc.source_risk import SourceRiskInputError, verify_source_risk_report

    if source_quality_report.source_risk is None:
        raise AssembleInputError(
            "source quality report has no verified source-risk audit"
        )
    try:
        verify_source_risk_report(
            source_quality_report.source_risk,
            manifest=manifest,
            sources_root=sources_root,
        )
    except SourceRiskInputError as exc:
        raise AssembleInputError(str(exc)) from exc
    if url_coverage is not None:
        # 有帳本才回填 URL→快照檔映射;無帳本行為與現狀完全相同。
        manifest = backfill_snapshot_files(manifest, url_coverage)

    facts = collect_facts(sources_root, manifest)
    endpoints = named_endpoints(extraction_dir, endpoint_texts)
    violations = check_extraction(
        inventory, endpoints, integration, manifest, facts, focus)
    violations += verify_extraction_evidence(
        inventory,
        endpoints,
        integration,
        manifest,
        facts,
        generated_at,
        extra_references=focus_evidence_references(focus),
    )
    if not violations:
        preflight_extraction = build_extraction_from_files(
            inventory, endpoint_texts, store=None
        )
        preflight_plan = build_normalization_plan(preflight_extraction, manifest)
        preflight_contract = build_integration_contract(
            integration, preflight_plan, manifest
        )
        preflight_plan = preflight_plan.model_copy(
            update={"integration": preflight_contract}
        )
        violations += verify_evidence_claim_paths(preflight_plan)
    if violations:
        raise AssembleInputError(
            "擷取輸入不符契約(修正後重跑 assemble):\n"
            + "\n".join(f"  - {v}" for v in violations))

    run_dir = output_root / run_id
    run_parent = run_dir.parent
    run_parent.mkdir(parents=True, exist_ok=True)
    if run_dir.exists() or run_dir.is_symlink():
        raise RunDirectoryCollisionError(
            f"run 目錄已存在,拒絕覆寫:{run_dir}"
        )
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{run_dir.name}.staging-", dir=run_parent))
    published = False
    try:
        (staging_dir / "manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8")
        write_source_quality_reports(
            source_quality_report, source_diff_report, staging_dir / "source-quality"
        )

        store = ExtractionStore(staging_dir / "extraction")
        extraction = build_extraction_from_files(inventory, endpoint_texts, store)

        plan = build_normalization_plan(extraction, manifest)
        contract = build_integration_contract(integration, plan, manifest)
        plan = plan.model_copy(update={"integration": contract})
        persist_plan(staging_dir, plan)
        preparation_report = assess_preparation(
            manifest=manifest,
            inventory=inventory,
            endpoint_texts=endpoint_texts,
            plan=plan,
            url_coverage=url_coverage,
        )
        write_preparation_reports(preparation_report, staging_dir)
        result = generate_outputs(plan, manifest, staging_dir)
        report = validate_outputs(
            plan, result, manifest, focus, facts.documented_error_codes(),
            # 投影在此一處算出:`collect_facts` 的結果與 extraction 都在手上,讓
            # validate 自行重掃會讓同一份來源在一次 run 內被掃兩次,可能給出
            # 「閘門判過但報告說沒掃到」這種自相矛盾的輸出。
            fact_coverage=build_fact_coverage(
                manifest, facts, extraction_identities(inventory, endpoints)
            ),
        )
        write_validation_reports(report, staging_dir / "validation")
        if focus is not None:
            write_focus_reports(focus, staging_dir)

        status = RunStatus.PASSED if report.ok else RunStatus.FAILED
        shadow = None
        strict = None
        if architecture_mode is ArchitectureMode.SHADOW:
            shadow = run_shadow_safely(
                manifest=manifest,
                plan=plan,
                facts=facts,
                sources_root=sources_root,
                legacy_report=report,
                legacy_status=status,
                generated_at=generated_at,
                run_dir=staging_dir,
            )
        elif architecture_mode is ArchitectureMode.STRICT:
            if report.ok:
                strict = run_strict_core_safely(
                    manifest=manifest,
                    plan=plan,
                    facts=facts,
                    sources_root=sources_root,
                    legacy_report=report,
                    generated_at=generated_at,
                    run_dir=staging_dir,
                )
                if strict.status == "error":
                    status = RunStatus.BLOCKED
                elif strict.status != "ok":
                    status = RunStatus.FAILED
            else:
                strict = write_strict_blocked_marker(
                    run_dir=staging_dir,
                    legacy_status=status,
                )
        toolchain = build_toolchain(model=extractor_model)
        # ``run.json`` is the completion marker and must be materialized last.
        persist_run_descriptor(staging_dir, RunDescriptor(
            run_id=run_id, status=status, generated_at=generated_at,
            toolchain=toolchain, architecture_mode=architecture_mode.value,
        ))
        try:
            publish_directory_noreplace(staging_dir, run_dir)
        except DirectoryPublicationCollisionError as exc:
            raise RunDirectoryCollisionError(
                f"run 目錄已存在,拒絕覆寫:{run_dir}"
            ) from exc
        except DirectoryPublicationError as exc:
            raise RuntimeError(f"run 目錄發佈失敗:{run_dir}") from exc
        published = True
        if shadow is not None:
            shadow = shadow.model_copy(
                update={
                    "core_dir": _published_run_path(shadow.core_dir, staging_dir, run_dir),
                    "comparison_path": _published_run_path(
                        shadow.comparison_path, staging_dir, run_dir
                    ),
                    "error_path": _published_run_path(
                        shadow.error_path, staging_dir, run_dir
                    ),
                }
            )
        if strict is not None:
            strict = strict.model_copy(
                update={
                    "core_dir": _published_run_path(strict.core_dir, staging_dir, run_dir),
                    "candidate_path": _published_run_path(
                        strict.candidate_path, staging_dir, run_dir
                    ),
                    "error_path": _published_run_path(
                        strict.error_path, staging_dir, run_dir
                    ),
                }
            )
    finally:
        if not published:
            shutil.rmtree(staging_dir, ignore_errors=True)

    return RunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        report=report,
        rounds=0,
        status=status,
        toolchain=toolchain,
        shadow=shadow,
        strict=strict,
    )


def _published_run_path(value: str | None, staging_dir: Path, run_dir: Path) -> str | None:
    """Rebase a summary path created in staging after its atomic publication."""
    if value is None:
        return None
    path = Path(value)
    try:
        return str(run_dir / path.relative_to(staging_dir))
    except ValueError:
        return value
