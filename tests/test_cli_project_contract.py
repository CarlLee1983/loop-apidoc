from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result
import yaml

from loop_apidoc.cli import app
from loop_apidoc.protocol_run import ContractFormat, project_contract
from loop_apidoc.domain.evidence import (
    EvidenceBundle,
    EvidenceFragment,
    FragmentPrecision,
    FragmentReconstructionRef,
    LineRangeLocator,
    SourceArtifact,
    SourceDescriptor,
    SourceSet,
    SupportRelationshipType,
)
from loop_apidoc.domain.models import (
    AsyncApiDirection,
    AsyncApiTransportBinding,
    ClaimStatus,
    ContractClaim,
    ContractMetadata,
    EvidenceBinding,
    GraphqlOperationKind,
    GraphqlTransportBinding,
    GroundedApiContract,
    Interaction,
    InteractionMode,
    Operation,
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


def test_project_contract_fails_when_an_emitted_value_contradicts_its_exact_evidence(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    interaction = projection_input.contract.interactions[0]
    # fragment-11 states the root field is `viewer`; the contract now claims a
    # different field while still citing that fragment as explicit support.
    contradicted = interaction.model_copy(
        update={
            "binding": interaction.binding.model_copy(
                update={"root_field": "deleteEverything"}
            )
        }
    )
    contract = projection_input.contract.model_copy(
        update={"interactions": (contradicted,)}
    )
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "graphql-run"
    _write_input(input_path, projection_input.model_copy(update={"contract": contract}))

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
    assert json.loads(result.stdout)["status"] == "failed"
    report = json.loads((output / "validation" / "report.json").read_text())
    mismatches = [
        issue
        for issue in report["issues"]
        if issue["location"] == "interactions[0]/binding/root_field"
    ]
    assert [issue["code"] for issue in mismatches] == ["SOURCE_UNVERIFIED"]
    assert "deleteEverything" in mismatches[0]["evidence"]
    assert "viewer" in mismatches[0]["evidence"]


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


def test_project_contract_reports_an_empty_asyncapi_payload_schema_as_invalid(
    tmp_path: Path,
) -> None:
    projection_input = _asyncapi_projection_input()
    hollow = projection_input.contract.schemas[0].model_copy(update={"fields": ()})
    contract = projection_input.contract.model_copy(update={"schemas": (hollow,)})
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "asyncapi-run"
    _write_input(input_path, projection_input.model_copy(update={"contract": contract}))

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

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    assert ("OUTPUT_MISMATCH", "asyncapi.yaml") in {
        (issue["code"], issue["location"]) for issue in report["issues"]
    }


def test_project_contract_marks_an_asyncapi_version_the_source_never_stated(
    tmp_path: Path,
) -> None:
    projection_input = _asyncapi_projection_input()
    contract = projection_input.contract.model_copy(
        update={
            "metadata": projection_input.contract.metadata.model_copy(
                update={"version": None}
            )
        }
    )
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "asyncapi-run"
    _write_input(input_path, projection_input.model_copy(update={"contract": contract}))

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
    info = yaml.safe_load((output / "asyncapi.yaml").read_text(encoding="utf-8"))["info"]
    # A required-by-format placeholder must be distinguishable from a version
    # the source actually stated as 0.0.0.
    assert info["x-loop-status"] == "missing-source"


def test_project_contract_rejects_two_interactions_on_one_graphql_root_field(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    interaction = projection_input.contract.interactions[0]
    # Emitting both would produce a duplicated field in `type Query`, which is
    # not valid SDL.
    contract = projection_input.contract.model_copy(
        update={"interactions": (interaction, interaction)}
    )
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "graphql-run"
    _write_input(input_path, projection_input.model_copy(update={"contract": contract}))

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
    assert "viewer" in result.output
    assert not output.exists()


def test_project_contract_rejects_two_interactions_on_one_asyncapi_channel(
    tmp_path: Path,
) -> None:
    projection_input = _asyncapi_projection_input()
    interaction = projection_input.contract.interactions[0]
    # A send and a receive slice on one channel is the ordinary AsyncAPI shape;
    # the single-entry channel/operation maps would silently drop one of them.
    opposite = interaction.model_copy(
        update={
            "binding": interaction.binding.model_copy(
                update={
                    "direction": AsyncApiDirection.PUBLISH,
                    "message_name": "collection_ack",
                }
            )
        }
    )
    contract = projection_input.contract.model_copy(
        update={"interactions": (interaction, opposite)}
    )
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "asyncapi-run"
    _write_input(input_path, projection_input.model_copy(update={"contract": contract}))

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
    assert "notify-collections" in result.output
    assert not output.exists()


def _run_graphql(tmp_path: Path, projection_input: ProjectionInput) -> tuple[Result, Path]:
    input_path = tmp_path / "projection-input.json"
    output = tmp_path / "run"
    _write_input(input_path, projection_input)
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
    return result, output


def test_project_contract_rejects_a_transport_the_selected_format_cannot_carry(
    tmp_path: Path,
) -> None:
    # AsyncAPI interactions cannot be projected as GraphQL.
    result, output = _run_graphql(tmp_path, _asyncapi_projection_input())

    assert result.exit_code == 2
    assert "asyncapi" in result.output
    assert not output.exists()


def test_project_contract_rejects_legacy_http_operations(tmp_path: Path) -> None:
    projection_input = _graphql_projection_input()
    contract = projection_input.contract.model_copy(
        update={"operations": (Operation(method="GET", path="/viewer"),)}
    )
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"contract": contract})
    )

    assert result.exit_code == 2
    assert "operations" in result.output
    assert not output.exists()


