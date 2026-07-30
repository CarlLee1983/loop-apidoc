from __future__ import annotations

from loop_apidoc.domain.builder import ContractClaimInput, build_grounded_contract
from loop_apidoc.domain.evidence import (
    ClaimEvidenceRelationship,
    SupportRelationshipType,
    VerificationMethod,
    fragment_digest,
)
from loop_apidoc.domain.models import ClaimStatus, ContractMetadata, EvidenceBinding


def _metadata() -> ContractMetadata:
    return ContractMetadata(
        contract_id="demo",
        title="Demo API",
        version="1",
        source_set_id="sources",
        source_set_version="1",
        domain_version="1",
    )


def _relationship(
    *,
    claim_identity: str,
    claim_path: str,
    fragment_id: str,
    relationship: SupportRelationshipType,
) -> ClaimEvidenceRelationship:
    return ClaimEvidenceRelationship(
        id=f"relationship-{fragment_id}",
        claim_identity=claim_identity,
        claim_path=claim_path,
        fragment_id=fragment_id,
        relationship=relationship,
        verification_method=VerificationMethod.TABLE_CELL_MAPPING,
        claim_value_digest=fragment_digest("true"),
        evidence_value_digest=fragment_digest("true"),
        observed_value=True,
        reason_code="TABLE_CELL_VALUE_MATCH",
    )


def test_supported_environment_accepts_the_generic_evidence_binding():
    contract = build_grounded_contract(
        _metadata(),
        (
            ContractClaimInput(
                identity="claim:environment:prod:definition",
                claim_kind="environment",
                value={"name": "prod", "servers": ["https://api.example.test"]},
                status=ClaimStatus.SUPPORTED,
                evidence_refs=("fragment-manual",),
            ),
        ),
    )

    assert contract.environments[0].evidence == (
        EvidenceBinding(fragment_id="fragment-manual"),
    )
    assert contract.payment_profile is None


def test_builder_attaches_parameter_binding_to_exact_child():
    identity = "claim:operation:POST /payments:definition"
    relationship = _relationship(
        claim_identity=identity,
        claim_path="/parameters/query/amount/required",
        fragment_id="fragment-required",
        relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
    )

    contract = build_grounded_contract(
        _metadata(),
        (
            ContractClaimInput(
                identity=identity,
                claim_kind="operation",
                value={
                    "method": "POST",
                    "path": "/payments",
                    "parameters": [
                        {
                            "name": "amount",
                            "location": "query",
                            "required": True,
                        }
                    ],
                    "responses": [{"status_code": "200", "description": "OK"}],
                },
                status=ClaimStatus.SUPPORTED,
                support_relationships=(relationship,),
            ),
        ),
    )

    binding = contract.operations[0].parameters[0].evidence[0]
    assert binding.relationship_id == relationship.id
    assert binding.claim_path == relationship.claim_path
    assert binding.relationship == SupportRelationshipType.EXPLICIT_SUPPORT


def test_builder_routes_a_supported_http_interaction_into_the_canonical_contract():
    contract = build_grounded_contract(
        _metadata(),
        (
            ContractClaimInput(
                identity="interaction:http:GET:/health",
                claim_kind="interaction",
                value={
                    "identity": "interaction:http:GET:/health",
                    "mode": "request_reply",
                    "binding": {
                        "transport": "http",
                        "method": "GET",
                        "path": "/health",
                        "responses": [{"status_code": "200", "description": "OK"}],
                    },
                },
                status=ClaimStatus.SUPPORTED,
                evidence_refs=("fragment-health",),
            ),
        ),
    )

    assert contract.interactions[0].binding.path == "/health"
    assert contract.interactions[0].evidence == (
        EvidenceBinding(fragment_id="fragment-health"),
    )


def test_builder_routes_payment_semantics_into_an_optional_profile():
    contract = build_grounded_contract(
        _metadata(),
        (
            ContractClaimInput(
                identity="claim:transport-policy:http-defaults:definition",
                claim_kind="transport_policy",
                value={
                    "name": "HTTP defaults",
                    "protocol": "HTTPS",
                    "methods": ["POST"],
                    "operation_refs": ["operation:POST:/deposit"],
                },
                status=ClaimStatus.SUPPORTED,
            ),
            ContractClaimInput(
                identity="claim:amount-direction:deposit:definition",
                claim_kind="amount_direction",
                value={
                    "operation_ref": "operation:POST:/deposit",
                    "balance_effect": "credit",
                    "amount_sign": "positive",
                    "precision": "12,4",
                },
                status=ClaimStatus.SUPPORTED,
            ),
            ContractClaimInput(
                identity="claim:idempotency-rule:9:definition",
                claim_kind="idempotency_rule",
                value={
                    "operation_refs": ["operation:POST:/deposit"],
                    "code": "9",
                    "meaning": "Duplicate transaction.",
                    "action": "Treat the original transaction as processed.",
                },
                status=ClaimStatus.SUPPORTED,
            ),
            ContractClaimInput(
                identity="claim:line-currency-policy:agent:definition",
                claim_kind="line_currency_policy",
                value={
                    "scope": "Agent line",
                    "policy": "single",
                    "currency_binding": "agent",
                    "operation_refs": ["operation:POST:/deposit"],
                },
                status=ClaimStatus.SUPPORTED,
            ),
        ),
    )

    assert contract.transport_policies[0].protocol == "HTTPS"
    assert contract.idempotency_rules[0].action == (
        "Treat the original transaction as processed."
    )
    assert contract.payment_profile is not None
    assert contract.payment_profile.amount_directions[0].balance_effect == "credit"
    assert contract.payment_profile.line_currency_policies[0].policy == "single"
    assert "amount_directions" not in type(contract).model_fields
    assert "line_currency_policies" not in type(contract).model_fields
