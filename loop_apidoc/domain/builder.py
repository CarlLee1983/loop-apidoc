from __future__ import annotations

from typing import Any

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
        evidence_refs: tuple[str, ...],
    ) -> None:
        self.identity = identity
        self.claim_kind = claim_kind
        self.value = value
        self.status = status
        self.evidence_refs = evidence_refs


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
        evidence = tuple(
            EvidenceBinding(fragment_id=ref) for ref in claim.evidence_refs
        )
        contract_claims.append(
            ContractClaim(
                identity=claim.identity,
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
        value = dict(claim.value)
        value.setdefault("evidence", [item.model_dump() for item in evidence])
        values[field].append(model.model_validate(value))
    return GroundedApiContract(
        metadata=metadata,
        **{field: tuple(items) for field, items in values.items()},
        claims=tuple(contract_claims),
        gaps=tuple(gaps),
        conflicts=tuple(conflicts),
    )
