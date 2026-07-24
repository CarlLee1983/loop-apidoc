from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel
import yaml

from loop_apidoc.domain.evidence import (
    EvidenceBundle,
    SourceSet,
    SupportRelationshipType,
)
from loop_apidoc.domain.models import (
    AsyncApiDirection,
    AsyncApiTransportBinding,
    EvidenceBinding,
    FrozenModel,
    GraphqlOperationKind,
    GraphqlTransportBinding,
    GroundedApiContract,
    HttpTransportBinding,
    Schema,
)


class UnsupportedProjectionError(ValueError):
    """A projection cannot faithfully represent one of the contract interactions."""


class ProjectionInput(FrozenModel):
    contract: GroundedApiContract
    source_set: SourceSet | None = None
    evidence: EvidenceBundle | None = None


class ProjectionCompiler(Protocol):
    name: str
    version: str

    def compile(
        self,
        contract: GroundedApiContract | ProjectionInput,
    ) -> "Projection": ...


class Projection:
    __slots__ = ("content", "media_type", "name", "version")

    def __init__(
        self, *, name: str, version: str, media_type: str, content: bytes
    ) -> None:
        self.name = name
        self.version = version
        self.media_type = media_type
        self.content = content

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Projection):
            return NotImplemented
        return (
            self.name,
            self.version,
            self.media_type,
            self.content,
        ) == (
            other.name,
            other.version,
            other.media_type,
            other.content,
        )


class OpenApiProjectionCompiler:
    name = "openapi"
    _MISSING_SOURCE_STATUS = "missing-source"

    def __init__(self, version: str) -> None:
        self.version = version

    def compile(
        self,
        contract: GroundedApiContract | ProjectionInput,
    ) -> Projection:
        projection_input = _projection_input(contract)
        contract = projection_input.contract
        schemas = {
            schema.name: {
                "type": "object",
                "properties": {
                    field.name: _field_schema(field.type, field.schema_ref)
                    for field in schema.fields
                },
                **(
                    {
                        "required": [
                            field.name for field in schema.fields if field.required
                        ]
                    }
                    if any(field.required for field in schema.fields)
                    else {}
                ),
            }
            for schema in contract.schemas
        }
        paths: dict[str, dict] = {}
        for operation in contract.operations:
            operation_payload = _openapi_operation_payload(operation)
            claim_map = _operation_claim_map(operation)
            if projection_input.evidence is not None and claim_map:
                operation_payload["x-loop-claim-map"] = claim_map
            paths.setdefault(operation.path, {})[
                operation.method.lower()
            ] = operation_payload
        for interaction in contract.interactions:
            binding = interaction.binding
            if not isinstance(binding, HttpTransportBinding):
                raise UnsupportedProjectionError(
                    "openapi projection does not support "
                    f"{binding.transport!r} interactions"
                )
            paths.setdefault(binding.path, {})[binding.method.lower()] = (
                _openapi_interaction_payload(interaction)
            )
        info = {
            "title": contract.metadata.title,
            "version": contract.metadata.version or "0.0.0",
        }
        if contract.metadata.version is None:
            info["x-loop-status"] = self._MISSING_SOURCE_STATUS
        payload = {
            "openapi": "3.1.0",
            "info": info,
            "servers": [
                {"url": server, "description": environment.name}
                for environment in contract.environments
                for server in environment.servers
            ],
            "paths": paths,
            "components": {
                "schemas": schemas,
                "securitySchemes": {
                    scheme.name: {"type": scheme.type} for scheme in contract.security
                },
            },
        }
        return Projection(
            name=self.name,
            version=self.version,
            media_type="application/vnd.oai.openapi+json;version=3.1",
            content=_canonical_json(payload),
        )


