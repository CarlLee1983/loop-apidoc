"""OpenAPI 投影編譯器與其 operation / payload 輔助函式。"""

from __future__ import annotations


from loop_apidoc.domain.evidence import (
    SupportRelationshipType,
)
from loop_apidoc.domain.models import (
    EvidenceBinding,
    GroundedApiContract,
    HttpTransportBinding,
)
from loop_apidoc.domain.projections import (
    Projection,
    ProjectionInput,
    UnsupportedProjectionError,
    _MISSING_SOURCE_STATUS,
    _canonical_json,
    _component_schema_ref,
    _field_schema,
    _projection_input,
    _require_component_schema_names,
)


class OpenApiProjectionCompiler:
    name = "openapi"

    def __init__(self, version: str) -> None:
        self.version = version

    def compile(
        self,
        contract: GroundedApiContract | ProjectionInput,
    ) -> Projection:
        projection_input = _projection_input(contract)
        contract = projection_input.contract
        _require_component_schema_names(contract.schemas)
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
            _add_openapi_operation(
                paths,
                method=operation.method,
                path=operation.path,
                payload=operation_payload,
            )
        for interaction in contract.interactions:
            binding = interaction.binding
            if not isinstance(binding, HttpTransportBinding):
                raise UnsupportedProjectionError(
                    "openapi projection does not support "
                    f"{binding.transport!r} interactions"
                )
            _add_openapi_operation(
                paths,
                method=binding.method,
                path=binding.path,
                payload=_openapi_interaction_payload(interaction),
            )
        info = {
            "title": contract.metadata.title,
            "version": contract.metadata.version or "0.0.0",
        }
        if contract.metadata.version is None:
            info["x-loop-status"] = _MISSING_SOURCE_STATUS
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


def _add_openapi_operation(
    paths: dict[str, dict],
    *,
    method: str,
    path: str,
    payload: dict,
) -> None:
    path_item = paths.setdefault(path, {})
    method_key = method.lower()
    if method_key in path_item:
        raise UnsupportedProjectionError(
            "openapi projection cannot represent two HTTP operations on "
            f"{method.upper()} {path}"
        )
    path_item[method_key] = payload


def _openapi_operation_payload(operation) -> dict:
    return _openapi_payload(
        summary=operation.summary,
        parameters=operation.parameters,
        request_schema_ref=operation.request_schema_ref,
        responses=operation.responses,
        security=operation.security,
    )


def _openapi_interaction_payload(interaction) -> dict:
    binding = interaction.binding
    return _openapi_payload(
        summary=interaction.summary,
        parameters=binding.parameters,
        request_schema_ref=binding.request_schema_ref,
        responses=binding.responses,
        security=binding.security,
    )


def _openapi_payload(
    *, summary, parameters, responses, security, request_schema_ref=None
) -> dict:
    response_payload = {
        response.status_code: {
            "description": response.description or "",
            **(
                {
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": _component_schema_ref(response.schema_ref)
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
                                    "$ref": _component_schema_ref(parameter.schema_ref)
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
        **(
            {
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": _component_schema_ref(request_schema_ref)
                            }
                        }
                    }
                }
            }
            if request_schema_ref
            else {}
        ),
        "responses": response_payload,
        **({"security": [{name: []} for name in security]} if security else {}),
    }


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
