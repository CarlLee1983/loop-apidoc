"""Typed pydantic guards for agent-written extraction inputs.

These models exist purely to *validate* the JSON the agent writes
(`inventory.json`, `endpoints/ep<N>.json`, optional `integration.json`) at the
assemble boundary — they are not consumed by the pipeline (the raw dicts still
flow through `inventory_to_stage_answers` etc.). The goal is to fail loudly on
schema-contract mistakes (e.g. localized field keys, a malformed endpoint shape)
*before* a run directory is created, instead of letting them surface later as a
degraded output or a validation gap.

Design rules:
- Nulls / empty arrays stay allowed wherever a source may genuinely omit info —
  fail-closed gaps are surfaced by validation, not by rejecting the input.
- Only the localized-key hot spots (`schemas[].fields[]`, endpoint
  `parameters[]`) forbid unknown keys; `x-` extension keys are tolerated. Every
  other entry is permissive about extra keys to avoid false positives on
  free-form areas (`examples`, integration `test_cases[].request/response`).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator


class _StrictEntry(BaseModel):
    """Forbids unknown keys but tolerates `x-` extension keys (stripped before
    validation, since these models only gate — they do not feed the pipeline)."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_extensions(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not str(k).startswith("x-")}
        return data


class FieldEntry(_StrictEntry):
    name: str
    type: str | None = None
    required: bool | None = None
    description: str | None = None
    one_of: list[str] | None = None
    discriminator: dict[str, Any] | None = None


class ParamEntry(_StrictEntry):
    name: str
    in_: str | None = None
    type: str | None = None
    required: bool | None = None
    description: str | None = None
    one_of: list[str] | None = None
    discriminator: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _alias_in(cls, data: Any) -> Any:
        data = super()._drop_extensions(data)
        # `in` is a Python keyword; accept the source key and map it to `in_`.
        if isinstance(data, dict) and "in" in data:
            data = {**data, "in_": data["in"]}
            data.pop("in")
        return data


class _Lax(BaseModel):
    """Permissive base: known keys are type-checked, unknown keys ignored."""

    model_config = ConfigDict(extra="ignore")


class SchemaEntry(_Lax):
    name: str | None = None
    fields: list[FieldEntry] = []
    enums: list[Any] = []
    constraints: str | None = None
    source: str | None = None


class ResponseEntry(_Lax):
    status: str | None = None
    description: str | None = None
    # `schema` is left to extra="ignore" (a field named `schema` shadows a
    # pydantic BaseModel attribute); it is a free-form description string anyway.
    schema_ref: str | None = None


class EndpointDetailInput(_Lax):
    method: str | None = None
    path: str | None = None
    source: str | None = None
    parameters: list[ParamEntry] = []
    request: dict[str, Any] | None = None
    responses: list[ResponseEntry] = []
    tags: list[str] = []
    security: list[str] = []
    examples: list[Any] = []
    missing: list[Any] = []


class InventoryInput(_Lax):
    title: str | None = None
    version: str | None = None
    overview: str | None = None
    environments: list[dict[str, Any]] = []
    security_schemes: list[dict[str, Any]] = []
    endpoints: list[dict[str, Any]] = []
    schemas: list[SchemaEntry] = []
    errors: list[dict[str, Any]] = []
    operational: list[dict[str, Any]] = []
    missing: list[Any] = []


class IntegrationInput(_Lax):
    version: str | None = None
    crypto: list[dict[str, Any]] = []
    callbacks: list[dict[str, Any]] = []
    field_conditions: list[dict[str, Any]] = []
    test_cases: list[dict[str, Any]] = []
    missing: list[Any] = []


def _format_loc(loc: tuple[Any, ...]) -> str:
    out = ""
    for part in loc:
        part = "in" if part == "in_" else part  # report the source key name
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def first_error(exc: ValidationError) -> str:
    """One-line 'field.path: message' from the first validation error."""
    err = exc.errors()[0]
    return f"{_format_loc(tuple(err['loc']))}: {err['msg']}"
