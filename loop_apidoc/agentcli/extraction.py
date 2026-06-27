from __future__ import annotations

import json

from loop_apidoc.agentcli.adapter import ClaudeCodeAdapter
from loop_apidoc.extraction.jsonblock import extract_json_block
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.questions import build_endpoint_detail_question
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.extraction.store import ExtractionStore

# One comprehensive query replaces ~16 NotebookLM inventory queries: the agent
# holds the whole (markdown) manual and emits every inventory category at once.
# Per-endpoint detail stays fanned out (one focused query each) because the full
# detail of all endpoints would overflow a single response.
INVENTORY_PROMPT = (
    "Read the markdown manual provided to you and output ONE JSON object (and "
    "nothing else) with this exact schema, filled STRICTLY from the sources:\n"
    '{"overview": str, '
    '"environments": [{"name": str, "base_url": str, "version": str|null, "source": str}], '
    '"security_schemes": [{"name": str, "type": str|null, "location": str|null, '
    '"details": str|null, "source": str}], '
    '"endpoints": [{"method": str, "path": str, "summary": str, "source": str}], '
    '"schemas": [{"name": str, "fields": [obj], "enums": [str], "constraints": str|null, "source": str}], '
    '"errors": [{"code": str, "meaning": str, "http_status": str|null, "source": str}], '
    '"operational": [{"topic": str, "detail": str, "source": str}], '
    '"missing": [str]}\n'
    "Include EVERY endpoint and EVERY error code defined by the manual. Cite the "
    "section/page in each `source`. For anything the sources do not state, use null "
    "and add a short label to `missing`. Do not infer or use REST/OAuth conventions."
)

# Which inventory key feeds which plan stage; each becomes that stage's INITIAL
# structured answer so build_normalization_plan consumes it unchanged.
_INVENTORY_STAGES: tuple[tuple[str, str], ...] = (
    ("03", "environments"),
    ("04", "security_schemes"),
    ("05", "endpoints"),
    ("07", "schemas"),
    ("08", "errors"),
    ("09", "operational"),
)


def _block(key: str, inventory: dict) -> str:
    value = inventory.get(key)
    payload = {key: value if isinstance(value, list) else [],
               "missing": inventory.get("missing") or []}
    return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def inventory_to_stage_answers(inventory: dict) -> dict[str, str]:
    """Split one inventory JSON into per-stage answer texts (pure)."""
    answers: dict[str, str] = {
        "01": "Source inventory: a single source manual was provided and read.",
        "02": str(inventory.get("overview") or "").strip()
        or "(no overview stated)",
        "10": "Gaps/conflicts: " + "; ".join(
            str(m) for m in (inventory.get("missing") or [])
        ) if inventory.get("missing") else "(none reported)",
    }
    for stage_id, key in _INVENTORY_STAGES:
        answers[stage_id] = _block(key, inventory)
    return answers


def run_agent_extraction(
    adapter: ClaudeCodeAdapter, store: ExtractionStore
) -> ExtractionResult:
    """Collapsed extraction: one inventory query + one query per endpoint.

    Produces the same on-disk artifacts and ExtractionResult shape as the
    NotebookLM orchestrator, so plan/generate/validate run unchanged."""
    artifacts: list[AnswerArtifact] = []

    inv_answer = adapter.ask(INVENTORY_PROMPT).answer
    inventory = extract_json_block(inv_answer) or {}

    for stage_id, answer in inventory_to_stage_answers(inventory).items():
        artifacts.append(store.record(
            query_id=f"{stage_id}-initial", stage_id=stage_id,
            kind=QueryKind.INITIAL, question=INVENTORY_PROMPT,
            answer=answer, returncode=0,
        ))

    endpoints = inventory.get("endpoints") if isinstance(inventory, dict) else None
    for idx, ep in enumerate(endpoints or []):
        if not (isinstance(ep, dict) and ep.get("method") and ep.get("path")):
            continue
        question = build_endpoint_detail_question(
            ep["method"], ep["path"], ep.get("summary"))
        answer = adapter.ask(question).answer
        artifacts.append(store.record(
            query_id=f"06-ep{idx}", stage_id="06", kind=QueryKind.INITIAL,
            question=question, answer=answer, returncode=0,
        ))

    return ExtractionResult(notebook_url="", artifacts=artifacts)
