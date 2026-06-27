from __future__ import annotations

import json
from pathlib import Path

from loop_apidoc.agentcli.extraction import inventory_to_stage_answers
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.extraction.store import ExtractionStore


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
