"""AsyncAPI 投影編譯器與其 action / schema payload 輔助函式。"""

from __future__ import annotations


import yaml

from loop_apidoc.domain.models import (
    AsyncApiDirection,
    AsyncApiTransportBinding,
    GroundedApiContract,
    Schema,
)
from loop_apidoc.domain.projections import (
    Projection,
    ProjectionInput,
    UnsupportedProjectionError,
    _MISSING_SOURCE_STATUS,
    _field_schema,
    _projection_input,
    _require_component_schema_names,
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
        _require_component_schema_names(contract.schemas)
        schema_names = {schema.name for schema in contract.schemas}
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
            if binding.payload_schema_ref not in schema_names:
                raise UnsupportedProjectionError(
                    "asyncapi projection cannot resolve payload schema "
                    f"{binding.payload_schema_ref!r}"
                )
            if binding.channel in channels:
                # A single-entry map would drop the earlier slice with no gap
                # record. Refuse to emit rather than lose a documented channel.
                raise UnsupportedProjectionError(
                    "asyncapi projection cannot represent two interactions on "
                    f"channel {binding.channel!r}"
                )
            payload_schema_token = binding.payload_schema_ref.replace(
                "~", "~0"
            ).replace("/", "~1")
            channels[binding.channel] = {
                "address": binding.channel_address,
                "messages": {
                    binding.message_name: {
                        "payload": {
                            "$ref": (f"#/components/schemas/{payload_schema_token}")
                        }
                    }
                },
            }
            channel_token = binding.channel.replace("~", "~0").replace("/", "~1")
            operations[binding.channel] = {
                "action": _asyncapi_action(binding.direction),
                "channel": {"$ref": f"#/channels/{channel_token}"},
            }
        info = {
            "title": contract.metadata.title,
            "version": contract.metadata.version or "0.0.0",
        }
        if contract.metadata.version is None:
            info["x-loop-status"] = _MISSING_SOURCE_STATUS
        payload = {
            "asyncapi": "3.0.0",
            "info": info,
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
            {"required": [field.name for field in schema.fields if field.required]}
            if any(field.required for field in schema.fields)
            else {}
        ),
    }
