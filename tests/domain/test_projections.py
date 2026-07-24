from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import yaml

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
    AsyncApiDirection,
    AsyncApiTransportBinding,
    Environment,
    EvidenceBinding,
    GraphqlOperationKind,
    GraphqlTransportBinding,
    GroundedApiContract,
    HttpTransportBinding,
    Interaction,
    InteractionMode,
    Operation,
    Parameter,
    Response,
    Schema,
    SchemaField,
)
from loop_apidoc.domain.projections import (
    AsyncApiProjectionCompiler,
    OpenApiProjectionCompiler,
    GraphqlProjectionCompiler,
    ProjectionInput,
    ProvenanceProjectionCompiler,
    ReviewProjectionCompiler,
    UnsupportedProjectionError,
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


def test_openapi_projection_compiles_a_http_interaction_through_the_protocol_seam():
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="health-v2",
            title="Health API",
            version="2026-07",
            source_set_id="sources",
            source_set_version="1",
            domain_version="2",
        ),
        interactions=(
            Interaction(
                identity="interaction:http:GET:/health",
                mode=InteractionMode.REQUEST_REPLY,
                binding=HttpTransportBinding(
                    method="GET",
                    path="/health",
                    responses=(Response(status_code="200", description="OK"),),
                ),
            ),
        ),
    )

    payload = json.loads(OpenApiProjectionCompiler(version="1").compile(contract).content)

    assert payload["paths"] == {
        "/health": {"get": {"responses": {"200": {"description": "OK"}}}}
    }


def test_openapi_projection_rejects_a_graphql_interaction_without_inventing_http():
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="catalog",
            title="Catalog API",
            version="2026-07",
            source_set_id="sources",
            source_set_version="1",
            domain_version="2",
        ),
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

    with pytest.raises(UnsupportedProjectionError, match="graphql"):
        OpenApiProjectionCompiler(version="1").compile(contract)


def test_graphql_projection_compiles_the_source_backed_viewer_query_as_sdl():
    # GitHub public-schema snapshot: Query.viewer at lines 47721-47723;
    # User.login at 71427-71430 and User.name at 71437-71440.
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="github-graphql",
            title="GitHub GraphQL API",
            version=None,
            source_set_id="github-schema",
            source_set_version="2026-07-24",
            domain_version="2",
        ),
        interactions=(
            Interaction(
                identity="interaction:graphql:query:viewer",
                mode=InteractionMode.REQUEST_REPLY,
                binding=GraphqlTransportBinding(
                    operation_kind=GraphqlOperationKind.QUERY,
                    root_field="viewer",
                    output_schema_ref="User",
                    output_required=True,
                ),
            ),
        ),
        schemas=(
            Schema(
                name="User",
                fields=(
                    SchemaField(name="login", type="String", required=True),
                    SchemaField(name="name", type="String", required=False),
                ),
            ),
        ),
    )

    projection = GraphqlProjectionCompiler(version="1").compile(contract)

    assert projection.name == "graphql"
    assert projection.media_type == "application/graphql"
    assert projection.content.decode() == (
        "type Query {\n"
        "  viewer: User!\n"
        "}\n\n"
        "type User {\n"
        "  login: String!\n"
        "  name: String\n"
        "}\n"
    )


def test_graphql_interaction_evidence_traces_to_its_sdl_target():
    binding = EvidenceBinding(
        fragment_id="fragment-viewer",
        relationship_id="relationship-viewer",
        claim_identity="interaction:graphql:query:viewer",
        claim_path="/binding/root_field",
        relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
    )
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="github-graphql",
            title="GitHub GraphQL API",
            version=None,
            source_set_id="github-schema",
            source_set_version="2026-07-24",
            domain_version="2",
        ),
        interactions=(
            Interaction(
                identity="interaction:graphql:query:viewer",
                mode=InteractionMode.REQUEST_REPLY,
                binding=GraphqlTransportBinding(
                    operation_kind=GraphqlOperationKind.QUERY,
                    root_field="viewer",
                    output_schema_ref="User",
                    output_required=True,
                    evidence=(binding,),
                ),
                evidence=(binding,),
            ),
        ),
    )
    source_set = SourceSet(
        id="github-schema",
        version="2026-07-24",
        sources=(
            SourceDescriptor(
                id="github-public-schema",
                kind="url",
                locator="https://docs.github.com/public/fpt/schema.docs.graphql",
                media_type="application/graphql",
            ),
        ),
    )
    evidence = EvidenceBundle(
        source_set_id="github-schema",
        source_set_version="2026-07-24",
        artifacts=(
            SourceArtifact(
                id="artifact-github-schema",
                source_id="github-public-schema",
                media_type="application/graphql",
                content_digest=(
                    "f7a98392e2281c215810c5ac648c3a6940bcd49db74beb2502143f244fdb4da3"
                ),
                acquired_at=NOW,
            ),
        ),
        fragments=(
            EvidenceFragment(
                id="fragment-viewer",
                source_artifact_id="artifact-github-schema",
                locator=LineRangeLocator(start_line=47721, end_line=47723),
                fragment_digest=fragment_digest(
                    'The currently authenticated user.\n"""\nviewer: User!'
                ),
                normalized_excerpt='The currently authenticated user.\n"""\nviewer: User!',
                precision=FragmentPrecision.EXACT,
            ),
        ),
    )

    payload = json.loads(
        ProvenanceProjectionCompiler(version="1")
        .compile(ProjectionInput(contract=contract, source_set=source_set, evidence=evidence))
        .content
    )

    assert payload["entries"][0]["target"] == "graphql:Query.viewer"
    assert payload["entries"][0]["fragment_locator"] == {
        "kind": "line_range",
        "start_line": 47721,
        "end_line": 47723,
    }


