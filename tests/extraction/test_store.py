from __future__ import annotations

import json
from pathlib import Path

from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.extraction.store import ExtractionStore


def test_record_writes_answer_and_jsonl(tmp_path: Path):
    store = ExtractionStore(tmp_path)
    art = store.record(
        query_id="05-initial", stage_id="05", kind=QueryKind.INITIAL,
        question="List endpoints", answer="```json\n{}\n```", returncode=0,
    )
    assert isinstance(art, AnswerArtifact)
    assert art.answer_path == "answers/05-initial.txt"
    answer_file = tmp_path / "answers" / "05-initial.txt"
    assert answer_file.read_text(encoding="utf-8") == "```json\n{}\n```"

    lines = (tmp_path / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["query_id"] == "05-initial"
    assert rec["kind"] == "initial"
    assert rec["answer_path"] == "answers/05-initial.txt"


def test_rerun_same_query_id_does_not_overwrite(tmp_path: Path):
    store = ExtractionStore(tmp_path)
    first = store.record(query_id="05-initial", stage_id="05", kind=QueryKind.INITIAL,
                         question="q", answer="round-1 answer", returncode=0)
    second = store.record(query_id="05-initial", stage_id="05", kind=QueryKind.INITIAL,
                          question="q", answer="round-2 answer", returncode=0)

    # First write keeps the canonical filename (backward compatible).
    assert first.answer_path == "answers/05-initial.txt"
    # Re-run must land on a distinct path so the prior artifact is preserved.
    assert second.answer_path != first.answer_path

    first_file = tmp_path / first.answer_path
    second_file = tmp_path / second.answer_path
    assert first_file.read_text(encoding="utf-8") == "round-1 answer"
    assert second_file.read_text(encoding="utf-8") == "round-2 answer"

    # The JSONL audit trail has two records pointing at the two distinct files.
    lines = (tmp_path / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    paths = [json.loads(l)["answer_path"] for l in lines]
    assert paths == [first.answer_path, second.answer_path]
    assert len(set(paths)) == 2


def test_record_appends_in_order(tmp_path: Path):
    store = ExtractionStore(tmp_path)
    store.record(query_id="05-initial", stage_id="05", kind=QueryKind.INITIAL,
                 question="q1", answer="a1", returncode=0)
    store.record(query_id="05-reverse", stage_id="05", kind=QueryKind.REVERSE,
                 question="q2", answer="a2", returncode=0)
    lines = (tmp_path / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["query_id"] for l in lines] == ["05-initial", "05-reverse"]


def test_extraction_result_selectors():
    arts = [
        AnswerArtifact(query_id="05-initial", stage_id="05", kind=QueryKind.INITIAL,
                       answer="i", answer_path="answers/05-initial.txt", returncode=0),
        AnswerArtifact(query_id="05-followup", stage_id="05", kind=QueryKind.FOLLOWUP,
                       answer="f", answer_path="answers/05-followup.txt", returncode=0),
        AnswerArtifact(query_id="02-initial", stage_id="02", kind=QueryKind.INITIAL,
                       answer="n", answer_path="answers/02-initial.txt", returncode=0),
    ]
    result = ExtractionResult(notebook_url="https://nb/x", artifacts=arts)
    assert [a.query_id for a in result.for_stage("05")] == ["05-initial", "05-followup"]
    assert result.latest_structured("05").kind is QueryKind.FOLLOWUP
    assert result.initial("02").answer == "n"
    assert result.latest_structured("99") is None
