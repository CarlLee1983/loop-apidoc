from __future__ import annotations

from pydantic import BaseModel, Field

from loop_apidoc.plan.models import PlanItemStatus


class ProvenanceEntry(BaseModel):
    target: str
    status: PlanItemStatus
    manifest_source: str | None = None
    query_id: str | None = None
    answer_path: str | None = None
    locator: str | None = None


class ProvenanceDocument(BaseModel):
    notebook_url: str
    entries: list[ProvenanceEntry] = Field(default_factory=list)


class GenerateResult(BaseModel):
    openapi: dict
    markdown: str
    provenance: ProvenanceDocument
    integration: dict | None = None
