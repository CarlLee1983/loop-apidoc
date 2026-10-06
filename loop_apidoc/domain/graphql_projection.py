"""GraphQL SDL 投影編譯器與其 schema block 輔助函式。"""

from __future__ import annotations


from loop_apidoc.domain.models import (
    GraphqlOperationKind,
    GraphqlTransportBinding,
    GroundedApiContract,
    Schema,
)
from loop_apidoc.domain.projections import (
    Projection,
    ProjectionInput,
    UnsupportedProjectionError,
    _projection_input,
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
            if any(
                field == binding.root_field
                for field, _ in root_fields[binding.operation_kind]
            ):
                # Duplicated root fields are invalid SDL; refuse rather than
                # emit a document no GraphQL consumer can parse.
                raise UnsupportedProjectionError(
                    "graphql projection cannot represent two "
                    f"{binding.operation_kind.value} interactions on root field "
                    f"{binding.root_field!r}"
                )
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
