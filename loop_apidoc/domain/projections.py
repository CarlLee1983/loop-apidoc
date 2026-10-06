from __future__ import annotations

import json
import re
from typing import Protocol


from loop_apidoc.domain.evidence import (
    EvidenceBundle,
    SourceSet,
)
from loop_apidoc.domain.models import (
    FrozenModel,
    GroundedApiContract,
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


_MISSING_SOURCE_STATUS = "missing-source"
_COMPONENT_SCHEMA_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _field_schema(field_type: str | None, schema_ref: str | None) -> dict:
    if schema_ref:
        return {"$ref": _component_schema_ref(schema_ref)}
    return {"type": field_type} if field_type else {}


def _require_component_schema_names(schemas: tuple[Schema, ...]) -> None:
    for schema in schemas:
        if _COMPONENT_SCHEMA_NAME_RE.fullmatch(schema.name) is None:
            raise UnsupportedProjectionError(
                f"invalid component schema name: {schema.name!r}"
            )


def _component_schema_ref(schema_name: str) -> str:
    schema_token = schema_name.replace("~", "~0").replace("/", "~1")
    return f"#/components/schemas/{schema_token}"


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