def test_graphql_projection_rejects_an_unresolved_output_schema_reference():
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="catalog",
            title="Catalog API",
            version="1",
            source_set_id="sources",
            source_set_version="1",
            domain_version="2",
        ),
        interactions=(
            Interaction(
                identity="interaction:graphql:query:product",
                mode=InteractionMode.REQUEST_REPLY,
                binding=GraphqlTransportBinding(
                    operation_kind=GraphqlOperationKind.QUERY,
                    root_field="product",
                    output_schema_ref="Product",
                ),
            ),
        ),
    )

    with pytest.raises(UnsupportedProjectionError, match="Product"):
        GraphqlProjectionCompiler(version="1").compile(contract)


def test_asyncapi_projection_compiles_the_source_backed_collection_notification():
    # OGC pinned AsyncAPI snapshot: channel/message at lines 24-31,
    # receive operation at lines 61-65, and collection_msg fields at lines 83-101.
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="ogc-edr-pubsub",
            title="OGC API EDR Pub/Sub example",
            version="1.0.0",
            source_set_id="ogc-edr-asyncapi",
            source_set_version="88ed4ddee449db2ea60359a61eb3a1dff6a46c24",
            domain_version="2",
        ),
        interactions=(
            Interaction(
                identity="interaction:asyncapi:receive:notify-collections",
                mode=InteractionMode.SUBSCRIBE,
                binding=AsyncApiTransportBinding(
                    channel="notify-collections",
                    channel_address="collections",
                    direction=AsyncApiDirection.SUBSCRIBE,
                    message_name="collection_msg",
                    payload_schema_ref="collection_msg",
                ),
            ),
        ),
        schemas=(
            Schema(
                name="collection_msg",
                fields=(
                    SchemaField(name="id", type="string", required=True),
                    SchemaField(name="href", type="string", required=True),
                    SchemaField(name="time", type="string", required=False),
                ),
            ),
        ),
    )

    projection = AsyncApiProjectionCompiler(version="1").compile(contract)

    assert projection.name == "asyncapi"
    assert projection.media_type == "application/yaml"
    payload = yaml.safe_load(projection.content)
    assert payload["asyncapi"] == "3.0.0"
    assert payload["channels"]["notify-collections"] == {
        "address": "collections",
        "messages": {
            "collection_msg": {
                "payload": {"$ref": "#/components/schemas/collection_msg"}
            }
        },
    }
    assert payload["operations"]["notify-collections"] == {
        "action": "receive",
        "channel": {"$ref": "#/channels/notify-collections"},
    }
    assert payload["components"]["schemas"]["collection_msg"]["required"] == [
        "id",
        "href",
    ]


def test_asyncapi_payload_evidence_traces_to_its_message_payload_target():
    binding = EvidenceBinding(
        fragment_id="fragment-collection-payload",
        relationship_id="relationship-collection-payload",
        claim_identity="interaction:asyncapi:receive:notify-collections",
        claim_path="/binding/payload_schema_ref",
        relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
    )
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="ogc-edr-pubsub",
            title="OGC API EDR Pub/Sub example",
            version="1.0.0",
            source_set_id="ogc-edr-asyncapi",
            source_set_version="88ed4ddee449db2ea60359a61eb3a1dff6a46c24",
            domain_version="2",
        ),
        interactions=(
            Interaction(
                identity="interaction:asyncapi:receive:notify-collections",
                mode=InteractionMode.SUBSCRIBE,
                binding=AsyncApiTransportBinding(
                    channel="notify-collections",
                    channel_address="collections",
                    direction=AsyncApiDirection.SUBSCRIBE,
                    message_name="collection_msg",
                    payload_schema_ref="collection_msg",
                    evidence=(binding,),
                ),
            ),
        ),
    )
    source_set = SourceSet(
        id="ogc-edr-asyncapi",
        version="88ed4ddee449db2ea60359a61eb3a1dff6a46c24",
        sources=(
            SourceDescriptor(
                id="ogc-edr-example",
                kind="url",
                locator=(
                    "https://raw.githubusercontent.com/opengeospatial/"
                    "ogcapi-environmental-data-retrieval/88ed4ddee449db2ea60359a61eb3a1dff6a46c24/"
                    "extensions/pubsub/standard/examples/yaml/asyncapi.yaml"
                ),
                media_type="application/yaml",
            ),
        ),
    )
    evidence = EvidenceBundle(
        source_set_id="ogc-edr-asyncapi",
        source_set_version="88ed4ddee449db2ea60359a61eb3a1dff6a46c24",
        artifacts=(
            SourceArtifact(
                id="artifact-ogc-edr-example",
                source_id="ogc-edr-example",
                media_type="application/yaml",
                content_digest=(
                    "f9752316b74e39865f5e98419c8b5996d084be2e963fa127486dfccf038f4536"
                ),
                acquired_at=NOW,
            ),
        ),
        fragments=(
            EvidenceFragment(
                id="fragment-collection-payload",
                source_artifact_id="artifact-ogc-edr-example",
                locator=LineRangeLocator(start_line=24, end_line=31),
                fragment_digest=fragment_digest("notify-collections payload"),
                normalized_excerpt="notify-collections payload",
                precision=FragmentPrecision.EXACT,
            ),
        ),
    )

    payload = json.loads(
        ProvenanceProjectionCompiler(version="1")
        .compile(ProjectionInput(contract=contract, source_set=source_set, evidence=evidence))
        .content
    )

    assert payload["entries"][0]["target"] == (
        "asyncapi:notify-collections.receive.message.collection_msg.payload"
    )


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
