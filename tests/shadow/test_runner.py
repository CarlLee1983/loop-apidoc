from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.core.models import LifecycleState
from loop_apidoc.domain.evidence import (
    JsonPointerLocator,
    SupportRelationshipType,
    canonical_json,
    fragment_digest,
)
from loop_apidoc.domain.models import ClaimStatus
from loop_apidoc.extraction.evidence import ExtractionEvidenceReference
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    ContractTestCase,
    CryptoScheme,
    EndpointEntry,
    FieldCondition,
    IntegrationContract,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SchemaEntry,
    SourceCitation,
    SystemGroup,
)
from loop_apidoc.run.models import RunStatus
from loop_apidoc.shadow.runner import execute_shadow
from loop_apidoc.source_facts.markdown import scan_markdown
from loop_apidoc.source_facts.models import FactIndex
from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)


NOW = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


def _manifest() -> Manifest:
    return Manifest(
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


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="",
        system_groups=[SystemGroup(name="Demo API", version="1")],
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED,
                citations=[
                    SourceCitation(
                        query_id="06-ep0",
                        answer_path="answer.json",
                        manifest_source="manual.md",
                    )
                ],
                method="GET",
                path="/ping",
                responses=[{"status": "200", "description": "OK"}],
            )
        ],
    )


def test_runner_executes_through_core_validation_without_approval_or_publication():
    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=_plan(),
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    assert artifacts.workflow.state is LifecycleState.APPROVAL_READY
    assert artifacts.artifact_publications == 0
    assert artifacts.approval_requests == 0
    assert artifacts.events[-1].kind == "lifecycle.approval_ready"
    assert artifacts.contract.operations == ()
    assert artifacts.claims[0].status is ClaimStatus.UNVERIFIED
    assert artifacts.decision.verdict.value == "accept"
    assert artifacts.comparison.verdict_match is True


def test_runner_executes_when_legacy_validation_failed():
    legacy_report = ValidationReport(
        issues=[
            Issue(
                code=IssueCode.REQUIRED_INFO_MISSING,
                severity=Severity.ERROR,
                location="paths./ping.get",
                evidence="source",
                suggested_fix="fill",
            )
        ]
    )

    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=_plan(),
        legacy_report=legacy_report,
        legacy_status=RunStatus.FAILED,
        generated_at=NOW,
    )

    assert artifacts.workflow.state is LifecycleState.APPROVAL_READY
    assert artifacts.comparison.legacy_status == "failed"
    assert artifacts.comparison.verdict_match is False


def test_runner_preserves_unknown_nested_and_integration_values():
    citation = _plan().endpoints[0].citations
    plan = _plan().model_copy(
        update={
            "endpoints": [
                EndpointEntry(
                    status=PlanItemStatus.SUPPORTED,
                    citations=citation,
                    method="GET",
                    path="/search",
                    parameters=[{"name": "q", "in": "query"}],
                    responses=[{"status": "200"}],
                )
            ],
            "schemas": [
                SchemaEntry(
                    status=PlanItemStatus.SUPPORTED,
                    citations=citation,
                    name="Result",
                    fields=[{"name": "value", "type": "string"}],
                )
            ],
            "integration": IntegrationContract(
                crypto=[
                    CryptoScheme(
                        status=PlanItemStatus.SUPPORTED,
                        citations=citation,
                        name="OpaqueMechanic",
                    )
                ],
                field_conditions=[
                    FieldCondition(
                        status=PlanItemStatus.SUPPORTED,
                        citations=citation,
                        scope="Result.value",
                    )
                ],
                test_cases=[
                    ContractTestCase(
                        status=PlanItemStatus.SUPPORTED,
                        citations=citation,
                        name="source example",
                    )
                ],
            ),
        }
    )

    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=plan,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    operation = next(
        proposal
        for proposal in artifacts.runtime_result.claim_proposals
        if proposal.claim_kind == "operation"
    )
    schema = next(
        proposal
        for proposal in artifacts.runtime_result.claim_proposals
        if proposal.claim_kind == "schema"
    )
    assert operation.value["parameters"][0].get("required") is None
    assert schema.value["fields"][0].get("required") is None
    assert all(
        proposal.value.get("kind") is None
        for proposal in artifacts.runtime_result.claim_proposals
        if proposal.claim_kind == "integration_mechanic"
    )


