from __future__ import annotations

import json
from typing import Protocol

from loop_apidoc.domain.models import GroundedApiContract


class ProjectionCompiler(Protocol):
    name: str
    version: str

    def compile(self, contract: GroundedApiContract) -> "Projection": ...


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

    def __init__(self, version: str) -> None:
        self.version = version

    def compile(self, contract: GroundedApiContract) -> Projection:
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
            paths.setdefault(operation.path, {})[operation.method.lower()] = {
                **({"summary": operation.summary} if operation.summary else {}),
                "responses": responses,
                **(
                    {"security": [{name: []} for name in operation.security]}
                    if operation.security
                    else {}
                ),
            }
        payload = {
            "openapi": "3.1.0",
            "info": {
                "title": contract.metadata.title,
                "version": contract.metadata.version,
            },
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

    def compile(self, contract: GroundedApiContract) -> Projection:
        return Projection(
            name=self.name,
            version=self.version,
            media_type="application/json",
            content=_canonical_json(contract.model_dump(mode="json")),
        )


def _field_schema(field_type: str | None, schema_ref: str | None) -> dict:
    if schema_ref:
        return {"$ref": f"#/components/schemas/{schema_ref}"}
    return {"type": field_type} if field_type else {}


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
