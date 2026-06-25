from __future__ import annotations

from pathlib import Path

from loop_apidoc.extraction.orchestrator import run_extraction
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.extraction.store import ExtractionStore

NB = "https://notebooklm.google.com/notebook/abc"


class _FakeAskResult:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.returncode = 0


class _FakeAdapter:
    """Returns a complete endpoints block for stage 05, a gappy environments block for
    stage 03 (to force a follow-up that then returns a complete block), and prose
    otherwise. Matches on the quoted JSON keys that the question builder embeds via
    `json_hint` — reverse questions carry no json_hint and fall through to prose.
    Records every question asked."""

    def __init__(self) -> None:
        self.questions: list[str] = []

    def ask(self, question: str, notebook_url: str) -> _FakeAskResult:
        self.questions.append(question)
        if "still unfilled" in question:  # follow-up: re-emit the FULL block, now complete
            return _FakeAskResult('```json\n{"environments": [{"name": "prod", '
                                  '"base_url": "https://api", "version": "v1", '
                                  '"source": "api.pdf"}], "missing": []}\n```')
        if '"endpoints"' in question:
            return _FakeAskResult('```json\n{"endpoints": [{"method": "GET", '
                                  '"path": "/u", "summary": "s", "source": "api.pdf"}], '
                                  '"missing": []}\n```')
        if '"environments"' in question:  # stage 03 initial: null fields -> gaps
            return _FakeAskResult('```json\n{"environments": [{"name": "prod", '
                                  '"base_url": null, "version": null, "source": null}], '
                                  '"missing": ["base_url", "version"]}\n```')
        return _FakeAskResult("Prose answer. The sources cover the basics.")


def test_run_extraction_persists_and_returns(tmp_path: Path):
    store = ExtractionStore(tmp_path)
    adapter = _FakeAdapter()
    result = run_extraction(adapter, NB, store)

    # 10 stages: each has initial + reverse; structured stage 03 also has a followup.
    ids = [a.query_id for a in result.artifacts]
    assert "01-initial" in ids and "01-reverse" in ids
    assert "03-initial" in ids and "03-followup" in ids and "03-reverse" in ids
    assert "05-initial" in ids
    # stage 05 had no gaps -> no follow-up
    assert "05-followup" not in ids

    # persisted
    assert (tmp_path / "answers" / "03-followup.txt").exists()
    assert (tmp_path / "queries.jsonl").exists()


def test_followup_only_when_gaps(tmp_path: Path):
    store = ExtractionStore(tmp_path)
    result = run_extraction(_FakeAdapter(), NB, store)
    assert result.latest_structured("03").kind is QueryKind.FOLLOWUP
    assert result.latest_structured("05").kind is QueryKind.INITIAL


def test_questions_carry_notebook_and_context(tmp_path: Path):
    adapter = _FakeAdapter()
    run_extraction(adapter, NB, ExtractionStore(tmp_path))
    assert all(NB in q for q in adapter.questions)
    # later stages should include accumulated known-summary context
    assert any("Known so far" in q for q in adapter.questions)
