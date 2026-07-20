from __future__ import annotations

from loop_apidoc.domain.builder import ContractClaimInput, build_grounded_contract
from loop_apidoc.domain.models import ClaimStatus, ContractMetadata, EvidenceBinding


def test_supported_environment_accepts_the_generic_evidence_binding():
    contract = build_grounded_contract(
        ContractMetadata(
            contract_id="demo",
            title="Demo API",
            version="1",
            source_set_id="sources",
            source_set_version="1",
            domain_version="1",
        ),
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
