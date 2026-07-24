from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import Field

from loop_apidoc.domain.base import FrozenModel as FrozenModel
from loop_apidoc.domain.evidence import SupportRelationshipType


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    MISSING = "missing"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"
    WAIVED = "waived"
    SUPERSEDED = "superseded"


class EvidenceBinding(FrozenModel):
    fragment_id: str
    relationship_id: str | None = None
    claim_identity: str | None = None
    claim_path: str | None = None
    relationship: SupportRelationshipType | None = None
    locator: str | None = None


class ContractMetadata(FrozenModel):
    contract_id: str
    title: str
    # A source may state a title but omit its document/API version. The Canonical
    # API Contract preserves that gap as null; a format-specific projection can
    # add a visibly marked placeholder when its target format requires a string.
    version: str | None = None
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


class InteractionMode(str, Enum):
    REQUEST_REPLY = "request_reply"
    PUBLISH = "publish"
    SUBSCRIBE = "subscribe"
    STREAM = "stream"


class HttpTransportBinding(FrozenModel):
    """HTTP-specific details carried by a protocol-neutral interaction."""

    transport: Literal["http"] = "http"
    method: str
    path: str
    server: str | None = None
    parameters: tuple[Parameter, ...] = ()
    request_schema_ref: str | None = None
    responses: tuple[Response, ...] = ()
    security: tuple[str, ...] = ()
    evidence: tuple[EvidenceBinding, ...] = ()


class GraphqlOperationKind(str, Enum):
    QUERY = "query"
    MUTATION = "mutation"
    SUBSCRIPTION = "subscription"


class GraphqlTransportBinding(FrozenModel):
    """GraphQL operation details carried by a protocol-neutral interaction."""

    transport: Literal["graphql"] = "graphql"
    operation_kind: GraphqlOperationKind
    root_field: str
    output_schema_ref: str | None = None
    output_required: bool | None = None
    evidence: tuple[EvidenceBinding, ...] = ()


class AsyncApiDirection(str, Enum):
    PUBLISH = "publish"
    SUBSCRIBE = "subscribe"


class AsyncApiTransportBinding(FrozenModel):
    """AsyncAPI message details carried by a protocol-neutral interaction."""

    transport: Literal["asyncapi"] = "asyncapi"
    channel: str
    channel_address: str | None = None
    direction: AsyncApiDirection
    message_name: str
    payload_schema_ref: str | None = None
    evidence: tuple[EvidenceBinding, ...] = ()


TransportBinding = Annotated[
    HttpTransportBinding | GraphqlTransportBinding | AsyncApiTransportBinding,
    Field(discriminator="transport"),
]


class Interaction(FrozenModel):
    """A source-grounded interaction with a transport-specific binding."""

    identity: str
    mode: InteractionMode
    binding: TransportBinding
    summary: str | None = None
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
    claim_kind: str | None = None
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
    interactions: tuple[Interaction, ...] = ()
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