class GraphqlProjectionCompiler:
    """Compile GraphQL interactions into a deterministic SDL projection."""

    name = "graphql"

    def __init__(self, version: str) -> None:
        self.version = version

    def compile(
        self,
        contract: GroundedApiContract | ProjectionInput,
    ) -> Projection:
        contract = _projection_input(contract).contract
        schema_names = {schema.name for schema in contract.schemas}
        root_fields: dict[GraphqlOperationKind, list[tuple[str, str]]] = {
            GraphqlOperationKind.QUERY: [],
            GraphqlOperationKind.MUTATION: [],
            GraphqlOperationKind.SUBSCRIPTION: [],
        }
        for interaction in contract.interactions:
            binding = interaction.binding
            if not isinstance(binding, GraphqlTransportBinding):
                raise UnsupportedProjectionError(
                    "graphql projection does not support "
                    f"{binding.transport!r} interactions"
                )
            if binding.output_schema_ref is None:
                raise UnsupportedProjectionError(
                    "graphql projection requires an explicit output schema reference"
                )
            if binding.output_schema_ref not in schema_names:
                raise UnsupportedProjectionError(
                    "graphql projection cannot resolve output schema "
                    f"{binding.output_schema_ref!r}"
                )
            output_type = binding.output_schema_ref
            if binding.output_required:
                output_type += "!"
            root_fields[binding.operation_kind].append(
                (binding.root_field, output_type)
            )

        blocks = [
            _graphql_root_block(kind, fields)
            for kind, fields in (
                (GraphqlOperationKind.QUERY, root_fields[GraphqlOperationKind.QUERY]),
                (
                    GraphqlOperationKind.MUTATION,
                    root_fields[GraphqlOperationKind.MUTATION],
                ),
                (
                    GraphqlOperationKind.SUBSCRIPTION,
                    root_fields[GraphqlOperationKind.SUBSCRIPTION],
                ),
            )
            if fields
        ]
        blocks.extend(_graphql_schema_block(schema) for schema in contract.schemas)
        content = "\n\n".join(blocks) + ("\n" if blocks else "")
        return Projection(
            name=self.name,
            version=self.version,
            media_type="application/graphql",
            content=content.encode(),
        )


class AsyncApiProjectionCompiler:
    """Compile AsyncAPI interactions into a deterministic AsyncAPI 3 document."""

    name = "asyncapi"

    def __init__(self, version: str) -> None:
        self.version = version

    def compile(
        self,
        contract: GroundedApiContract | ProjectionInput,
    ) -> Projection:
        contract = _projection_input(contract).contract
        channels: dict[str, dict] = {}
        operations: dict[str, dict] = {}
        for interaction in contract.interactions:
            binding = interaction.binding
            if not isinstance(binding, AsyncApiTransportBinding):
                raise UnsupportedProjectionError(
                    "asyncapi projection does not support "
                    f"{binding.transport!r} interactions"
                )
            if binding.channel_address is None:
                raise UnsupportedProjectionError(
                    "asyncapi projection requires an explicit channel address"
                )
            if binding.payload_schema_ref is None:
                raise UnsupportedProjectionError(
                    "asyncapi projection requires an explicit payload schema reference"
                )
            channels[binding.channel] = {
                "address": binding.channel_address,
                "messages": {
                    binding.message_name: {
                        "payload": {
                            "$ref": (
                                "#/components/schemas/"
                                f"{binding.payload_schema_ref}"
                            )
                        }
                    }
                },
            }
            operations[binding.channel] = {
                "action": _asyncapi_action(binding.direction),
                "channel": {"$ref": f"#/channels/{binding.channel}"},
            }
        payload = {
            "asyncapi": "3.0.0",
            "info": {
                "title": contract.metadata.title,
                "version": contract.metadata.version or "0.0.0",
            },
            "channels": channels,
            "operations": operations,
            "components": {
                "schemas": {
                    schema.name: _asyncapi_schema_payload(schema)
                    for schema in contract.schemas
                }
            },
        }
        return Projection(
            name=self.name,
            version=self.version,
            media_type="application/yaml",
            content=yaml.safe_dump(
                payload,
                allow_unicode=True,
                sort_keys=True,
            ).encode(),
        )


class ReviewProjectionCompiler:
    name = "review-data"

    def __init__(self, version: str) -> None:
        self.version = version

    def compile(
        self,
        contract: GroundedApiContract | ProjectionInput,
    ) -> Projection:
        projection_input = _projection_input(contract)
        if (
            projection_input.source_set is None
            or projection_input.evidence is None
        ):
            payload = projection_input.contract.model_dump(mode="json")
        else:
            payload = {
                "contract": projection_input.contract.model_dump(mode="json"),
                "relationships": _trace_entries(projection_input),
            }
        return Projection(
            name=self.name,
            version=self.version,
            media_type="application/json",
            content=_canonical_json(payload),
        )


class ProvenanceProjectionCompiler:
    name = "provenance"

    def __init__(self, version: str) -> None:
        self.version = version

    def compile(
        self,
        contract: GroundedApiContract | ProjectionInput,
    ) -> Projection:
        projection_input = _projection_input(contract)
        entries = (
            _trace_entries(projection_input)
            if projection_input.source_set is not None
            and projection_input.evidence is not None
            else []
        )
        return Projection(
            name=self.name,
            version=self.version,
            media_type="application/json",
            content=_canonical_json({"entries": entries}),
        )


def _field_schema(field_type: str | None, schema_ref: str | None) -> dict:
    if schema_ref:
        return {"$ref": f"#/components/schemas/{schema_ref}"}
    return {"type": field_type} if field_type else {}


