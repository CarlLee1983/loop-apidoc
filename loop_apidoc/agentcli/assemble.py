from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from loop_apidoc.agentcli.extraction import inventory_to_stage_answers
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.generate.writer import generate_outputs
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.run.models import RunResult, RunStatus
from loop_apidoc.run.pipeline import _persist_plan
from loop_apidoc.validate.report import write_reports
from loop_apidoc.validate.validator import validate_outputs


class AssembleInputError(ValueError):
    """agent 產出的擷取檔缺漏或格式錯誤時拋出(fail loudly)。"""


def load_extraction_inputs(extraction_dir: Path) -> tuple[dict, list[str]]:
    """讀 inventory.json(物件)與 endpoints/*.json(原始文字,依檔名排序)。"""
    inv_path = extraction_dir / "inventory.json"
    if not inv_path.is_file():
        raise AssembleInputError(f"找不到 inventory.json:{inv_path}")
    try:
        inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssembleInputError(f"inventory.json 不是合法 JSON:{exc}") from exc
    if not isinstance(inventory, dict):
        raise AssembleInputError("inventory.json 必須是一個 JSON 物件")

    endpoint_texts: list[str] = []
    endpoints_dir = extraction_dir / "endpoints"
    if endpoints_dir.is_dir():
        for path in sorted(endpoints_dir.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise AssembleInputError(
                    f"{path.name} 不是合法 JSON:{exc}") from exc
            endpoint_texts.append(text)
    return inventory, endpoint_texts


def build_extraction_from_files(
    inventory: dict, endpoint_texts: list[str], store: ExtractionStore
) -> ExtractionResult:
    """把 agent 產出的 inventory + per-endpoint JSON 組成 ExtractionResult,
    產出與 NotebookLM/`claude -p` 後端相同的 artifact 形狀,讓 plan 不需改動。"""
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
) -> RunResult:
    """agent-native 組裝:manifest(原始來源)→ 由 agent 產出的擷取檔組 plan
    → generate → validate。不做擷取、不 spawn 任何 agent。

    註:tail 與 agentcli.pipeline.run_agent_pipeline 刻意維持小幅重複,
    以免改動既有 `run-agent` 後端(向後相容優先於 DRY)。"""
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [], generated_at=generated_at)
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8")

    inventory, endpoint_texts = load_extraction_inputs(extraction_dir)
    store = ExtractionStore(run_dir / "extraction")
    extraction = build_extraction_from_files(inventory, endpoint_texts, store)

    plan = build_normalization_plan(extraction, manifest)
    _persist_plan(run_dir, plan)
    result = generate_outputs(plan, manifest, run_dir)
    report = validate_outputs(plan, result, manifest)
    write_reports(report, run_dir / "validation")

    return RunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        report=report,
        rounds=0,
        status=RunStatus.PASSED if report.ok else RunStatus.FAILED,
    )
