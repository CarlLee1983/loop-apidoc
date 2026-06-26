from __future__ import annotations

from loop_apidoc.extraction.questions import build_question
from loop_apidoc.extraction.stages import QueryKind, stage_by_id

NB = "https://notebooklm.google.com/notebook/abc"


def test_initial_structured_question_is_short_and_self_contained():
    stage = stage_by_id("05")
    q = build_question(stage, QueryKind.INITIAL)
    assert stage.goal in q
    assert stage.json_hint in q
    # No heavy preamble or embedded context (the cause of NotebookLM confusion).
    assert NB not in q
    assert "Known so far" not in q
    assert "conversation history" not in q


def test_followup_lists_pending_and_demands_full_block():
    stage = stage_by_id("03")
    q = build_question(
        stage, QueryKind.FOLLOWUP, pending_fields=["base_url", "version"]
    )
    assert "base_url" in q and "version" in q
    assert "full" in q.lower()
    assert "missing" in q
    assert stage.json_hint in q


def test_reverse_question_asks_for_omissions_and_anchors_topic():
    stage = stage_by_id("05")
    q = build_question(stage, QueryKind.REVERSE)
    assert "miss" in q.lower() or "conflict" in q.lower()
    assert f"Topic: {stage.title}" in q
    assert NB not in q


def test_narrative_initial_has_no_json_hint():
    stage = stage_by_id("02")
    q = build_question(stage, QueryKind.INITIAL)
    assert "```json" not in q
    assert stage.goal in q