def test_project_contract_rejects_a_contract_without_interactions(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    contract = projection_input.contract.model_copy(update={"interactions": ()})
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"contract": contract})
    )

    assert result.exit_code == 2
    assert "no interactions" in result.output
    assert not output.exists()


def test_project_contract_rejects_an_unreadable_projection_input(tmp_path: Path) -> None:
    input_path = tmp_path / "projection-input.json"
    input_path.write_text("{not json", encoding="utf-8")
    output = tmp_path / "run"

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
    assert not output.exists()


def test_project_contract_rejects_an_input_missing_its_evidence_bundle(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"evidence": None})
    )

    assert result.exit_code == 2
    assert "requires contract, source_set, and evidence" in result.output
    assert not output.exists()


def test_project_contract_fails_when_the_source_set_identity_disagrees(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    metadata = projection_input.contract.metadata.model_copy(
        update={"source_set_version": "1999-01-01"}
    )
    contract = projection_input.contract.model_copy(update={"metadata": metadata})
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"contract": contract})
    )

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    assert ("SOURCE_UNVERIFIED", "projection-input.source_set") in {
        (issue["code"], issue["location"]) for issue in report["issues"]
    }


def test_project_contract_fails_when_an_artifact_names_an_unknown_source(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    artifact, *rest = projection_input.evidence.artifacts
    evidence = projection_input.evidence.model_copy(
        update={
            "artifacts": (artifact.model_copy(update={"source_id": "ghost"}), *rest)
        }
    )
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"evidence": evidence})
    )

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    assert ("SOURCE_UNVERIFIED", f"evidence.artifacts.{artifact.id}") in {
        (issue["code"], issue["location"]) for issue in report["issues"]
    }


def test_project_contract_fails_when_a_fragment_names_an_unknown_artifact(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    first, *rest = projection_input.evidence.fragments
    orphan = first.model_copy(update={"source_artifact_id": "ghost-artifact"})
    evidence = projection_input.evidence.model_copy(
        update={"fragments": (orphan, *rest)}
    )
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"evidence": evidence})
    )

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    assert ("SOURCE_UNVERIFIED", f"evidence.fragments.{first.id}") in {
        (issue["code"], issue["location"]) for issue in report["issues"]
    }