def test_runner_preserves_structured_citation_diagnostic_lineage():
    plan = _plan().model_copy(
        update={
            "endpoints": [
                EndpointEntry(
                    status=PlanItemStatus.SUPPORTED,
                    citations=[
                        SourceCitation(
                            query_id="06-ep9",
                            answer_path="answers/06-ep9.json",
                            manifest_source="missing.md",
                            locator="p.9",
                        )
                    ],
                    method="GET",
                    path="/unresolved",
                    responses=[{"status": "200"}],
                )
            ]
        }
    )

    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=plan,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    diagnostic = artifacts.comparison.diagnostics[0]
    assert diagnostic.code == "CITATION_UNRESOLVED"
    assert diagnostic.plan_location == "endpoints[0]"
    assert diagnostic.manifest_source == "missing.md"
    assert diagnostic.query_id == "06-ep9"
    assert diagnostic.answer_path == "answers/06-ep9.json"


def test_runner_keeps_single_value_conflict_as_unverified_claim():
    plan = _plan().model_copy(
        update={
            "endpoints": [
                EndpointEntry(
                    status=PlanItemStatus.CONFLICTING,
                    citations=_plan().endpoints[0].citations,
                    method="GET",
                    path="/conflict",
                    responses=[{"status": "200"}],
                )
            ]
        }
    )

    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=plan,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    assert len(artifacts.claims) == 1
    assert artifacts.claims[0].status.value == "unverified"


def _write_manifest(root: Path, text: str) -> tuple[Manifest, FactIndex]:
    source = root / "manual.md"
    source.write_text(text, encoding="utf-8")
    content = source.read_bytes()
    manifest = Manifest(
        sources_root=str(root),
        generated_at=NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                scanned_at=NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    return (
        manifest,
        FactIndex(sources=[scan_markdown("manual.md", text)]),
    )


def _table_plan(required: bool) -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="",
        system_groups=[SystemGroup(name="Demo API", version="1")],
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED,
                citations=[
                    SourceCitation(
                        query_id="06-ep0",
                        answer_path="answer.json",
                        manifest_source="manual.md",
                    )
                ],
                method="POST",
                path="/payments",
                parameters=[
                    {
                        "name": "amount",
                        "in": "query",
                        "required": required,
                    }
                ],
                responses=[{"status": "200", "description": "OK"}],
            )
        ],
    )


