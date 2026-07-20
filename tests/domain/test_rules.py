from __future__ import annotations

from loop_apidoc.domain.models import (
    ClaimStatus,
    ContractClaim,
    ContractMetadata,
    GroundedApiContract,
    Operation,
    Response,
)
from loop_apidoc.domain.rules import ApiDomainRulePack


def _metadata() -> ContractMetadata:
    return ContractMetadata(
        contract_id="contract-1",
        title="Payments",
        version="1",
        source_set_id="sources",
        source_set_version="1",
        domain_version="1",
    )


def test_rules_report_dangling_schema_and_missing_evidence():
    contract = GroundedApiContract(
        metadata=_metadata(),
        operations=(
            Operation(
                method="POST",
                path="/payments",
                responses=(Response(status_code="200", schema_ref="Missing"),),
            ),
        ),
        claims=(
            ContractClaim(
                identity="claim:operation:POST:/payments:exists",
                status=ClaimStatus.SUPPORTED,
            ),
        ),
    )

    findings = ApiDomainRulePack(version="1").evaluate(contract)

    assert {finding.code for finding in findings} == {
        "CLAIM_EVIDENCE_REQUIRED",
        "OPERATION_EVIDENCE_REQUIRED",
        "SCHEMA_REFERENCE_UNRESOLVED",
    }


def test_valid_grounded_operation_passes_rules():
    from loop_apidoc.domain.models import EvidenceBinding

    evidence = (EvidenceBinding(fragment_id="fragment-1"),)
    contract = GroundedApiContract(
        metadata=_metadata(),
        operations=(
            Operation(
                method="GET",
                path="/health",
                responses=(Response(status_code="200", description="OK"),),
                evidence=evidence,
            ),
        ),
        claims=(
            ContractClaim(
                identity="claim:operation:GET:/health:exists",
                status=ClaimStatus.SUPPORTED,
                evidence=evidence,
            ),
        ),
    )

    assert ApiDomainRulePack(version="1").evaluate(contract) == ()
