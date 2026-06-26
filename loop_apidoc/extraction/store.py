from __future__ import annotations

from pathlib import Path

from loop_apidoc.extraction.models import AnswerArtifact, QueryRecord
from loop_apidoc.extraction.stages import QueryKind


class ExtractionStore:
    """Persists each query round to extraction/queries.jsonl and
    extraction/answers/<query_id>.txt without discarding prior rounds (spec §7.1)."""

    def __init__(self, extraction_dir: Path) -> None:
        self._dir = extraction_dir
        self._answers = extraction_dir / "answers"
        self._queries = extraction_dir / "queries.jsonl"
        # How many times each query_id has been recorded this run. Correction
        # re-runs reuse a query_id, so later writes get a versioned filename
        # instead of overwriting the prior round's artifact (spec §7.1 audit).
        self._counts: dict[str, int] = {}

    def record(
        self,
        *,
        query_id: str,
        stage_id: str,
        kind: QueryKind,
        question: str,
        answer: str,
        returncode: int,
    ) -> AnswerArtifact:
        self._answers.mkdir(parents=True, exist_ok=True)
        attempt = self._counts.get(query_id, 0) + 1
        self._counts[query_id] = attempt
        filename = f"{query_id}.txt" if attempt == 1 else f"{query_id}.r{attempt}.txt"
        answer_path = f"answers/{filename}"
        (self._answers / filename).write_text(answer, encoding="utf-8")
        record = QueryRecord(
            query_id=query_id, stage_id=stage_id, kind=kind, question=question,
            answer_path=answer_path, returncode=returncode,
        )
        with self._queries.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
        return AnswerArtifact(
            query_id=query_id, stage_id=stage_id, kind=kind, answer=answer,
            answer_path=answer_path, returncode=returncode,
        )