def test_project_contract_fails_when_an_exact_fragment_embeds_no_excerpt(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    first, *rest = projection_input.evidence.fragments
    # The domain model accepts an exact fragment that can be reconstructed from
    # its artifact, but a standalone protocol run has no artifact to read.
    bare = first.model_copy(
        update={
            "normalized_excerpt": None,
            "reconstruction_ref": FragmentReconstructionRef(
                source_artifact_id=first.source_artifact_id,
                locator=first.locator,
            ),
        }
    )
    evidence = projection_input.evidence.model_copy(update={"fragments": (bare, *rest)})
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"evidence": evidence})
    )

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    assert ("SOURCE_UNVERIFIED", f"evidence.fragments.{first.id}") in {
        (issue["code"], issue["location"]) for issue in report["issues"]
    }


def test_project_contract_fails_when_a_binding_cites_an_absent_fragment(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    interaction = projection_input.contract.interactions[0]
    dangling = interaction.model_copy(
        update={
            "evidence": tuple(
                reference.model_copy(update={"fragment_id": "fragment-missing"})
                for reference in interaction.evidence
            )
        }
    )
    contract = projection_input.contract.model_copy(
        update={"interactions": (dangling,)}
    )
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"contract": contract})
    )

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    assert any(
        "fragment-missing" in issue["evidence"] for issue in report["issues"]
    )


def test_project_contract_fails_when_a_binding_claims_an_unsupported_relationship(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    interaction = projection_input.contract.interactions[0]
    binding = interaction.binding
    weakened = interaction.model_copy(
        update={
            "binding": binding.model_copy(
                update={
                    "evidence": tuple(
                        reference.model_copy(
                            update={
                                "relationship": SupportRelationshipType.INSUFFICIENT
                            }
                        )
                        for reference in binding.evidence
                    )
                }
            )
        }
    )
    contract = projection_input.contract.model_copy(
        update={"interactions": (weakened,)}
    )
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"contract": contract})
    )

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    locations = {issue["location"] for issue in report["issues"]}
    # The interaction-level coverage gate must also report the now-unsupported
    # emitted values, not merely the malformed relationship.
    assert "interactions[0]/binding/operation_kind" in locations


def test_project_contract_fails_when_a_claim_path_does_not_resolve(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    interaction = projection_input.contract.interactions[0]
    misrouted = interaction.model_copy(
        update={
            "evidence": tuple(
                reference.model_copy(update={"claim_path": "/binding/no_such_field"})
                for reference in interaction.evidence
            )
        }
    )
    contract = projection_input.contract.model_copy(
        update={"interactions": (misrouted,)}
    )
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"contract": contract})
    )

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    assert ("SOURCE_UNVERIFIED", "interactions[0]/binding/no_such_field") in {
        (issue["code"], issue["location"]) for issue in report["issues"]
    }


def test_project_contract_reports_domain_rule_findings_in_the_run(
    tmp_path: Path,
) -> None:
    projection_input = _graphql_projection_input()
    contract = projection_input.contract.model_copy(
        update={
            "claims": (
                ContractClaim(identity="viewer.login", status=ClaimStatus.SUPPORTED),
            )
        }
    )
    result, output = _run_graphql(
        tmp_path, projection_input.model_copy(update={"contract": contract})
    )

    assert result.exit_code == 1
    report = json.loads((output / "validation" / "report.json").read_text())
    assert ("SOURCE_UNVERIFIED", "claims[0]") in {
        (issue["code"], issue["location"]) for issue in report["issues"]
    }


def test_project_contract_leaves_no_partial_run_when_writing_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "run"

    def explode(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("loop_apidoc.protocol_run.run._write_run", explode)

    with pytest.raises(OSError):
        project_contract(
            _graphql_projection_input(),
            contract_format=ContractFormat.GRAPHQL,
            output=output,
        )

    assert not output.exists()
    # The staging directory is a sibling of the target; none may survive.
    assert list(tmp_path.iterdir()) == []


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