def _graphql_root_block(
    kind: GraphqlOperationKind,
    fields: list[tuple[str, str]],
) -> str:
    root_name = {
        GraphqlOperationKind.QUERY: "Query",
        GraphqlOperationKind.MUTATION: "Mutation",
        GraphqlOperationKind.SUBSCRIPTION: "Subscription",
    }[kind]
    rendered_fields = "\n".join(
        f"  {name}: {output_type}" for name, output_type in sorted(fields)
    )
    return f"type {root_name} {{\n{rendered_fields}\n}}"


def _graphql_schema_block(schema: Schema) -> str:
    fields: list[str] = []
    for field in schema.fields:
        field_type = field.schema_ref or field.type
        if field_type is None:
            raise UnsupportedProjectionError(
                f"graphql projection requires a type for schema field {schema.name}.{field.name}"
            )
        if field.required:
            field_type += "!"
        fields.append(f"  {field.name}: {field_type}")
    rendered_fields = "\n".join(sorted(fields))
    return f"type {schema.name} {{\n{rendered_fields}\n}}"


def _asyncapi_action(direction: AsyncApiDirection) -> str:
    return "send" if direction == AsyncApiDirection.PUBLISH else "receive"


def _asyncapi_schema_payload(schema: Schema) -> dict:
    properties = {
        field.name: _field_schema(field.type, field.schema_ref)
        for field in schema.fields
    }
    return {
        "type": "object",
        "properties": properties,
        **(
            {
                "required": [
                    field.name for field in schema.fields if field.required
                ]
            }
            if any(field.required for field in schema.fields)
            else {}
        ),
    }


def _openapi_operation_payload(operation) -> dict:
    return _openapi_payload(
        summary=operation.summary,
        parameters=operation.parameters,
        responses=operation.responses,
        security=operation.security,
    )


def _openapi_interaction_payload(interaction) -> dict:
    binding = interaction.binding
    return _openapi_payload(
        summary=interaction.summary,
        parameters=binding.parameters,
        responses=binding.responses,
        security=binding.security,
    )


def _openapi_payload(*, summary, parameters, responses, security) -> dict:
    response_payload = {
        response.status_code: {
            "description": response.description or "",
            **(
                {
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": f"#/components/schemas/{response.schema_ref}"
                            }
                        }
                    }
                }
                if response.schema_ref
                else {}
            ),
        }
        for response in responses
    }
    return {
        **({"summary": summary} if summary else {}),
        **(
            {
                "parameters": [
                    {
                        "name": parameter.name,
                        "in": parameter.location,
                        **(
                            {"required": parameter.required}
                            if parameter.required is not None
                            else {}
                        ),
                        **(
                            {
                                "schema": {
                                    "$ref": (
                                        "#/components/schemas/"
                                        f"{parameter.schema_ref}"
                                    )
                                }
                            }
                            if parameter.schema_ref
                            else {}
                        ),
                    }
                    for parameter in parameters
                ]
            }
            if parameters
            else {}
        ),
        "responses": response_payload,
        **({"security": [{name: []} for name in security]} if security else {}),
    }


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _projection_input(
    value: GroundedApiContract | ProjectionInput,
) -> ProjectionInput:
    if isinstance(value, ProjectionInput):
        return value
    return ProjectionInput(contract=value)


def _operation_claim_map(operation) -> dict[str, dict]:
    grouped: dict[str, list[EvidenceBinding]] = {}
    for binding in operation.evidence:
        if (
            binding.claim_path is None
            or binding.relationship_id is None
            or binding.relationship
            not in {
                SupportRelationshipType.EXPLICIT_SUPPORT,
                SupportRelationshipType.DERIVED_SUPPORT,
            }
        ):
            continue
        grouped.setdefault(binding.claim_path, []).append(binding)
    return {
        path: {
            "claim_identity": bindings[0].claim_identity,
            "claim_path": path,
            "relationships": [
                {
                    "relationship_id": binding.relationship_id,
                    "fragment_id": binding.fragment_id,
                    "relationship": binding.relationship.value,
                }
                for binding in sorted(
                    bindings,
                    key=lambda item: (
                        item.relationship_id or "",
                        item.fragment_id,
                    ),
                )
            ],
        }
        for path, bindings in sorted(grouped.items())
    }


