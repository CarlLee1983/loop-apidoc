from __future__ import annotations

from loop_apidoc.extraction.jsonblock import extract_json_block, find_gaps
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.questions import build_known_summary, build_question
from loop_apidoc.extraction.stages import STAGES, QueryKind, QueryStage, StageMode
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.retry import run_with_retries


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


def run_extraction(
    adapter: NotebookLMAdapter,
    notebook_url: str,
    store: ExtractionStore,
    *,
    max_attempts: int = 3,
) -> ExtractionResult:
    artifacts: list[AnswerArtifact] = []
    prior_initials: list[tuple[str, str]] = []

    for stage in STAGES:
        known = build_known_summary(prior_initials)

        initial_q = build_question(
            stage, QueryKind.INITIAL, notebook_url=notebook_url, known_summary=known
        )
        initial = _ask_and_store(
            adapter, store, stage, QueryKind.INITIAL, initial_q, notebook_url, max_attempts
        )
        artifacts.append(initial)
        prior_initials.append((stage.title, initial.answer))

        if stage.mode is StageMode.STRUCTURED:
            block = extract_json_block(initial.answer)
            gaps = find_gaps(block) if block is not None else []
            if gaps:
                followup_q = build_question(
                    stage, QueryKind.FOLLOWUP, notebook_url=notebook_url,
                    known_summary=known, pending_fields=gaps,
                )
                artifacts.append(
                    _ask_and_store(adapter, store, stage, QueryKind.FOLLOWUP,
                                   followup_q, notebook_url, max_attempts)
                )

        reverse_q = build_question(
            stage, QueryKind.REVERSE, notebook_url=notebook_url, known_summary=known
        )
        artifacts.append(
            _ask_and_store(adapter, store, stage, QueryKind.REVERSE,
                           reverse_q, notebook_url, max_attempts)
        )

    return ExtractionResult(notebook_url=notebook_url, artifacts=artifacts)
