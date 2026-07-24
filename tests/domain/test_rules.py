from __future__ import annotations

from loop_apidoc.domain.models import (
    ClaimStatus,
    ContractClaim,
    ContractMetadata,
    EvidenceBinding,
    GraphqlOperationKind,
    GraphqlTransportBinding,
    GroundedApiContract,
    HttpTransportBinding,
    Interaction,
    InteractionMode,
    Operation,
    Response,
)
from loop_apidoc.domain.evidence import SupportRelationshipType
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
        "CLAIM_SEMANTIC_SUPPORT_REQUIRED",
        "OPERATION_EVIDENCE_REQUIRED",
        "SCHEMA_REFERENCE_UNRESOLVED",
    }


def test_rules_apply_response_and_evidence_requirements_to_http_interactions():
    contract = GroundedApiContract(
        metadata=_metadata(),
        interactions=(
            Interaction(
                identity="interaction:http:GET:/health",
                mode=InteractionMode.REQUEST_REPLY,
                binding=HttpTransportBinding(method="GET", path="/health"),
            ),
        ),
    )

    findings = ApiDomainRulePack(version="1").evaluate(contract)

    assert {finding.code for finding in findings} == {
        "INTERACTION_EVIDENCE_REQUIRED",
        "INTERACTION_RESPONSE_REQUIRED",
    }


def test_rules_apply_common_evidence_requirement_to_graphql_interactions():
    contract = GroundedApiContract(
        metadata=_metadata(),
        interactions=(
            Interaction(
                identity="interaction:graphql:query:product",
                mode=InteractionMode.REQUEST_REPLY,
                binding=GraphqlTransportBinding(
                    operation_kind=GraphqlOperationKind.QUERY,
                    root_field="product",
                ),
            ),
        ),
    )

    findings = ApiDomainRulePack(version="1").evaluate(contract)

    assert {finding.code for finding in findings} == {"INTERACTION_EVIDENCE_REQUIRED"}


def test_fragment_id_only_binding_does_not_satisfy_semantic_rule():
    evidence = (EvidenceBinding(fragment_id="fragment-1"),)
    contract = GroundedApiContract(
        metadata=_metadata(),
        claims=(
            ContractClaim(
                identity="claim:scalar:currency:definition",
                claim_kind="scalar",
                status=ClaimStatus.SUPPORTED,
                value="USD",
                evidence=evidence,
            ),
        ),
    )

    findings = ApiDomainRulePack(version="2").evaluate(contract)

    assert "CLAIM_SEMANTIC_SUPPORT_REQUIRED" in {
        finding.code for finding in findings
    }


def test_supported_claim_with_incomplete_path_coverage_is_rejected():
    evidence = (
        EvidenceBinding(
            fragment_id="fragment-summary",
            relationship_id="relationship-summary",
            claim_identity="claim:operation:GET /health:definition",
            claim_path="/summary",
            relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
        ),
    )
    contract = GroundedApiContract(
        metadata=_metadata(),
        claims=(
            ContractClaim(
                identity="claim:operation:GET /health:definition",
                claim_kind="operation",
                status=ClaimStatus.SUPPORTED,
                value={
                    "method": "GET",
                    "path": "/health",
                    "summary": "Health",
                    "responses": [{"status_code": "200", "description": "OK"}],
                },
                evidence=evidence,
            ),
        ),
    )

    assert "CLAIM_SUPPORT_COVERAGE_INCOMPLETE" in {
        finding.code for finding in ApiDomainRulePack(version="2").evaluate(contract)
    }


def test_contradiction_relationship_surfaces_domain_finding():
    evidence = (
        EvidenceBinding(
            fragment_id="fragment-a",
            relationship_id="relationship-a",
            claim_identity="claim:scalar:currency:definition",
            claim_path="",
            relationship=SupportRelationshipType.CONTRADICTS,
        ),
    )
    contract = GroundedApiContract(
        metadata=_metadata(),
        claims=(
            ContractClaim(
                identity="claim:scalar:currency:definition",
                claim_kind="scalar",
                status=ClaimStatus.CONFLICTING,
                value="USD",
                evidence=evidence,
            ),
        ),
    )

    assert "CLAIM_EVIDENCE_CONTRADICTS" in {
        finding.code for finding in ApiDomainRulePack(version="2").evaluate(contract)
    }


def test_valid_grounded_operation_passes_rules():
    value = {
        "method": "GET",
        "path": "/health",
        "responses": [{"status_code": "200", "description": "OK"}],
    }
    paths = ("/method", "/path", "/responses/200/description", "/responses/200/status_code")
    evidence = tuple(
        EvidenceBinding(
            fragment_id=f"fragment-{index}",
            relationship_id=f"relationship-{index}",
            claim_identity="claim:operation:GET /health:definition",
            claim_path=path,
            relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
        )
        for index, path in enumerate(paths)
    )
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
                identity="claim:operation:GET /health:definition",
                claim_kind="operation",
                status=ClaimStatus.SUPPORTED,
                value=value,
                evidence=evidence,
            ),
        ),
    )

    assert ApiDomainRulePack(version="2").evaluate(contract) == ()
