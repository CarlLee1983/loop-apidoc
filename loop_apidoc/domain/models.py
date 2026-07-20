from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    MISSING = "missing"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"
    WAIVED = "waived"
    SUPERSEDED = "superseded"


class EvidenceBinding(FrozenModel):
    fragment_id: str
    locator: str | None = None


class ContractMetadata(FrozenModel):
    contract_id: str
    title: str
    version: str
    source_set_id: str
    source_set_version: str
    domain_version: str


class Environment(FrozenModel):
    name: str
    servers: tuple[str, ...] = ()
    evidence: tuple[EvidenceBinding, ...] = ()


class Parameter(FrozenModel):
    name: str
    location: str
    required: bool | None = None
    schema_ref: str | None = None
    evidence: tuple[EvidenceBinding, ...] = ()


class Response(FrozenModel):
    status_code: str
    description: str | None = None
    schema_ref: str | None = None
    evidence: tuple[EvidenceBinding, ...] = ()


class Operation(FrozenModel):
    method: str
    path: str
    summary: str | None = None
    server: str | None = None
    parameters: tuple[Parameter, ...] = ()
    request_schema_ref: str | None = None
    responses: tuple[Response, ...] = ()
    security: tuple[str, ...] = ()
    evidence: tuple[EvidenceBinding, ...] = ()


class Webhook(FrozenModel):
    name: str
    callback_path: str | None = None
    verification: str | None = None
    expected_response: str | None = None
    evidence: tuple[EvidenceBinding, ...] = ()


class SchemaField(FrozenModel):
    name: str
    type: str | None = None
    schema_ref: str | None = None
    required: bool | None = None
    condition: str | None = None
    evidence: tuple[EvidenceBinding, ...] = ()


class Schema(FrozenModel):
    name: str
    fields: tuple[SchemaField, ...] = ()
    evidence: tuple[EvidenceBinding, ...] = ()


class SecurityScheme(FrozenModel):
    name: str
    type: str
    evidence: tuple[EvidenceBinding, ...] = ()


class ApiError(FrozenModel):
    code: str
    description: str | None = None
    applicable_to: tuple[str, ...] = ()
    evidence: tuple[EvidenceBinding, ...] = ()


class IntegrationMechanic(FrozenModel):
    name: str
    kind: str | None = None
    operation_refs: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    evidence: tuple[EvidenceBinding, ...] = ()


class OperationalConstraint(FrozenModel):
    topic: str
    detail: str
    evidence: tuple[EvidenceBinding, ...] = ()


class ContractClaim(FrozenModel):
    identity: str
    status: ClaimStatus
    value: Any = None
    evidence: tuple[EvidenceBinding, ...] = ()


class Gap(FrozenModel):
    identity: str
    reason: str
    evidence: tuple[EvidenceBinding, ...] = ()


class Conflict(FrozenModel):
    identity: str
    values: tuple[Any, ...]
    evidence: tuple[EvidenceBinding, ...] = ()


class WaiverRecord(FrozenModel):
    identity: str
    reason: str
    approved_by: str
    expires_at: datetime
    scope: tuple[str, ...] = ()


class GroundedApiContract(FrozenModel):
    metadata: ContractMetadata
    environments: tuple[Environment, ...] = ()
    operations: tuple[Operation, ...] = ()
    webhooks: tuple[Webhook, ...] = ()
    schemas: tuple[Schema, ...] = ()
    security: tuple[SecurityScheme, ...] = ()
    errors: tuple[ApiError, ...] = ()
    integration_mechanics: tuple[IntegrationMechanic, ...] = ()
    operational_constraints: tuple[OperationalConstraint, ...] = ()
    claims: tuple[ContractClaim, ...] = ()
    gaps: tuple[Gap, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    waivers: tuple[WaiverRecord, ...] = ()
