from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PlanItemStatus(str, Enum):
    SUPPORTED = "supported"
    CONFLICTING = "conflicting"
    MISSING = "missing"
    UNVERIFIED = "unverified"


class SourceCitation(BaseModel):
    query_id: str
    answer_path: str
    manifest_source: str | None = None
    locator: str | None = None


class _Cited(BaseModel):
    status: PlanItemStatus
    citations: list[SourceCitation] = Field(default_factory=list)


class EnvironmentEntry(_Cited):
    name: str | None = None
    base_url: str | None = None
    version: str | None = None


class SecuritySchemeEntry(_Cited):
    name: str | None = None
    type: str | None = None
    location: str | None = None
    details: str | None = None


class EndpointEntry(_Cited):
    method: str | None = None
    path: str | None = None
    summary: str | None = None
    parameters: list[dict] = Field(default_factory=list)
    request: dict | None = None
    responses: list[dict] = Field(default_factory=list)
    examples: list[dict] = Field(default_factory=list)


class SchemaEntry(_Cited):
    name: str | None = None
    fields: list[dict] = Field(default_factory=list)
    # The SKILL contract documents enums as a list of freeform strings
    # (e.g. "ItemType: 1=一般商品"); structured form [{"name", "values"}] is
    # also accepted. Keep the element type open so neither shape is dropped —
    # a non-list (e.g. "bad") is still rejected, which is the intended guard.
    enums: list = Field(default_factory=list)
    constraints: str | None = None


class ErrorEntry(_Cited):
    code: str | None = None
    meaning: str | None = None
    http_status: str | None = None


class OperationalEntry(_Cited):
    topic: str | None = None
    detail: str | None = None


class SystemGroup(BaseModel):
    name: str
    description: str | None = None


class MissingItem(BaseModel):
    area: str
    detail: str
    query_id: str | None = None


class SourceConflict(BaseModel):
    area: str
    detail: str
    query_id: str | None = None


class UnverifiedItem(BaseModel):
    area: str
    detail: str
    query_id: str | None = None


class NormalizationPlan(BaseModel):
    notebook_url: str
    source_inventory_note: str = ""
    overview_note: str = ""
    conflicts_note: str = ""
    system_groups: list[SystemGroup] = Field(default_factory=list)
    environments: list[EnvironmentEntry] = Field(default_factory=list)
    security_schemes: list[SecuritySchemeEntry] = Field(default_factory=list)
    endpoints: list[EndpointEntry] = Field(default_factory=list)
    schemas: list[SchemaEntry] = Field(default_factory=list)
    errors: list[ErrorEntry] = Field(default_factory=list)
    operational: list[OperationalEntry] = Field(default_factory=list)
    missing_items: list[MissingItem] = Field(default_factory=list)
    source_conflicts: list[SourceConflict] = Field(default_factory=list)
    unverified_items: list[UnverifiedItem] = Field(default_factory=list)