def _trace_entries(projection_input: ProjectionInput) -> list[dict]:
    source_set = projection_input.source_set
    evidence = projection_input.evidence
    if source_set is None or evidence is None:
        return []
    fragments = {fragment.id: fragment for fragment in evidence.fragments}
    artifacts = {artifact.id: artifact for artifact in evidence.artifacts}
    sources = {source.id: source for source in source_set.sources}
    entries: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for binding, target in _binding_targets(projection_input.contract):
        if binding.relationship_id is None or binding.claim_path is None:
            continue
        key = (binding.relationship_id, target)
        if key in seen:
            continue
        seen.add(key)
        fragment = fragments.get(binding.fragment_id)
        if fragment is None:
            continue
        artifact = artifacts.get(fragment.source_artifact_id)
        if artifact is None:
            continue
        source = sources.get(artifact.source_id)
        if source is None:
            continue
        entries.append(
            {
                "target": target,
                "claim_identity": binding.claim_identity,
                "claim_path": binding.claim_path,
                "relationship_id": binding.relationship_id,
                "relationship": (
                    binding.relationship.value
                    if binding.relationship is not None
                    else None
                ),
                "fragment_id": fragment.id,
                "fragment_locator": fragment.locator.model_dump(
                    mode="json",
                    exclude_none=True,
                ),
                "fragment_digest": fragment.fragment_digest,
                "source_artifact_id": artifact.id,
                "source_artifact_digest": artifact.content_digest,
                "source_id": source.id,
                "source_locator": source.locator,
            }
        )
    return sorted(
        entries,
        key=lambda item: (
            item["target"],
            item["claim_identity"] or "",
            item["claim_path"],
            item["relationship_id"],
            item["fragment_id"],
        ),
    )


def _binding_targets(
    contract: GroundedApiContract,
) -> tuple[tuple[EvidenceBinding, str], ...]:
    values: list[tuple[EvidenceBinding, str]] = []
    for operation in contract.operations:
        for binding in operation.evidence:
            if binding.claim_path is None:
                continue
            values.append(
                (
                    binding,
                    _operation_target(
                        operation.path,
                        operation.method,
                        binding.claim_path,
                    ),
                )
            )
    for interaction in contract.interactions:
        for binding in (*interaction.evidence, *interaction.binding.evidence):
            if binding.claim_path is not None:
                values.append(
                    (
                        binding,
                        _interaction_target(interaction, binding.claim_path),
                    )
                )
    for schema in contract.schemas:
        for binding in schema.evidence:
            if binding.claim_path is None:
                continue
            suffix = binding.claim_path.strip("/").replace("/", ".")
            values.append(
                (
                    binding,
                    f"components.schemas.{schema.name}"
                    + (f".{suffix}" if suffix else ""),
                )
            )
    known = {
        (binding.relationship_id, target) for binding, target in values
    }
    for binding in _semantic_bindings(contract):
        if any(key[0] == binding.relationship_id for key in known):
            continue
        suffix = (binding.claim_path or "").strip("/").replace("/", ".")
        target = f"claims.{binding.claim_identity}"
        if suffix:
            target = f"{target}.{suffix}"
        values.append((binding, target))
    return tuple(values)


def _operation_target(path: str, method: str, claim_path: str) -> str:
    base = f"paths.{path}.{method.lower()}"
    suffix = claim_path.strip("/").replace("/", ".")
    if claim_path in {"/method", "/path"} or not suffix:
        return base
    return f"{base}.{suffix}"


def _interaction_target(interaction, claim_path: str) -> str:
    binding = interaction.binding
    if isinstance(binding, HttpTransportBinding):
        return _operation_target(binding.path, binding.method, "/")
    if isinstance(binding, GraphqlTransportBinding):
        root = {
            GraphqlOperationKind.QUERY: "Query",
            GraphqlOperationKind.MUTATION: "Mutation",
            GraphqlOperationKind.SUBSCRIPTION: "Subscription",
        }[binding.operation_kind]
        return f"graphql:{root}.{binding.root_field}"
    if isinstance(binding, AsyncApiTransportBinding):
        target = (
            f"asyncapi:{binding.channel}.{_asyncapi_action(binding.direction)}"
            f".message.{binding.message_name}"
        )
        if claim_path == "/binding/payload_schema_ref":
            return f"{target}.payload"
        return target
    raise UnsupportedProjectionError(
        f"provenance projection does not support {binding.transport!r} interactions"
    )


def _semantic_bindings(value: object) -> tuple[EvidenceBinding, ...]:
    found: dict[
        tuple[str | None, str, str | None],
        EvidenceBinding,
    ] = {}

    def visit(item: object) -> None:
        if isinstance(item, EvidenceBinding):
            if item.relationship_id is not None:
                found[
                    (
                        item.relationship_id,
                        item.fragment_id,
                        item.claim_path,
                    )
                ] = item
            return
        if isinstance(item, BaseModel):
            for name in type(item).model_fields:
                visit(getattr(item, name))
            return
        if isinstance(item, tuple | list):
            for child in item:
                visit(child)

    visit(value)
    return tuple(
        found[key]
        for key in sorted(
            found,
            key=lambda item: (
                item[0] or "",
                item[1],
                item[2] or "",
            ),
        )
    )
