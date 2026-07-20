from __future__ import annotations

import json
from datetime import datetime, timezone

from loop_apidoc.domain.evidence import (
    EvidenceBundle,
    EvidenceFragment,
    FragmentPrecision,
    LineRangeLocator,
    SourceArtifact,
    SourceDescriptor,
    SourceSet,
    SupportRelationshipType,
    TableCellLocator,
    fragment_digest,
)
from loop_apidoc.domain.models import (
    ContractMetadata,
    Environment,
    EvidenceBinding,
    GroundedApiContract,
    Operation,
    Parameter,
    Response,
)
from loop_apidoc.domain.projections import (
    OpenApiProjectionCompiler,
    ProjectionInput,
    ProvenanceProjectionCompiler,
    ReviewProjectionCompiler,
)

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def _contract() -> GroundedApiContract:
    return GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="contract-1",
            title="Health API",
            version="2026-07",
            source_set_id="sources",
            source_set_version="1",
            domain_version="1",
        ),
        environments=(
            Environment(name="production", servers=("https://api.example.com",)),
        ),
        operations=(
            Operation(
                method="GET",
                path="/health",
                responses=(Response(status_code="200", description="OK"),),
                evidence=(EvidenceBinding(fragment_id="fragment-1"),),
            ),
        ),
    )


def test_openapi_projection_is_reproducible():
    compiler = OpenApiProjectionCompiler(version="1")

    first = compiler.compile(_contract())
    second = compiler.compile(_contract())

    assert first == second
    assert first.media_type == "application/vnd.oai.openapi+json;version=3.1"
    payload = json.loads(first.content)
    assert payload["paths"]["/health"]["get"]["responses"]["200"]["description"] == "OK"


def test_review_projection_preserves_contract_states():
    projection = ReviewProjectionCompiler(version="1").compile(_contract())

    assert projection.name == "review-data"
    assert json.loads(projection.content)["metadata"]["contract_id"] == "contract-1"


def _projection_input_with_split_operation_evidence() -> ProjectionInput:
    identity = "claim:operation:POST /payments:definition"
    summary_binding = EvidenceBinding(
        fragment_id="fragment-summary",
        relationship_id="relationship-summary",
        claim_identity=identity,
        claim_path="/summary",
        relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
    )
    required_binding = EvidenceBinding(
        fragment_id="fragment-required",
        relationship_id="relationship-required",
        claim_identity=identity,
        claim_path="/parameters/query/amount/required",
        relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
    )
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="payments",
            title="Payments",
            version="1",
            source_set_id="sources",
            source_set_version="1",
            domain_version="2",
        ),
        operations=(
            Operation(
                method="POST",
                path="/payments",
                summary="Create payment",
                parameters=(
                    Parameter(
                        name="amount",
                        location="query",
                        required=True,
                        evidence=(required_binding,),
                    ),
                ),
                responses=(Response(status_code="200", description="OK"),),
                evidence=(summary_binding, required_binding),
            ),
        ),
    )
    source_set = SourceSet(
        id="sources",
        version="1",
        sources=(
            SourceDescriptor(
                id="source-summary",
                kind="file",
                locator="summary.md",
                media_type="text/markdown",
            ),
            SourceDescriptor(
                id="source-required",
                kind="file",
                locator="fields.md",
                media_type="text/markdown",
            ),
        ),
    )
    evidence = EvidenceBundle(
        source_set_id="sources",
        source_set_version="1",
        artifacts=(
            SourceArtifact(
                id="artifact-summary",
                source_id="source-summary",
                media_type="text/markdown",
                content_digest="a" * 64,
                acquired_at=NOW,
            ),
            SourceArtifact(
                id="artifact-required",
                source_id="source-required",
                media_type="text/markdown",
                content_digest="b" * 64,
                acquired_at=NOW,
            ),
        ),
        fragments=(
            EvidenceFragment(
                id="fragment-summary",
                source_artifact_id="artifact-summary",
                locator=LineRangeLocator(start_line=4, end_line=4),
                fragment_digest=fragment_digest("Create payment"),
                normalized_excerpt="Create payment",
                precision=FragmentPrecision.EXACT,
            ),
            EvidenceFragment(
                id="fragment-required",
                source_artifact_id="artifact-required",
                locator=TableCellLocator(
                    table_index=0,
                    row_index=0,
                    column_index=2,
                    row_key="amount",
                    column_name="Required",
                ),
                fragment_digest=fragment_digest("Y"),
                normalized_excerpt="Y",
                semantic_value=True,
                semantic_role="parameter.required",
                precision=FragmentPrecision.EXACT,
            ),
        ),
    )
    return ProjectionInput(
        contract=contract,
        source_set=source_set,
        evidence=evidence,
    )


def test_operation_fields_trace_to_different_exact_fragments():
    projection = ProvenanceProjectionCompiler(version="1").compile(
        _projection_input_with_split_operation_evidence()
    )

    payload = json.loads(projection.content)
    by_target = {entry["target"]: entry for entry in payload["entries"]}
    assert (
        by_target["paths./payments.post.summary"]["fragment_id"]
        == "fragment-summary"
    )
    assert (
        by_target[
            "paths./payments.post.parameters.query.amount.required"
        ]["fragment_id"]
        == "fragment-required"
    )
    assert by_target["paths./payments.post.summary"][
        "source_artifact_id"
    ] != by_target[
        "paths./payments.post.parameters.query.amount.required"
    ][
        "source_artifact_id"
    ]


def test_openapi_claim_map_joins_field_target_to_claim_path():
    payload = json.loads(
        OpenApiProjectionCompiler(version="2")
        .compile(_projection_input_with_split_operation_evidence())
        .content
    )

    operation = payload["paths"]["/payments"]["post"]
    assert operation["x-loop-claim-map"]["/summary"]["claim_path"] == "/summary"
    assert operation["parameters"][0]["required"] is True


def test_review_projection_contains_relationship_and_exact_locator():
    payload = json.loads(
        ReviewProjectionCompiler(version="2")
        .compile(_projection_input_with_split_operation_evidence())
        .content
    )

    assert payload["relationships"][0]["fragment_locator"]["kind"] != (
        "whole_document"
    )
