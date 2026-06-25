from __future__ import annotations

from loop_apidoc.extraction.questions import build_known_summary, build_question
from loop_apidoc.extraction.stages import QueryKind, stage_by_id

NB = "https://notebooklm.google.com/notebook/abc"


def test_known_summary_formats_lines():
    summary = build_known_summary([("Overview", "It is a payments API.\nWith webhooks.")])
    assert "- Overview: It is a payments API. With webhooks." in summary


def test_known_summary_empty():
    assert build_known_summary([]) == "(none yet)"


def test_initial_structured_question_is_self_contained():
    stage = stage_by_id("05")
    q = build_question(stage, QueryKind.INITIAL, notebook_url=NB, known_summary="(none yet)")
    assert NB in q
    assert "(none yet)" in q
    assert stage.goal in q
    assert stage.json_hint in q


def test_followup_lists_pending_and_demands_full_block():
    stage = stage_by_id("03")
    q = build_question(
        stage, QueryKind.FOLLOWUP, notebook_url=NB, known_summary="x",
        pending_fields=["base_url", "version"],
    )
    assert "base_url" in q and "version" in q
    assert "full" in q.lower()
    assert "missing" in q


def test_reverse_question_asks_for_omissions():
    stage = stage_by_id("05")
    q = build_question(stage, QueryKind.REVERSE, notebook_url=NB, known_summary="x")
    assert "miss" in q.lower() or "conflict" in q.lower()
    assert NB in q


def test_narrative_initial_has_no_json_hint():
    stage = stage_by_id("02")
    q = build_question(stage, QueryKind.INITIAL, notebook_url=NB, known_summary="x")
    assert "```json" not in q
    assert stage.goal in q
