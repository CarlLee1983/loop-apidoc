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
