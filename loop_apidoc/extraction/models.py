from __future__ import annotations

from pydantic import BaseModel, Field

from loop_apidoc.extraction.stages import QueryKind


class QueryRecord(BaseModel):
    query_id: str
    stage_id: str
    kind: QueryKind
    question: str
    answer_path: str
    returncode: int


class AnswerArtifact(BaseModel):
    query_id: str
    stage_id: str
    kind: QueryKind
    answer: str
    answer_path: str
    returncode: int


class ExtractionResult(BaseModel):
    notebook_url: str
    artifacts: list[AnswerArtifact] = Field(default_factory=list)

    def for_stage(self, stage_id: str) -> list[AnswerArtifact]:
        return [a for a in self.artifacts if a.stage_id == stage_id]

    def initial(self, stage_id: str) -> AnswerArtifact | None:
        for art in self.artifacts:
            if art.stage_id == stage_id and art.kind is QueryKind.INITIAL:
                return art
        return None

    def latest_structured(self, stage_id: str) -> AnswerArtifact | None:
        followup = None
        initial = None
        for art in self.artifacts:
            if art.stage_id != stage_id:
                continue
            if art.kind is QueryKind.FOLLOWUP:
                followup = art
            elif art.kind is QueryKind.INITIAL:
                initial = art
        return followup or initial
