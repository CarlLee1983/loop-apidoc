from __future__ import annotations

from loop_apidoc.extraction.jsonblock import extract_json_block, find_gaps
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.questions import (
    build_endpoint_detail_question,
    build_question,
)
from loop_apidoc.extraction.stages import STAGES, QueryKind, QueryStage, StageMode
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.retry import run_with_retries

# Stage 06 (per-endpoint details) is fanned out across the endpoints discovered
# in stage 05 rather than asked as one "every endpoint" query: NotebookLM reliably
# details a single endpoint per focused query but collapses the bulk ask to one.
_ENDPOINT_DETAIL_STAGE = "05"
_DETAIL_STAGE = "06"


def _endpoints_from(stage05_artifacts: list[AnswerArtifact]) -> list[dict]:
    """Extract the {method, path, summary} endpoint list from stage 05's INITIAL
    answer, to drive per-endpoint detail queries."""
    initial = next(
        (a for a in stage05_artifacts if a.kind is QueryKind.INITIAL), None
    )
    if initial is None:
        return []
    block = extract_json_block(initial.answer)
    raw = block.get("endpoints") if isinstance(block, dict) else None
    if not isinstance(raw, list):
        return []
    return [
        e for e in raw
        if isinstance(e, dict) and e.get("method") and e.get("path")
    ]


def _run_endpoint_details(
    adapter: NotebookLMAdapter,
    store: ExtractionStore,
    stage: QueryStage,
    endpoints: list[dict],
    notebook_url: str,
    max_attempts: int,
) -> list[AnswerArtifact]:
    if not endpoints:
        # Stage 05 yielded no endpoint list to fan out over; fall back to one
        # generic stage-06 query so the stage still contributes an artifact.
        return [_ask_and_store(
            adapter, store, stage, QueryKind.INITIAL,
            build_question(stage, QueryKind.INITIAL), notebook_url, max_attempts)]
    artifacts: list[AnswerArtifact] = []
    for idx, ep in enumerate(endpoints):
        question = build_endpoint_detail_question(
            ep["method"], ep["path"], ep.get("summary") or ep.get("name")
        )
        result = run_with_retries(
            lambda q=question: adapter.ask(q, notebook_url), max_attempts=max_attempts
        )
        artifacts.append(
            store.record(
                query_id=f"{_DETAIL_STAGE}-ep{idx}",
                stage_id=_DETAIL_STAGE,
                kind=QueryKind.INITIAL,
                question=question,
                answer=result.answer,
                returncode=result.returncode,
            )
        )
    return artifacts


def _ask_and_store(
    adapter: NotebookLMAdapter,
    store: ExtractionStore,
    stage: QueryStage,
    kind: QueryKind,
    question: str,
    notebook_url: str,
    max_attempts: int,
) -> AnswerArtifact:
    result = run_with_retries(
        lambda: adapter.ask(question, notebook_url), max_attempts=max_attempts
    )
    return store.record(
        query_id=f"{stage.stage_id}-{kind.value}",
        stage_id=stage.stage_id,
        kind=kind,
        question=question,
        answer=result.answer,
        returncode=result.returncode,
    )


def _run_stage(
    adapter: NotebookLMAdapter,
    store: ExtractionStore,
    stage: QueryStage,
    notebook_url: str,
    max_attempts: int,
) -> list[AnswerArtifact]:
    """Run one stage: INITIAL, optional FOLLOWUP (structured gaps), then REVERSE.

    The INITIAL artifact is always the first element of the returned list. Each
    question is self-contained (no cross-stage context), so stages no longer
    depend on the order they run in.
    """
    artifacts: list[AnswerArtifact] = []

    initial_q = build_question(stage, QueryKind.INITIAL)
    initial = _ask_and_store(
        adapter, store, stage, QueryKind.INITIAL, initial_q, notebook_url, max_attempts
    )
    artifacts.append(initial)

    if stage.mode is StageMode.STRUCTURED:
        block = extract_json_block(initial.answer)
        gaps = find_gaps(block) if block is not None else []
        if gaps:
            followup_q = build_question(
                stage, QueryKind.FOLLOWUP, pending_fields=gaps
            )
            artifacts.append(
                _ask_and_store(adapter, store, stage, QueryKind.FOLLOWUP,
                               followup_q, notebook_url, max_attempts)
            )

    reverse_q = build_question(stage, QueryKind.REVERSE)
    artifacts.append(
        _ask_and_store(adapter, store, stage, QueryKind.REVERSE,
                       reverse_q, notebook_url, max_attempts)
    )
    return artifacts


def run_extraction(
    adapter: NotebookLMAdapter,
    notebook_url: str,
    store: ExtractionStore,
    *,
    max_attempts: int = 3,
) -> ExtractionResult:
    artifacts: list[AnswerArtifact] = []
    stage05: list[AnswerArtifact] = []
    for stage in STAGES:
        if stage.stage_id == _DETAIL_STAGE:
            artifacts.extend(_run_endpoint_details(
                adapter, store, stage, _endpoints_from(stage05),
                notebook_url, max_attempts))
            continue
        stage_arts = _run_stage(adapter, store, stage, notebook_url, max_attempts)
        artifacts.extend(stage_arts)
        if stage.stage_id == _ENDPOINT_DETAIL_STAGE:
            stage05 = stage_arts
    return ExtractionResult(notebook_url=notebook_url, artifacts=artifacts)


def rerun_stages(
    adapter: NotebookLMAdapter,
    notebook_url: str,
    store: ExtractionStore,
    prior: ExtractionResult,
    stage_ids: set[str],
    *,
    max_attempts: int = 3,
) -> ExtractionResult:
    """Re-query only `stage_ids`; retain prior artifacts for every other stage.

    Returns a merged ExtractionResult consumable by build_normalization_plan
    unchanged. Questions are self-contained, so a re-run stage does not depend on
    other stages being fresh or retained.
    """
    artifacts: list[AnswerArtifact] = []
    stage05: list[AnswerArtifact] = prior.for_stage(_ENDPOINT_DETAIL_STAGE)
    for stage in STAGES:
        if stage.stage_id == _DETAIL_STAGE:
            if _DETAIL_STAGE in stage_ids:
                artifacts.extend(_run_endpoint_details(
                    adapter, store, stage, _endpoints_from(stage05),
                    notebook_url, max_attempts))
            else:
                artifacts.extend(prior.for_stage(_DETAIL_STAGE))
            continue
        if stage.stage_id in stage_ids:
            stage_arts = _run_stage(adapter, store, stage, notebook_url, max_attempts)
            artifacts.extend(stage_arts)
            if stage.stage_id == _ENDPOINT_DETAIL_STAGE:
                stage05 = stage_arts  # fresh endpoints drive a re-run of stage 06
        else:
            artifacts.extend(prior.for_stage(stage.stage_id))
    return ExtractionResult(notebook_url=notebook_url, artifacts=artifacts)
