from __future__ import annotations

from typing import Any

from loop_apidoc.domain.claim_paths import escape_segment
from loop_apidoc.domain.evidence import ClaimEvidenceRelationship
from loop_apidoc.domain.models import (
    ApiError,
    ClaimStatus,
    Conflict,
    ContractClaim,
    ContractMetadata,
    Environment,
    EvidenceBinding,
    Gap,
    GroundedApiContract,
    IntegrationMechanic,
    Operation,
    OperationalConstraint,
    Schema,
    SecurityScheme,
    Webhook,
)


class ContractClaimInput:
    def __init__(
        self,
        *,
        identity: str,
        claim_kind: str,
        value: Any,
        status: ClaimStatus,
        evidence_refs: tuple[str, ...] = (),
        support_relationships: tuple[ClaimEvidenceRelationship, ...] = (),
    ) -> None:
        self.identity = identity
        self.claim_kind = claim_kind
        self.value = value
        self.status = status
        self.evidence_refs = evidence_refs
        self.support_relationships = support_relationships


_MODEL_BY_KIND = {
    "environment": Environment,
    "operation": Operation,
    "webhook": Webhook,
    "schema": Schema,
    "security": SecurityScheme,
    "error": ApiError,
    "integration_mechanic": IntegrationMechanic,
    "operational_constraint": OperationalConstraint,
}
_FIELD_BY_KIND = {
    "environment": "environments",
    "operation": "operations",
    "webhook": "webhooks",
    "schema": "schemas",
    "security": "security",
    "error": "errors",
    "integration_mechanic": "integration_mechanics",
    "operational_constraint": "operational_constraints",
}


def build_grounded_contract(
    metadata: ContractMetadata,
    claims: tuple[ContractClaimInput, ...],
) -> GroundedApiContract:
    values: dict[str, list] = {field: [] for field in _FIELD_BY_KIND.values()}
    contract_claims: list[ContractClaim] = []
    gaps: list[Gap] = []
    conflicts: list[Conflict] = []
    for claim in sorted(claims, key=lambda item: item.identity):
        semantic_evidence = tuple(
            EvidenceBinding(
                fragment_id=relationship.fragment_id,
                relationship_id=relationship.id,
                claim_identity=relationship.claim_identity,
                claim_path=relationship.claim_path,
                relationship=relationship.relationship,
            )
            for relationship in claim.support_relationships
        )
        semantic_fragment_ids = {
            binding.fragment_id for binding in semantic_evidence
        }
        legacy_evidence = tuple(
            EvidenceBinding(fragment_id=ref) for ref in claim.evidence_refs
            if ref not in semantic_fragment_ids
        )
        evidence = semantic_evidence + legacy_evidence
        contract_claims.append(
            ContractClaim(
                identity=claim.identity,
                claim_kind=claim.claim_kind,
                status=claim.status,
                value=claim.value,
                evidence=evidence,
            )
        )
        if claim.status is ClaimStatus.MISSING:
            gaps.append(
                Gap(
                    identity=claim.identity,
                    reason="source fact missing",
                    evidence=evidence,
                )
            )
            continue
        if claim.status is ClaimStatus.CONFLICTING:
            raw_values = (
                claim.value if isinstance(claim.value, tuple | list) else (claim.value,)
            )
            conflicts.append(
                Conflict(
                    identity=claim.identity, values=tuple(raw_values), evidence=evidence
                )
            )
            continue
        if claim.status not in {ClaimStatus.SUPPORTED, ClaimStatus.WAIVED}:
            continue
        model = _MODEL_BY_KIND.get(claim.claim_kind)
        field = _FIELD_BY_KIND.get(claim.claim_kind)
        if model is None or field is None or not isinstance(claim.value, dict):
            continue
        value = _route_child_evidence(
            claim.claim_kind,
            claim.value,
            semantic_evidence,
        )
        value["evidence"] = [item.model_dump(mode="json") for item in evidence]
        values[field].append(model.model_validate(value))
    return GroundedApiContract(
        metadata=metadata,
        **{field: tuple(items) for field, items in values.items()},
        claims=tuple(contract_claims),
        gaps=tuple(gaps),
        conflicts=tuple(conflicts),
    )


def _route_child_evidence(
    claim_kind: str,
    raw_value: dict[str, Any],
    evidence: tuple[EvidenceBinding, ...],
) -> dict[str, Any]:
    value = dict(raw_value)
    value.pop("evidence", None)
    if claim_kind == "operation":
        value["parameters"] = [
            _operation_child(item, evidence, "parameters")
            for item in raw_value.get("parameters") or ()
        ]
        value["responses"] = [
            _operation_child(item, evidence, "responses")
            for item in raw_value.get("responses") or ()
        ]
    elif claim_kind == "schema":
        value["fields"] = [
            _schema_field_child(item, evidence)
            for item in raw_value.get("fields") or ()
        ]
    return value


def _operation_child(
    raw_child: Any,
    evidence: tuple[EvidenceBinding, ...],
    collection: str,
) -> Any:
    if not isinstance(raw_child, dict):
        return raw_child
    child = dict(raw_child)
    child.pop("evidence", None)
    if collection == "parameters":
        name = child.get("name")
        location = child.get("location")
        if name is None or location is None:
            return child
        prefix = (
            f"/parameters/{escape_segment(str(location))}/{escape_segment(str(name))}/"
        )
    else:
        status = child.get("status_code")
        if status is None:
            return child
        prefix = f"/responses/{escape_segment(str(status))}/"
    bindings = _bindings_with_prefix(evidence, prefix)
    if bindings:
        child["evidence"] = [
            binding.model_dump(mode="json") for binding in bindings
        ]
    return child


def _schema_field_child(
    raw_child: Any,
    evidence: tuple[EvidenceBinding, ...],
) -> Any:
    if not isinstance(raw_child, dict):
        return raw_child
    child = dict(raw_child)
    child.pop("evidence", None)
    name = child.get("name")
    if name is None:
        return child
    prefix = f"/fields/{escape_segment(str(name))}/"
    bindings = _bindings_with_prefix(evidence, prefix)
    if bindings:
        child["evidence"] = [
            binding.model_dump(mode="json") for binding in bindings
        ]
    return child


def _bindings_with_prefix(
    evidence: tuple[EvidenceBinding, ...],
    prefix: str,
) -> tuple[EvidenceBinding, ...]:
    return tuple(
        binding
        for binding in evidence
        if binding.claim_path is not None and binding.claim_path.startswith(prefix)
    )
