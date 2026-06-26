from __future__ import annotations

from pathlib import Path

from loop_apidoc.extraction.models import ExtractionResult
from loop_apidoc.extraction.orchestrator import rerun_stages, run_extraction
from loop_apidoc.extraction.stages import STAGES
from loop_apidoc.extraction.store import ExtractionStore

NB = "https://notebooklm.google.com/notebook/abc"


class _FakeAskResult:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.returncode = 0


class _MarkerAdapter:
    """Records every question and returns a per-stage, per-call marker answer.

    The marker (`ANSWER-<stage_id>-<n>`) lets tests detect which stage produced
    an answer and whether a re-run produced a *fresh* one (higher n). Stages are
    identified by their goal text (INITIAL) or `Topic: <title>` (FOLLOWUP/REVERSE)
    embedded in the question. Returns prose-shaped markers, so structured stages
    find no JSON block and never emit a follow-up — keeping query counts simple
    (2 per stage: initial + reverse)."""

    def __init__(self) -> None:
        self.questions: list[str] = []
        self._counts: dict[str, int] = {}

    def ask(self, question: str, notebook_url: str) -> _FakeAskResult:
        self.questions.append(question)
        for stage in STAGES:
            if stage.goal in question or f"Topic: {stage.title}" in question:
                self._counts[stage.stage_id] = self._counts.get(stage.stage_id, 0) + 1
                return _FakeAskResult(f"ANSWER-{stage.stage_id}-{self._counts[stage.stage_id]}")
        return _FakeAskResult("ANSWER-unknown")


def _goal(stage_id: str) -> str:
    return next(s.goal for s in STAGES if s.stage_id == stage_id)


def test_rerun_only_queries_requested_stage(tmp_path: Path) -> None:
    store = ExtractionStore(tmp_path)
    adapter = _MarkerAdapter()
    prior = run_extraction(adapter, NB, store)
    adapter.questions.clear()

    merged = rerun_stages(adapter, NB, store, prior, {"04"})

    # Only stage 04 was queried: 2 questions (initial + reverse).
    assert len(adapter.questions) == 2
    assert all(_goal("04") in q or "Topic: Authentication" in q for q in adapter.questions)


def test_rerun_retains_other_stages_and_refreshes_target(tmp_path: Path) -> None:
    store = ExtractionStore(tmp_path)
    adapter = _MarkerAdapter()
    prior = run_extraction(adapter, NB, store)

    merged = rerun_stages(adapter, NB, store, prior, {"04"})

    # Non-target stage 05 artifacts are the retained prior ones (identical).
    assert merged.for_stage("05") == prior.for_stage("05")
    # Target stage 04 got a fresh initial answer (higher marker count than prior).
    assert prior.initial("04").answer == "ANSWER-04-1"
    # After run_extraction, stage 04 has 2 calls (initial + reverse).
    # The rerun initial is the 3rd call total, so count = 3.
    assert merged.initial("04").answer == "ANSWER-04-3"
    # Every stage still represented exactly once for its initial.
    assert {s.stage_id for s in STAGES} == {a.stage_id for a in merged.artifacts}


def test_rerun_context_includes_fresh_prior_stage(tmp_path: Path) -> None:
    store = ExtractionStore(tmp_path)
    adapter = _MarkerAdapter()
    prior = run_extraction(adapter, NB, store)
    adapter.questions.clear()

    rerun_stages(adapter, NB, store, prior, {"05", "06"})

    # Stage 06's INITIAL question must carry the FRESH stage-05 answer (run 3: the
    # 3rd adapter call to stage 05, since run_extraction already made 2 calls:
    # initial=1, reverse=2; the rerun initial is call 3).
    # This proves the known_summary accumulator uses re-run answers, not retained ones.
    six_initial = next(q for q in adapter.questions if _goal("06") in q)
    assert "ANSWER-05-3" in six_initial


def test_rerun_over_merged_result_stays_stable_across_rounds(tmp_path: Path) -> None:
    # Risk #1: a second rerun consuming the first round's *merged* result must
    # not accumulate or duplicate artifacts — the correction loop runs up to 3
    # rounds, each feeding state["extraction"] (a prior merged result) back in.
    store = ExtractionStore(tmp_path)
    adapter = _MarkerAdapter()
    prior = run_extraction(adapter, NB, store)

    round1 = rerun_stages(adapter, NB, store, prior, {"05", "06"})
    round2 = rerun_stages(adapter, NB, store, round1, {"05", "06"})

    # Exactly one INITIAL per stage after two rounds — no stage duplicated.
    assert {s.stage_id for s in STAGES} == {a.stage_id for a in round2.artifacts}
    # Total artifact count is stable: no accumulation across rounds (each stage
    # still contributes initial + reverse only).
    assert len(round2.artifacts) == len(prior.artifacts)
    # Re-run target keeps refreshing each round (run_extraction=2 calls,
    # round1 initial=3, round2 initial=5).
    assert round1.initial("05").answer == "ANSWER-05-3"
    assert round2.initial("05").answer == "ANSWER-05-5"
    # Retained stage 04, never targeted, is the original prior artifact through
    # both rounds — not a stale copy that drifted.
    assert round2.for_stage("04") == prior.for_stage("04")


def test_rerun_far_fewer_queries_than_full(tmp_path: Path) -> None:
    store = ExtractionStore(tmp_path)
    adapter = _MarkerAdapter()
    prior = run_extraction(adapter, NB, store)
    full_count = len(adapter.questions)
    adapter.questions.clear()

    rerun_stages(adapter, NB, store, prior, {"05", "06"})
    assert len(adapter.questions) == 4  # 2 stages x (initial + reverse)
    assert len(adapter.questions) < full_count
