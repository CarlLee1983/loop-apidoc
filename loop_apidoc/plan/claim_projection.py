"""Pure legacy-plan projections into canonical material claim values.

The agent-native plan is still a compatibility representation, but both the
exact-evidence boundary and the shadow runtime must agree on which parts of a
plan item are material claims.  Keeping that projection here gives them one
deterministic definition without making the extraction gate depend on Core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loop_apidoc.domain.identity import (
    DomainIdentityError,
    canonical_operation_identity,
)
from loop_apidoc.plan.models import (
    Callback,
    ContractTestCase,
    CryptoScheme,
    EndpointEntry,
    EnvironmentEntry,
    ErrorEntry,
    FieldCondition,
    NormalizationPlan,
    OperationalEntry,
    SchemaEntry,
    SecuritySchemeEntry,
)


@dataclass(frozen=True)
class PlanClaimProjection:
    """One plan item expressed in the canonical claim-path value shape."""

    plan_location: str
    entry: Any
    claim_kind: str
    subject: str
    value: dict[str, Any]


def iter_plan_claim_projections(
    plan: NormalizationPlan,
) -> tuple[PlanClaimProjection, ...]:
    """Project every normalizable plan item in stable plan order."""

    projections: list[PlanClaimProjection] = []
    areas = (
        ("environments", "environment", _environment_value),
        ("endpoints", "operation", _operation_value),
        ("schemas", "schema", _schema_value),
        ("security_schemes", "security", _security_value),
        ("errors", "error", _error_value),
        ("operational", "operational_constraint", _operational_value),
    )
    for field, claim_kind, value_builder in areas:
        for index, entry in enumerate(getattr(plan, field)):
            location = f"{field}[{index}]"
            projections.append(
                PlanClaimProjection(
                    plan_location=location,
                    entry=entry,
                    claim_kind=claim_kind,
                    subject=_subject(entry, location),
                    value=value_builder(entry),
                )
            )

    integration = plan.integration
    if integration is not None:
        integration_areas = (
            ("crypto", "integration_mechanic", _crypto_value),
            ("callbacks", "webhook", _callback_value),
            ("field_conditions", "integration_mechanic", _condition_value),
            ("test_cases", "integration_mechanic", _test_case_value),
        )
        for field, claim_kind, value_builder in integration_areas:
            for index, entry in enumerate(getattr(integration, field)):
                location = f"integration.{field}[{index}]"
                projections.append(
                    PlanClaimProjection(
                        plan_location=location,
                        entry=entry,
                        claim_kind=claim_kind,
                        subject=_subject(entry, location),
                        value=value_builder(entry),
                    )
                )
    return tuple(projections)


def _subject(entry: Any, plan_location: str) -> str:
    if isinstance(entry, EnvironmentEntry):
        return entry.name or plan_location
    if isinstance(entry, EndpointEntry):
        if entry.method and entry.path:
            return f"{entry.method.strip().upper()} {entry.path}"
        return plan_location
    if isinstance(entry, SchemaEntry | SecuritySchemeEntry | CryptoScheme | Callback):
        return entry.name or plan_location
    if isinstance(entry, ErrorEntry):
        return entry.code or plan_location
    if isinstance(entry, OperationalEntry):
        return entry.topic or plan_location
    if isinstance(entry, FieldCondition):
        return entry.scope or plan_location
    if isinstance(entry, ContractTestCase):
        return entry.name or plan_location
    return plan_location


def _environment_value(entry: EnvironmentEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.name)
    if entry.base_url is not None:
        value["servers"] = [entry.base_url]
    return value


def _operation_value(entry: EndpointEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for field in ("method", "path", "summary", "server"):
        _put(value, field, getattr(entry, field))
    value["parameters"] = [_parameter_value(raw) for raw in entry.parameters]
    if entry.request and entry.request.get("schema_ref") is not None:
        value["request_schema_ref"] = entry.request["schema_ref"]
    value["responses"] = [_response_value(raw) for raw in entry.responses]
    if entry.security:
        value["security"] = list(entry.security)
    return value


def _parameter_value(raw: dict) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", raw.get("name"))
    _put(value, "location", raw.get("location") or raw.get("in"))
    if "required" in raw and raw["required"] is not None:
        value["required"] = raw["required"]
    _put(value, "schema_ref", raw.get("schema_ref"))
    return value


def _response_value(raw: dict) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "status_code", raw.get("status"))
    _put(value, "description", raw.get("description"))
    _put(value, "schema_ref", raw.get("schema_ref"))
    return value


def _schema_value(entry: SchemaEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.name)
    value["fields"] = [_schema_field_value(raw) for raw in entry.fields]
    return value


def _schema_field_value(raw: dict) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for field in ("name", "type", "schema_ref", "required", "condition"):
        if field in raw:
            _put(value, field, raw.get(field))
    return value


def _security_value(entry: SecuritySchemeEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.name)
    _put(value, "type", entry.type)
    return value


def _error_value(entry: ErrorEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "code", entry.code)
    _put(value, "description", entry.meaning)
    if entry.applicable_to:
        value["applicable_to"] = [
            _canonical_operation_reference(item)
            for item in entry.applicable_to
        ]
    return value


def _operational_value(entry: OperationalEntry) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "topic", entry.topic)
    _put(value, "detail", entry.detail)
    return value


def _crypto_value(entry: CryptoScheme) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "kind", entry.purpose)
    _put(value, "name", entry.name)
    steps = [step.desc for step in entry.payload_assembly if step.desc]
    if steps:
        value["steps"] = steps
    return value


def _callback_value(entry: Callback) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.name)
    _put(value, "verification", entry.verification)
    _put(value, "expected_response", entry.expected_response)
    return value


def _condition_value(entry: FieldCondition) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.scope)
    steps = [entry.when] if entry.when else []
    if steps:
        value["steps"] = steps
    return value


def _test_case_value(entry: ContractTestCase) -> dict[str, Any]:
    value: dict[str, Any] = {}
    _put(value, "name", entry.name)
    if entry.operation_ref is not None:
        value["operation_refs"] = [
            _canonical_operation_reference(entry.operation_ref)
        ]
    return value


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        target[key] = value


def _canonical_operation_reference(value: str) -> str:
    if value.startswith("operation:"):
        return value
    method, separator, path = value.strip().partition(" ")
    if not separator:
        return value
    try:
        return canonical_operation_identity(method, path)
    except DomainIdentityError:
        return value
