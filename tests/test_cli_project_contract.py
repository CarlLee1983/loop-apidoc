from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner
import yaml

from loop_apidoc.cli import app
from loop_apidoc.domain.evidence import (
    EvidenceBundle,
    EvidenceFragment,
    FragmentPrecision,
    LineRangeLocator,
    SourceArtifact,
    SourceDescriptor,
    SourceSet,
    SupportRelationshipType,
)
from loop_apidoc.domain.models import (
    AsyncApiDirection,
    AsyncApiTransportBinding,
    ContractMetadata,
    EvidenceBinding,
    GraphqlOperationKind,
    GraphqlTransportBinding,
    GroundedApiContract,
    Interaction,
    InteractionMode,
    Schema,
    SchemaField,
)
from loop_apidoc.domain.projections import ProjectionInput


RUNNER = CliRunner()
NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)


def _binding(fragment_id: str, claim_path: str) -> EvidenceBinding:
    return EvidenceBinding(
        fragment_id=fragment_id,
        relationship_id=f"relationship-{fragment_id}",
        claim_identity="interaction:graphql:query:viewer",
        claim_path=claim_path,
        relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
    )


def _graphql_projection_input() -> ProjectionInput:
    fragments = tuple(
        EvidenceFragment(
            id=f"fragment-{line}",
            source_artifact_id="artifact-github",
            locator=LineRangeLocator(start_line=line, end_line=line),
            fragment_digest=hashlib.sha256(value.encode()).hexdigest(),
            normalized_excerpt=value,
            semantic_value=value,
            semantic_role="field.value",
            precision=FragmentPrecision.EXACT,
        )
        for line, value in (
            (10, "query"),
            (11, "viewer"),
            (12, "User"),
            (13, "true"),
            (20, "login: String!"),
            (21, "name: String"),
        )
    )
    source_set = SourceSet(
        id="github-schema",
        version="2026-07-29",
        sources=(
            SourceDescriptor(
                id="github",
                kind="file",
                locator="schema.docs.graphql",
                media_type="application/graphql",
            ),
        ),
    )
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="github-graphql",
            title="GitHub GraphQL API",
            version="2026-07-29",
            source_set_id=source_set.id,
            source_set_version=source_set.version,
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
                    evidence=(
                        _binding("fragment-10", "/binding/operation_kind"),
                        _binding("fragment-11", "/binding/root_field"),
                        _binding("fragment-12", "/binding/output_schema_ref"),
                        _binding("fragment-13", "/binding/output_required"),
                    ),
                ),
                evidence=(_binding("fragment-11", "/binding/root_field"),),
            ),
        ),
        schemas=(
            Schema(
                name="User",
                fields=(
                    SchemaField(
                        name="login",
                        type="String",
                        required=True,
                        evidence=(
                            EvidenceBinding(
                                fragment_id="fragment-20",
                                relationship_id="relationship-fragment-20",
                                claim_identity="schema:User",
                                claim_path="/fields/login",
                                relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
                            ),
                        ),
                    ),
                    SchemaField(
                        name="name",
                        type="String",
                        required=False,
                        evidence=(
                            EvidenceBinding(
                                fragment_id="fragment-21",
                                relationship_id="relationship-fragment-21",
                                claim_identity="schema:User",
                                claim_path="/fields/name",
                                relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    return ProjectionInput(
        contract=contract,
        source_set=source_set,
        evidence=EvidenceBundle(
            source_set_id=source_set.id,
            source_set_version=source_set.version,
            artifacts=(
                SourceArtifact(
                    id="artifact-github",
                    source_id="github",
                    media_type="application/graphql",
                    content_digest="a" * 64,
                    acquired_at=NOW,
                ),
            ),
            fragments=fragments,
        ),
    )


def _write_input(path: Path, projection_input: ProjectionInput) -> None:
    path.write_text(projection_input.model_dump_json(indent=2), encoding="utf-8")


def _asyncapi_projection_input() -> ProjectionInput:
    values = (
        (30, "notify-collections"),
        (31, "collections"),
        (32, "subscribe"),
        (33, "collection_msg"),
        (34, "collection_msg"),
        (40, "id: string"),
        (41, "href: string"),
    )
    fragments = tuple(
        EvidenceFragment(
            id=f"fragment-{line}",
            source_artifact_id="artifact-ogc",
            locator=LineRangeLocator(start_line=line, end_line=line),
            fragment_digest=hashlib.sha256(value.encode()).hexdigest(),
            normalized_excerpt=value,
            semantic_value=value,
            semantic_role="field.value",
            precision=FragmentPrecision.EXACT,
        )
        for line, value in values
    )
    source_set = SourceSet(
        id="ogc-edr-asyncapi",
        version="88ed4ddee449",
        sources=(
            SourceDescriptor(
                id="ogc",
                kind="file",
                locator="asyncapi.yaml",
                media_type="application/yaml",
            ),
        ),
    )

    def binding(fragment_id: str, claim_path: str) -> EvidenceBinding:
        return EvidenceBinding(
            fragment_id=fragment_id,
            relationship_id=f"relationship-{fragment_id}",
            claim_identity="interaction:asyncapi:subscribe:notify-collections",
            claim_path=claim_path,
            relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
        )

    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="ogc-edr-pubsub",
            title="OGC API EDR Pub/Sub example",
            version="1.0.0",
            source_set_id=source_set.id,
            source_set_version=source_set.version,
            domain_version="2",
        ),
        interactions=(
            Interaction(
                identity="interaction:asyncapi:subscribe:notify-collections",
                mode=InteractionMode.SUBSCRIBE,
                binding=AsyncApiTransportBinding(
                    channel="notify-collections",
                    channel_address="collections",
                    direction=AsyncApiDirection.SUBSCRIBE,
                    message_name="collection_msg",
                    payload_schema_ref="collection_msg",
                    evidence=(
                        binding("fragment-30", "/binding/channel"),
                        binding("fragment-31", "/binding/channel_address"),
                        binding("fragment-32", "/binding/direction"),
                        binding("fragment-33", "/binding/message_name"),
                        binding("fragment-34", "/binding/payload_schema_ref"),
                    ),
                ),
                evidence=(binding("fragment-30", "/binding/channel"),),
            ),
        ),
        schemas=(
            Schema(
                name="collection_msg",
                fields=(
                    SchemaField(
                        name="id",
                        type="string",
                        required=True,
                        evidence=(
                            EvidenceBinding(
                                fragment_id="fragment-40",
                                relationship_id="relationship-fragment-40",
                                claim_identity="schema:collection_msg",
                                claim_path="/fields/id",
                                relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
                            ),
                        ),
                    ),
                    SchemaField(
                        name="href",
                        type="string",
                        required=True,
                        evidence=(
                            EvidenceBinding(
                                fragment_id="fragment-41",
                                relationship_id="relationship-fragment-41",
                                claim_identity="schema:collection_msg",
                                claim_path="/fields/href",
                                relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    return ProjectionInput(
        contract=contract,
        source_set=source_set,
        evidence=EvidenceBundle(
            source_set_id=source_set.id,
            source_set_version=source_set.version,
            artifacts=(
                SourceArtifact(
                    id="artifact-ogc",
                    source_id="ogc",
                    media_type="application/yaml",
                    content_digest="b" * 64,
                    acquired_at=NOW,
                ),
            ),
            fragments=fragments,
        ),
    )


def test_project_contract_graphql_writes_a_complete_validated_run(tmp_path: Path) -> None:
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "graphql-run"
    _write_input(input_path, _graphql_projection_input())

    result = RUNNER.invoke(
        app,
        [
            "project-contract",
            "--input",
            str(input_path),
            "--format",
            "graphql",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["format"] == "graphql"
    assert payload["status"] == "passed"
    assert payload["run_dir"] == str(output)
    assert (output / "schema.graphql").read_text(encoding="utf-8") == (
        "type Query {\n"
        "  viewer: User!\n"
        "}\n\n"
        "type User {\n"
        "  login: String!\n"
        "  name: String\n"
        "}\n"
    )
    assert (output / "graphql-guide.zh-TW.md").is_file()
    assert (output / "review.html").is_file()
    assert json.loads((output / "validation" / "report.json").read_text())["issues"] == []
    provenance = json.loads((output / "provenance.json").read_text())
    assert {entry["target"] for entry in provenance["entries"]} >= {
        "graphql:Query.viewer",
        "graphql:User.login",
        "graphql:User.name",
    }


def test_project_contract_asyncapi_writes_a_complete_validated_run(tmp_path: Path) -> None:
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "asyncapi-run"
    _write_input(input_path, _asyncapi_projection_input())

    result = RUNNER.invoke(
        app,
        [
            "project-contract",
            "--input",
            str(input_path),
            "--format",
            "asyncapi",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["format"] == "asyncapi"
    assert payload["status"] == "passed"
    document = yaml.safe_load((output / "asyncapi.yaml").read_text(encoding="utf-8"))
    assert document["asyncapi"] == "3.0.0"
    assert document["channels"]["notify-collections"]["address"] == "collections"
    assert document["operations"]["notify-collections"]["action"] == "receive"
    assert (output / "asyncapi-guide.zh-TW.md").is_file()
    assert (output / "review.html").is_file()
    assert json.loads((output / "validation" / "report.json").read_text())["issues"] == []
    provenance = json.loads((output / "provenance.json").read_text())
    assert {entry["target"] for entry in provenance["entries"]} >= {
        "asyncapi:notify-collections.receive.message.collection_msg",
        "asyncapi:notify-collections.receive.message.collection_msg.payload",
        "asyncapi:components.schemas.collection_msg.properties.id",
        "asyncapi:components.schemas.collection_msg.properties.href",
    }


def test_project_contract_asyncapi_rejects_an_unresolved_payload_schema(
    tmp_path: Path,
) -> None:
    projection_input = _asyncapi_projection_input()
    interaction = projection_input.contract.interactions[0]
    unresolved_binding = interaction.binding.model_copy(
        update={"payload_schema_ref": "MissingMessage"}
    )
    unresolved_contract = projection_input.contract.model_copy(
        update={
            "interactions": (
                interaction.model_copy(update={"binding": unresolved_binding}),
            )
        }
    )
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "asyncapi-run"
    _write_input(
        input_path,
        projection_input.model_copy(update={"contract": unresolved_contract}),
    )

    result = RUNNER.invoke(
        app,
        [
            "project-contract",
            "--input",
            str(input_path),
            "--format",
            "asyncapi",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2
    assert "cannot resolve payload schema 'MissingMessage'" in result.output
    assert not output.exists()


def test_project_contract_fails_validation_when_an_emitted_field_has_no_evidence(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    schema = projection_input.contract.schemas[0]
    unsupported_schema = schema.model_copy(
        update={
            "evidence": (),
            "fields": tuple(
                field.model_copy(update={"evidence": ()}) for field in schema.fields
            ),
        }
    )
    unsupported_contract = projection_input.contract.model_copy(
        update={"schemas": (unsupported_schema,)}
    )
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "graphql-run"
    _write_input(
        input_path,
        projection_input.model_copy(update={"contract": unsupported_contract}),
    )

    result = RUNNER.invoke(
        app,
        [
            "project-contract",
            "--input",
            str(input_path),
            "--format",
            "graphql",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    report = json.loads((output / "validation" / "report.json").read_text())
    assert {
        (issue["code"], issue["location"])
        for issue in report["issues"]
    } >= {
        ("SOURCE_UNVERIFIED", "schemas[0].fields.login"),
        ("SOURCE_UNVERIFIED", "schemas[0].fields.name"),
    }
    assert "SOURCE_UNVERIFIED" in (output / "review.html").read_text(encoding="utf-8")


def test_project_contract_graphql_reports_an_empty_object_type_as_invalid(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    empty_schema = projection_input.contract.schemas[0].model_copy(
        update={"fields": (), "evidence": ()}
    )
    empty_contract = projection_input.contract.model_copy(
        update={"schemas": (empty_schema,)}
    )
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "graphql-run"
    _write_input(
        input_path,
        projection_input.model_copy(update={"contract": empty_contract}),
    )

    result = RUNNER.invoke(
        app,
        [
            "project-contract",
            "--input",
            str(input_path),
            "--format",
            "graphql",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    assert ("OUTPUT_MISMATCH", "schema.graphql") in {
        (issue["code"], issue["location"]) for issue in report["issues"]
    }


def test_project_contract_fails_validation_for_a_tampered_exact_fragment_digest(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    first, *rest = projection_input.evidence.fragments
    tampered = first.model_copy(update={"fragment_digest": "c" * 64})
    tampered_evidence = projection_input.evidence.model_copy(
        update={"fragments": (tampered, *rest)}
    )
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "graphql-run"
    _write_input(
        input_path,
        projection_input.model_copy(update={"evidence": tampered_evidence}),
    )

    result = RUNNER.invoke(
        app,
        [
            "project-contract",
            "--input",
            str(input_path),
            "--format",
            "graphql",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    assert ("SOURCE_UNVERIFIED", "evidence.fragments.fragment-10") in {
        (issue["code"], issue["location"]) for issue in report["issues"]
    }


def test_project_contract_rejects_an_unknown_format_without_writing(tmp_path: Path) -> None:
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "run"
    _write_input(input_path, _graphql_projection_input())

    result = RUNNER.invoke(
        app,
        [
            "project-contract",
            "--input",
            str(input_path),
            "--format",
            "openapi",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2
    assert not output.exists()


def test_project_contract_refuses_to_overwrite_an_existing_run(tmp_path: Path) -> None:
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "run"
    output.mkdir()
    marker = output / "owned.txt"
    marker.write_text("keep", encoding="utf-8")
    _write_input(input_path, _graphql_projection_input())

    result = RUNNER.invoke(
        app,
        [
            "project-contract",
            "--input",
            str(input_path),
            "--format",
            "graphql",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 2
    assert "already exists" in result.output
    assert marker.read_text(encoding="utf-8") == "keep"
