from __future__ import annotations

from datetime import datetime, timezone

import pytest

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    Callback,
    ContractTestCase,
    CryptoScheme,
    CryptoStep,
    EndpointEntry,
    EnvironmentEntry,
    ErrorEntry,
    FieldCondition,
    IntegrationContract,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SchemaEntry,
    SecuritySchemeEntry,
    SourceCitation,
    SystemGroup,
)
from loop_apidoc.shadow.bridge import (
    SHADOW_RUNTIME_IDENTITY,
    SHADOW_RUNTIME_VERSION,
    ShadowMetadataError,
    build_contract_metadata,
    build_evidence,
    build_runtime_result,
)


NOW = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
CITATION = SourceCitation(
    query_id="06-ep0",
    answer_path="answer.json",
    manifest_source="manual.md",
    locator="p.2",
)


def _bridge():
    manifest = Manifest(
        sources_root="/sources",
        generated_at=NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=10,
                sha256="a" * 64,
                scanned_at=NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    return build_evidence(manifest, NOW)


def _plan(**updates) -> NormalizationPlan:
    data = {
        "notebook_url": "",
        "system_groups": [SystemGroup(name="Demo API", version="2026-07")],
    }
    data.update(updates)
    return NormalizationPlan(**data)


def test_supported_endpoint_uses_only_typed_source_values_and_evidence():
    endpoint = EndpointEntry(
        status=PlanItemStatus.SUPPORTED,
        citations=[CITATION],
        method="GET",
        path="/ping",
        summary="Health",
        parameters=[
            {
                "name": "verbose",
                "in": "query",
                "required": False,
                "schema_ref": "Verbose",
                "type": "boolean",
            }
        ],
        request={"schema_ref": "PingRequest", "content_type": "application/json"},
        responses=[
            {
                "status": "200",
                "description": "OK",
                "schema_ref": "PingResponse",
                "content_type": "application/json",
            }
        ],
        examples=[{"response": {"ok": True}}],
        tags=["Health"],
    )

    result = build_runtime_result(_plan(endpoints=[endpoint]), _bridge())

    proposal = result.claim_proposals[0]
    assert proposal.claim_kind == "operation"
    assert proposal.subject == "GET /ping"
    assert proposal.predicate == "definition"
    assert proposal.value == {
        "method": "GET",
        "path": "/ping",
        "summary": "Health",
        "parameters": [
            {
                "name": "verbose",
                "location": "query",
                "required": False,
                "schema_ref": "Verbose",
            }
        ],
        "request_schema_ref": "PingRequest",
        "responses": [
            {
                "status_code": "200",
                "description": "OK",
                "schema_ref": "PingResponse",
            }
        ],
    }
    assert proposal.evidence_refs == _bridge().resolve_citation("manual.md")
    assert proposal.confidence is None
    assert proposal.runtime_identity == SHADOW_RUNTIME_IDENTITY
    assert result.runtime_identity == SHADOW_RUNTIME_IDENTITY
    assert result.runtime_version == SHADOW_RUNTIME_VERSION


def test_unverified_value_has_no_evidence_and_missing_value_is_none():
    unverified = EndpointEntry(
        status=PlanItemStatus.UNVERIFIED,
        citations=[CITATION],
        method="GET",
        path="/unverified",
        responses=[{"status": "200"}],
    )
    missing = SchemaEntry(
        status=PlanItemStatus.MISSING,
        citations=[],
        name="MissingPayload",
    )

    result = build_runtime_result(
        _plan(endpoints=[unverified], schemas=[missing]), _bridge()
    )

    by_kind = {proposal.claim_kind: proposal for proposal in result.claim_proposals}
    assert by_kind["operation"].value["path"] == "/unverified"
    assert by_kind["operation"].evidence_refs == ()
    assert by_kind["schema"].value is None
    assert by_kind["schema"].evidence_refs == ()


def test_all_plan_areas_map_to_documented_claim_kinds():
    cited = {"status": PlanItemStatus.SUPPORTED, "citations": [CITATION]}
    integration = IntegrationContract(
        crypto=[
            CryptoScheme(
                **cited,
                name="RequestCipher",
                purpose="encryption",
                payload_assembly=[CryptoStep(step=1, desc="join fields")],
            )
        ],
        callbacks=[
            Callback(
                **cited,
                name="payment.updated",
                verification="HMAC",
                expected_response="200 OK",
            )
        ],
        field_conditions=[
            FieldCondition(
                **cited,
                scope="Payment.amount",
                rule="conditional",
                when="currency is TWD",
                then_required=["amount"],
            )
        ],
        test_cases=[
            ContractTestCase(
                **cited,
                name="pay success",
                operation_ref="POST /payments",
                request={"amount": 100},
                response={"status": "ok"},
            )
        ],
    )
    plan = _plan(
        environments=[
            EnvironmentEntry(
                **cited, name="prod", base_url="https://api.example.test"
            )
        ],
        security_schemes=[
            SecuritySchemeEntry(**cited, name="ApiKey", type="apiKey")
        ],
        schemas=[SchemaEntry(**cited, name="Payment", fields=[])],
        errors=[
            ErrorEntry(
                **cited,
                code="E001",
                meaning="invalid",
                applicable_to=["operation:POST:/payments"],
            )
        ],
        operational=[
            OperationalEntry(**cited, topic="rate limit", detail="10 requests/s")
        ],
        integration=integration,
    )

    result = build_runtime_result(plan, _bridge())

    assert [proposal.claim_kind for proposal in result.claim_proposals] == [
        "environment",
        "schema",
        "security",
        "error",
        "operational_constraint",
        "integration_mechanic",
        "webhook",
        "integration_mechanic",
        "integration_mechanic",
    ]


def test_operation_references_use_domain_canonical_identity():
    cited = {"status": PlanItemStatus.SUPPORTED, "citations": [CITATION]}
    plan = _plan(
        errors=[
            ErrorEntry(
                **cited,
                code="E001",
                meaning="invalid",
                applicable_to=["POST /payments"],
            )
        ],
        integration=IntegrationContract(
            test_cases=[
                ContractTestCase(
                    **cited,
                    name="payment succeeds",
                    operation_ref="POST /payments",
                )
            ]
        ),
    )

    result = build_runtime_result(plan, _bridge())

    assert result.claim_proposals[0].value["applicable_to"] == [
        "operation:POST:/payments"
    ]
    assert result.claim_proposals[1].value["operation_refs"] == [
        "operation:POST:/payments"
    ]


def test_unresolved_and_absent_citations_emit_diagnostics_without_references():
    unresolved = EndpointEntry(
        status=PlanItemStatus.SUPPORTED,
        citations=[
            SourceCitation(
                query_id="06-ep1",
                answer_path="answer.json",
                manifest_source="missing.md",
            )
        ],
        method="GET",
        path="/missing-citation",
        responses=[{"status": "200"}],
    )
    absent = SchemaEntry(
        status=PlanItemStatus.SUPPORTED,
        citations=[
            SourceCitation(
                query_id="07-initial",
                answer_path="answer.json",
                manifest_source=None,
            )
        ],
        name="Payload",
    )

    result = build_runtime_result(
        _plan(endpoints=[unresolved], schemas=[absent]), _bridge()
    )

    assert all(not proposal.evidence_refs for proposal in result.claim_proposals)
    assert any("missing.md" in message for message in result.diagnostics)
    assert any("has no manifest_source" in message for message in result.diagnostics)


def test_supported_entry_without_citations_emits_explicit_diagnostic():
    endpoint = EndpointEntry(
        status=PlanItemStatus.SUPPORTED,
        citations=[],
        method="GET",
        path="/uncited",
        responses=[{"status": "200"}],
    )

    result = build_runtime_result(_plan(endpoints=[endpoint]), _bridge())

    assert result.claim_proposals[0].evidence_refs == ()
    assert any("CITATION_MISSING" in item for item in result.diagnostics)
    assert any("endpoints[0]" in item for item in result.diagnostics)


def test_conflict_without_distinct_values_becomes_unverified_proposal():
    conflicting = EndpointEntry(
        status=PlanItemStatus.CONFLICTING,
        citations=[CITATION],
        method="GET",
        path="/conflict",
        responses=[{"status": "200"}],
    )

    result = build_runtime_result(_plan(endpoints=[conflicting]), _bridge())

    assert len(result.claim_proposals) == 1
    assert result.claim_proposals[0].value["path"] == "/conflict"
    assert result.claim_proposals[0].evidence_refs == ()
    assert any("does not preserve distinct values" in item for item in result.diagnostics)


def test_distinct_conflicting_values_for_same_identity_are_preserved():
    first = OperationalEntry(
        status=PlanItemStatus.CONFLICTING,
        citations=[CITATION],
        topic="rate limit",
        detail="10 requests/s",
    )
    second = OperationalEntry(
        status=PlanItemStatus.CONFLICTING,
        citations=[CITATION],
        topic="rate limit",
        detail="20 requests/s",
    )

    result = build_runtime_result(
        _plan(operational=[first, second]), _bridge()
    )

    assert len(result.claim_proposals) == 2
    assert {proposal.value["detail"] for proposal in result.claim_proposals} == {
        "10 requests/s",
        "20 requests/s",
    }


def test_duplicate_supported_identities_remain_distinct_stable_proposals():
    first = OperationalEntry(
        status=PlanItemStatus.SUPPORTED,
        citations=[CITATION],
        topic="rate limit",
        detail="10 requests/s",
    )
    second = first.model_copy()
    plan = _plan(operational=[first, second])

    first_result = build_runtime_result(plan, _bridge())
    second_result = build_runtime_result(plan, _bridge())

    assert len(first_result.claim_proposals) == 2
    assert first_result.claim_proposals[0].id != first_result.claim_proposals[1].id
    assert first_result == second_result


@pytest.mark.parametrize(
    "system_groups",
    [
        [],
        [SystemGroup(name="", version="1")],
    ],
)
def test_metadata_refuses_source_silent_title(system_groups):
    with pytest.raises(
        ShadowMetadataError,
        match="requires a source-stated title",
    ):
        build_contract_metadata(_plan(system_groups=system_groups), _bridge())


def test_metadata_uses_source_set_identity_and_source_stated_values():
    bridge = _bridge()

    metadata = build_contract_metadata(_plan(), bridge)

    assert metadata.contract_id == f"contract-{bridge.source_set_digest[:20]}"
    assert metadata.title == "Demo API"
    assert metadata.version == "2026-07"
    assert metadata.source_set_id == bridge.source_set.id
    assert metadata.source_set_version == bridge.source_set.version
