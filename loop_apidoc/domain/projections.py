from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel

from loop_apidoc.domain.evidence import (
    EvidenceBundle,
    SourceSet,
    SupportRelationshipType,
)
from loop_apidoc.domain.models import (
    EvidenceBinding,
    FrozenModel,
    GroundedApiContract,
)


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
            responses = {
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
                for response in operation.responses
            }
            operation_payload = {
                **({"summary": operation.summary} if operation.summary else {}),
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
                            for parameter in operation.parameters
                        ]
                    }
                    if operation.parameters
                    else {}
                ),
                "responses": responses,
                **(
                    {"security": [{name: []} for name in operation.security]}
                    if operation.security
                    else {}
                ),
            }
            claim_map = _operation_claim_map(operation)
            if projection_input.evidence is not None and claim_map:
                operation_payload["x-loop-claim-map"] = claim_map
            paths.setdefault(operation.path, {})[
                operation.method.lower()
            ] = operation_payload
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
