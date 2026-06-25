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
        answer_path = f"answers/{query_id}.txt"
        (self._answers / f"{query_id}.txt").write_text(answer, encoding="utf-8")
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
