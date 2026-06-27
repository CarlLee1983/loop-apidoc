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
    # Source-stated grouping labels and the names of security_schemes this
    # endpoint requires; both feed the OpenAPI operation (tags / security).
    tags: list[str] = Field(default_factory=list)
    security: list[str] = Field(default_factory=list)


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


class CryptoStep(BaseModel):
    step: int | None = None
    desc: str | None = None
    fields: list[str] = Field(default_factory=list)


class KeySource(BaseModel):
    key: str | None = None
    iv: str | None = None
    note: str | None = None


class CryptoVerify(BaseModel):
    field: str | None = None
    method: str | None = None
    desc: str | None = None


class CryptoScheme(_Cited):
    name: str | None = None
    purpose: str | None = None  # request | response | callback | signature
    algorithm: str | None = None
    mode: str | None = None
    padding: str | None = None
    encoding: str | None = None
    key_source: KeySource | None = None
    payload_assembly: list[CryptoStep] = Field(default_factory=list)
    verify: CryptoVerify | None = None


class Callback(_Cited):
    name: str | None = None
    trigger: str | None = None
    transport: str | None = None
    payload_ref: str | None = None
    verification: str | None = None
    expected_response: str | None = None


class FieldCondition(_Cited):
    scope: str | None = None
    rule: str | None = None
    when: str | None = None
    then_required: list[str] = Field(default_factory=list)


class ContractTestCase(_Cited):
    name: str | None = None
    operation_ref: str | None = None
    request: dict | None = None
    response: dict | None = None


class ContractMissing(BaseModel):
    area: str
    detail: str


class IntegrationContract(BaseModel):
    version: str = "1.0"
    crypto: list[CryptoScheme] = Field(default_factory=list)
    callbacks: list[Callback] = Field(default_factory=list)
    field_conditions: list[FieldCondition] = Field(default_factory=list)
    test_cases: list[ContractTestCase] = Field(default_factory=list)
    missing: list[ContractMissing] = Field(default_factory=list)


class SystemGroup(BaseModel):
    name: str
    description: str | None = None
    # Source-stated document/API version (e.g. "NDNF-1.2.2"); feeds info.version.
    version: str | None = None


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
    integration: IntegrationContract | None = None

    @property
    def resolved_title(self) -> str | None:
        """Source-stated document/API title for OpenAPI `info.title`."""
        return self.system_groups[0].name if self.system_groups else None

    @property
    def resolved_version(self) -> str | None:
        """Version for OpenAPI `info.version`: the source document version takes
        precedence over a stated environment/API version. Generators and
        provenance MUST agree, so both read this single resolution."""
        group = self.system_groups[0] if self.system_groups else None
        doc_version = group.version if group else None
        env_version = next((e.version for e in self.environments if e.version), None)
        return doc_version or env_version
