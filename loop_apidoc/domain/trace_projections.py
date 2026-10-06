"""Review 與 provenance 投影編譯器，以及 trace / binding 輔助函式。"""

from __future__ import annotations


from pydantic import BaseModel

from loop_apidoc.domain.asyncapi_projection import _asyncapi_action
from loop_apidoc.domain.models import (
    AsyncApiTransportBinding,
    EvidenceBinding,
    GraphqlOperationKind,
    GraphqlTransportBinding,
    GroundedApiContract,
    HttpTransportBinding,
)
from loop_apidoc.domain.projections import (
    Projection,
    ProjectionInput,
    UnsupportedProjectionError,
    _canonical_json,
    _projection_input,
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
        if projection_input.source_set is None or projection_input.evidence is None:
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
            values.append(
                (
                    binding,
                    _schema_target(contract, schema.name, binding.claim_path),
                )
            )
        for field in schema.fields:
            for binding in field.evidence:
                if binding.claim_path is None:
                    continue
                claim_path = binding.claim_path
                if not claim_path.startswith("/fields/"):
                    claim_path = f"/fields/{field.name}{claim_path}"
                values.append(
                    (
                        binding,
                        _schema_target(contract, schema.name, claim_path),
                    )
                )
    known = {(binding.relationship_id, target) for binding, target in values}
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


def _schema_target(
    contract: GroundedApiContract,
    schema_name: str,
    claim_path: str,
) -> str:
    parts = claim_path.strip("/").split("/") if claim_path.strip("/") else []
    transports = {
        interaction.binding.transport for interaction in contract.interactions
    }
    if transports == {"graphql"}:
        base = f"graphql:{schema_name}"
        if len(parts) >= 2 and parts[0] == "fields":
            suffix = ".".join(parts[1:])
            return f"{base}.{suffix}"
    elif transports == {"asyncapi"}:
        base = f"asyncapi:components.schemas.{schema_name}"
        if len(parts) >= 2 and parts[0] == "fields":
            suffix = ".".join(parts[1:])
            return f"{base}.properties.{suffix}"
    else:
        base = f"components.schemas.{schema_name}"
    suffix = ".".join(parts)
    return base + (f".{suffix}" if suffix else "")


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