def test_filename_only_legacy_citation_is_not_supported(tmp_path):
    manifest, facts = _write_manifest(
        tmp_path,
        "# Payments\n\nThis document contains general API prose.\n",
    )

    artifacts = execute_shadow(
        manifest=manifest,
        plan=_table_plan(required=True),
        facts=facts,
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    assert artifacts.claims[0].status is ClaimStatus.UNVERIFIED
    assert any(
        item.code == "LEGACY_CITATION_DEGRADED"
        for item in artifacts.comparison.diagnostics
    )


def test_shadow_table_cell_supports_matching_parameter_field(tmp_path):
    manifest, facts = _write_manifest(
        tmp_path,
        """## POST /payments

| Name | Type | Required |
| --- | --- | --- |
| amount | integer | Y |
""",
    )

    artifacts = execute_shadow(
        manifest=manifest,
        plan=_table_plan(required=True),
        facts=facts,
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    claim = artifacts.claims[0]
    assert any(
        relationship.claim_path == "/parameters/query/amount/required"
        and relationship.relationship
        is SupportRelationshipType.EXPLICIT_SUPPORT
        for relationship in claim.support_relationships
    )


def test_shadow_table_cell_mismatch_is_conflicting(tmp_path):
    manifest, facts = _write_manifest(
        tmp_path,
        """## POST /payments

| Name | Type | Required |
| --- | --- | --- |
| amount | integer | Y |
""",
    )

    artifacts = execute_shadow(
        manifest=manifest,
        plan=_table_plan(required=False),
        facts=facts,
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    claim = artifacts.claims[0]
    assert claim.status is ClaimStatus.CONFLICTING
    assert any(
        relationship.relationship is SupportRelationshipType.CONTRADICTS
        for relationship in claim.support_relationships
    )


def test_precise_line_citation_supports_matching_claim_path(tmp_path):
    manifest, facts = _write_manifest(tmp_path, "10 requests/s\n")
    plan = NormalizationPlan(
        notebook_url="",
        system_groups=[SystemGroup(name="Demo API", version="1")],
        operational=[
            OperationalEntry(
                status=PlanItemStatus.SUPPORTED,
                citations=[
                    SourceCitation(
                        query_id="08-op0",
                        answer_path="answer.json",
                        manifest_source="manual.md",
                        locator="lines 1-1",
                    )
                ],
                topic="rate limit",
                detail="10 requests/s",
            )
        ],
    )

    artifacts = execute_shadow(
        manifest=manifest,
        plan=plan,
        facts=facts,
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    assert any(
        relationship.claim_path == "/detail"
        and relationship.relationship
        is SupportRelationshipType.EXPLICIT_SUPPORT
        for relationship in artifacts.claims[0].support_relationships
    )


def test_json_pointer_citation_supports_matching_scalar_path(tmp_path):
    source = tmp_path / "openapi.json"
    source.write_text('{"detail":"10 requests/s"}', encoding="utf-8")
    content = source.read_bytes()
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=NOW,
        local_sources=[
            LocalSource(
                relative_path="openapi.json",
                mime_type="application/json",
                source_format=SourceFormat.OPENAPI_JSON,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                scanned_at=NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    plan = NormalizationPlan(
        notebook_url="",
        system_groups=[SystemGroup(name="Demo API", version="1")],
        operational=[
            OperationalEntry(
                status=PlanItemStatus.SUPPORTED,
                citations=[
                    SourceCitation(
                        query_id="08-op0",
                        answer_path="answer.json",
                        manifest_source="openapi.json",
                        locator="openapi.json#/detail",
                    )
                ],
                topic="rate limit",
                detail="10 requests/s",
            )
        ],
    )

    artifacts = execute_shadow(
        manifest=manifest,
        plan=plan,
        facts=FactIndex(),
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    claim = artifacts.claims[0]
    assert claim.status is ClaimStatus.UNVERIFIED
    assert any(
        relationship.claim_path == "/detail"
        and relationship.relationship
        is SupportRelationshipType.EXPLICIT_SUPPORT
        for relationship in claim.support_relationships
    )
    assert not any(
        relationship.relationship is SupportRelationshipType.CONTRADICTS
        for relationship in claim.support_relationships
    )


def test_shadow_derives_operation_path_and_method_from_v1_openapi_evidence(tmp_path):
    operation = {"summary": "Create payment"}
    source = tmp_path / "openapi.json"
    source.write_text(
        json.dumps({"paths": {"/payments": {"post": operation}}}),
        encoding="utf-8",
    )
    content = source.read_bytes()
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=NOW,
        local_sources=[
            LocalSource(
                relative_path="openapi.json",
                mime_type="application/json",
                source_format=SourceFormat.OPENAPI_JSON,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                scanned_at=NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    locator = JsonPointerLocator(pointer="/paths/~1payments/post")
    evidence = tuple(
        ExtractionEvidenceReference(
            version=1,
            source="openapi.json",
            locator=locator,
            fragment_digest=fragment_digest(canonical_json(operation)),
            claim_path=claim_path,
        )
        for claim_path in ("/method", "/path")
    )
    plan = NormalizationPlan(
        notebook_url="",
        system_groups=[SystemGroup(name="Demo API", version="1")],
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED,
                citations=[
                    SourceCitation(
                        query_id="06-ep0",
                        answer_path="answer.json",
                        manifest_source="openapi.json",
                        evidence=evidence,
                    )
                ],
                method="POST",
                path="/payments",
            )
        ],
    )

    artifacts = execute_shadow(
        manifest=manifest,
        plan=plan,
        facts=FactIndex(),
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    claim = artifacts.claims[0]
    assert claim.status is ClaimStatus.SUPPORTED
    assert {
        relationship.claim_path
        for relationship in claim.support_relationships
        if relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    } == {"/method", "/path"}


def test_shadow_derives_response_status_from_v1_openapi_evidence(tmp_path):
    response = {"description": "Accepted"}
    operation = {"responses": {"202": response}}
    source = tmp_path / "openapi.json"
    source.write_text(
        json.dumps(
            {
                "paths": {
                    "/payments": {"post": operation},
                }
            }
        ),
        encoding="utf-8",
    )
    content = source.read_bytes()
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=NOW,
        local_sources=[
            LocalSource(
                relative_path="openapi.json",
                mime_type="application/json",
                source_format=SourceFormat.OPENAPI_JSON,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                scanned_at=NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    evidence = (
        *(
            ExtractionEvidenceReference(
                version=1,
                source="openapi.json",
                locator=JsonPointerLocator(pointer="/paths/~1payments/post"),
                fragment_digest=fragment_digest(canonical_json(operation)),
                claim_path=claim_path,
            )
            for claim_path in ("/method", "/path")
        ),
        ExtractionEvidenceReference(
            version=1,
            source="openapi.json",
            locator=JsonPointerLocator(
                pointer="/paths/~1payments/post/responses/202"
            ),
            fragment_digest=fragment_digest(canonical_json(response)),
            claim_path="/responses/202/status_code",
        ),
    )
    plan = NormalizationPlan(
        notebook_url="",
        system_groups=[SystemGroup(name="Demo API", version="1")],
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED,
                citations=[
                    SourceCitation(
                        query_id="06-ep0",
                        answer_path="answer.json",
                        manifest_source="openapi.json",
                        evidence=evidence,
                    )
                ],
                method="POST",
                path="/payments",
                responses=[{"status": "202"}],
            )
        ],
    )

    artifacts = execute_shadow(
        manifest=manifest,
        plan=plan,
        facts=FactIndex(),
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    relationship = next(
        item
        for item in artifacts.claims[0].support_relationships
        if item.claim_path == "/responses/202/status_code"
    )
    assert relationship.claim_path == "/responses/202/status_code"
    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "202"


def test_shadow_derives_response_schema_name_from_v1_openapi_evidence(tmp_path):
    schema_ref = "#/components/schemas/Payment"
    response = {
        "content": {"application/json": {"schema": {"$ref": schema_ref}}}
    }
    operation = {"responses": {"202": response}}
    source = tmp_path / "openapi.json"
    source.write_text(
        json.dumps({"paths": {"/payments": {"post": operation}}}),
        encoding="utf-8",
    )
    content = source.read_bytes()
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=NOW,
        local_sources=[
            LocalSource(
                relative_path="openapi.json",
                mime_type="application/json",
                source_format=SourceFormat.OPENAPI_JSON,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                scanned_at=NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    evidence = (
        *(
            ExtractionEvidenceReference(
                version=1,
                source="openapi.json",
                locator=JsonPointerLocator(pointer="/paths/~1payments/post"),
                fragment_digest=fragment_digest(canonical_json(operation)),
                claim_path=claim_path,
            )
            for claim_path in ("/method", "/path")
        ),
        ExtractionEvidenceReference(
            version=1,
            source="openapi.json",
            locator=JsonPointerLocator(
                pointer="/paths/~1payments/post/responses/202"
            ),
            fragment_digest=fragment_digest(canonical_json(response)),
            claim_path="/responses/202/status_code",
        ),
        ExtractionEvidenceReference(
            version=1,
            source="openapi.json",
            locator=JsonPointerLocator(
                pointer=(
                    "/paths/~1payments/post/responses/202/content/"
                    "application~1json/schema/$ref"
                )
            ),
            fragment_digest=fragment_digest(canonical_json(schema_ref)),
            claim_path="/responses/202/schema_ref",
        ),
    )
    plan = NormalizationPlan(
        notebook_url="",
        system_groups=[SystemGroup(name="Demo API", version="1")],
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED,
                citations=[
                    SourceCitation(
                        query_id="06-ep0",
                        answer_path="answer.json",
                        manifest_source="openapi.json",
                        evidence=evidence,
                    )
                ],
                method="POST",
                path="/payments",
                responses=[{"status": "202", "schema_ref": "Payment"}],
            )
        ],
    )

    artifacts = execute_shadow(
        manifest=manifest,
        plan=plan,
        facts=FactIndex(),
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    relationship = next(
        item
        for item in artifacts.claims[0].support_relationships
        if item.claim_path == "/responses/202/schema_ref"
    )
    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "Payment"


def test_shadow_derives_ref_linked_request_array_property_from_v1_evidence(
    tmp_path,
):
    """A request body field behind ``items.$ref`` retains both source links."""
    request_ref = "#/components/schemas/BatchRequest"
    item_ref = "#/components/schemas/Voucher"
    item_property = {"type": "string"}
    source_document = {
        "paths": {
            "/payments": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": request_ref}
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "BatchRequest": {
                    "properties": {
                        "data": {
                            "type": "array",
                            "items": {"$ref": item_ref},
                        }
                    }
                },
                "Voucher": {"properties": {"playerId": item_property}},
            }
        },
    }
    source = tmp_path / "openapi.json"
    source.write_text(json.dumps(source_document), encoding="utf-8")
    content = source.read_bytes()
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=NOW,
        local_sources=[
            LocalSource(
                relative_path="openapi.json",
                mime_type="application/json",
                source_format=SourceFormat.OPENAPI_JSON,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                scanned_at=NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    evidence = (
        ExtractionEvidenceReference(
            version=1,
            source="openapi.json",
            locator=JsonPointerLocator(
                pointer="/components/schemas/Voucher/properties/playerId"
            ),
            fragment_digest=fragment_digest(canonical_json(item_property)),
            claim_path="/parameters/body/data[].playerId/name",
        ),
        ExtractionEvidenceReference(
            version=1,
            source="openapi.json",
            locator=JsonPointerLocator(
                pointer=(
                    "/components/schemas/BatchRequest/properties/data/items/$ref"
                )
            ),
            fragment_digest=fragment_digest(canonical_json(item_ref)),
            claim_path="/parameters/body/data[].playerId/name",
        ),
    )
    plan = NormalizationPlan(
        notebook_url="",
        system_groups=[SystemGroup(name="Demo API", version="1")],
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED,
                citations=[
                    SourceCitation(
                        query_id="06-ep0",
                        answer_path="answer.json",
                        manifest_source="openapi.json",
                        evidence=evidence,
                    )
                ],
                method="POST",
                path="/payments",
                request={"schema_ref": "BatchRequest"},
                parameters=[
                    {
                        "name": "data[].playerId",
                        "in": "body",
                        "required": True,
                    }
                ],
            )
        ],
    )

    artifacts = execute_shadow(
        manifest=manifest,
        plan=plan,
        facts=FactIndex(),
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    relationship = next(
        item
        for item in artifacts.claims[0].support_relationships
        if item.claim_path == "/parameters/body/data[].playerId/name"
        and item.relationship is SupportRelationshipType.DERIVED_SUPPORT
    )
    assert relationship.observed_value == "data[].playerId"
    assert len(relationship.context_fragment_ids) == 1


def test_shadow_derives_nested_inline_schema_field_claims_from_v1_evidence(
    tmp_path,
):
    """A nested inline property pointer proves its schema field claims."""
    property_pointer = (
        "/components/schemas/Batch/properties/data/items/properties/playerId"
    )
    source_property = {"type": "string"}
    source_document = {
        "components": {
            "schemas": {
                "Batch": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"playerId": source_property},
                            },
                        }
                    },
                }
            }
        }
    }
    source = tmp_path / "openapi.json"
    source.write_text(json.dumps(source_document), encoding="utf-8")
    content = source.read_bytes()
    manifest = Manifest(
        sources_root=str(tmp_path),
        generated_at=NOW,
        local_sources=[
            LocalSource(
                relative_path="openapi.json",
                mime_type="application/json",
                source_format=SourceFormat.OPENAPI_JSON,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                scanned_at=NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )
    evidence = tuple(
        ExtractionEvidenceReference(
            version=1,
            source="openapi.json",
            locator=JsonPointerLocator(pointer=property_pointer),
            fragment_digest=fragment_digest(canonical_json(source_property)),
            claim_path=claim_path,
        )
        for claim_path in (
            "/fields/data[].playerId/name",
            "/fields/data[].playerId/type",
        )
    )
    plan = NormalizationPlan(
        notebook_url="",
        system_groups=[SystemGroup(name="Demo API", version="1")],
        schemas=[
            SchemaEntry(
                status=PlanItemStatus.SUPPORTED,
                citations=[
                    SourceCitation(
                        query_id="05-schema0",
                        answer_path="inventory.json",
                        manifest_source="openapi.json",
                        evidence=evidence,
                    )
                ],
                name="Batch",
                fields=[{"name": "data[].playerId", "type": "string"}],
            )
        ],
    )

    artifacts = execute_shadow(
        manifest=manifest,
        plan=plan,
        facts=FactIndex(),
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    relationships = {
        relationship.claim_path: relationship
        for relationship in artifacts.claims[0].support_relationships
        if relationship.claim_path
        in {"/fields/data[].playerId/name", "/fields/data[].playerId/type"}
    }
    assert relationships["/fields/data[].playerId/name"].relationship is (
        SupportRelationshipType.DERIVED_SUPPORT
    )
    assert relationships["/fields/data[].playerId/name"].observed_value == (
        "data[].playerId"
    )
    assert relationships["/fields/data[].playerId/type"].relationship is (
        SupportRelationshipType.DERIVED_SUPPORT
    )
    assert relationships["/fields/data[].playerId/type"].observed_value == "string"
