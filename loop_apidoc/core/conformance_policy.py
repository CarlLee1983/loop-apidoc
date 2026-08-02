from __future__ import annotations

from loop_apidoc.domain.conformance import (
    ConformanceRelationship,
    ConformanceRelationshipType,
    FeedbackRoute,
    ImplementationObservation,
    ObservationKind,
    ObservationOutcome,
)
from loop_apidoc.domain.models import ContractClaim, Operation


def verify_observation_target(
    observation: ImplementationObservation,
    claim: ContractClaim,
    operation: Operation,
) -> str | None:
    """Return a fail-closed error when an allowlisted observation is misbound."""
    kind = observation.kind
    value = claim.value
    if kind in {
        ObservationKind.OPERATION_SUCCESS,
        ObservationKind.RESPONSE_STATUS,
    }:
        belongs = (
            claim.claim_kind == "operation"
            and isinstance(value, dict)
            and str(value.get("method", "")).upper() == operation.method.upper()
            and value.get("path") == operation.path
        )
        if not belongs:
            return "observation claim does not belong to its operation"
        parts = observation.claim_path.split("/")
        if (
            len(parts) != 4
            or parts[1] != "responses"
            or not parts[2]
            or parts[3] != "status_code"
        ):
            return "observation kind and claim path are not allowlisted"
        return None

    if kind in {
        ObservationKind.RESPONSE_FIELD,
        ObservationKind.RESPONSE_JSON_TYPE,
    }:
        schema_name = value.get("name") if isinstance(value, dict) else None
        response_refs = {
            response.schema_ref
            for response in operation.responses
            if response.schema_ref is not None
        }
        belongs = (
            claim.claim_kind == "schema"
            and isinstance(schema_name, str)
            and any(
                reference == schema_name
                or reference.rsplit("/", 1)[-1] == schema_name
                for reference in response_refs
            )
        )
        if not belongs:
            return "observation claim does not belong to its operation response"
        expected_suffix = (
            "/name"
            if kind is ObservationKind.RESPONSE_FIELD
            else "/type"
        )
        if (
            not observation.claim_path.startswith("/fields/")
            or not observation.claim_path.endswith(expected_suffix)
        ):
            return "observation kind and claim path are not allowlisted"
        return None

    return f"unsupported observation kind: {kind.value}"


def route_feedback(
    relationships: tuple[ConformanceRelationship, ...]
) -> FeedbackRoute:
    kinds = {item.relationship for item in relationships}
    if ConformanceRelationshipType.CONTRADICTS in kinds:
        contradictions = tuple(
            item
            for item in relationships
            if item.relationship is ConformanceRelationshipType.CONTRADICTS
        )
        if all(is_high_risk(item) for item in contradictions):
            return FeedbackRoute.PROVIDER_CLARIFICATION
        if any(not item.normative_evidence_refs for item in contradictions):
            return FeedbackRoute.EXTRACTION_CORRECTION
        return FeedbackRoute.AMENDMENT_PROPOSAL
    if ConformanceRelationshipType.OUT_OF_SCOPE in kinds:
        return FeedbackRoute.ENVIRONMENT_CONFIGURATION_CORRECTION
    if ConformanceRelationshipType.INCONCLUSIVE in kinds:
        inconclusive = tuple(
            item
            for item in relationships
            if item.relationship is ConformanceRelationshipType.INCONCLUSIVE
        )
        if any(
            item.outcome
            in {
                ObservationOutcome.HARNESS_FAILURE,
                ObservationOutcome.FIXTURE_FAILURE,
            }
            for item in inconclusive
        ):
            return FeedbackRoute.IMPLEMENTATION_CORRECTION
        if any(
            item.outcome
            in {
                ObservationOutcome.DNS_FAILURE,
                ObservationOutcome.PROXY_FAILURE,
                ObservationOutcome.GATEWAY_FAILURE,
            }
            for item in inconclusive
        ):
            return FeedbackRoute.ENVIRONMENT_CONFIGURATION_CORRECTION
        if any(
            item.attempt_count >= 2
            and item.outcome
            in {
                ObservationOutcome.NETWORK_FAILURE,
                ObservationOutcome.TIMEOUT,
                ObservationOutcome.RATE_LIMITED,
            }
            for item in inconclusive
        ):
            return FeedbackRoute.PROVIDER_RUNTIME_REGRESSION_REVIEW
        return FeedbackRoute.NEEDS_EVIDENCE
    return FeedbackRoute.CLOSED_NO_CHANGE


_HIGH_RISK_CLAIM_KINDS = {
    "security",
    "amount_direction",
    "idempotency_rule",
    "line_currency_policy",
}
_HIGH_RISK_PATH_TERMS = (
    "required",
    "security",
    "authentication",
    "credential",
    "token",
    "crypt",
    "amount",
    "currency",
    "balance",
    "idempot",
    "transaction",
    "rate_limit",
    "business_meaning",
)


def is_high_risk(relationship: ConformanceRelationship) -> bool:
    if relationship.kind in {
        ObservationKind.OPERATION_SUCCESS,
        ObservationKind.RESPONSE_FIELD,
    }:
        return True
    if relationship.claim_kind in _HIGH_RISK_CLAIM_KINDS:
        return True
    target = f"{relationship.claim_identity}/{relationship.claim_path}".lower()
    return any(term in target for term in _HIGH_RISK_PATH_TERMS)
