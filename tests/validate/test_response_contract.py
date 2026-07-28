from __future__ import annotations

from loop_apidoc.validate.models import IssueCode, Severity
from loop_apidoc.validate.response_contract import analyze_response_contracts


def _openapi(schema: dict | None) -> dict:
    response: dict = {"description": "OK"}
    if schema is not None:
        response["content"] = {"application/json": {"schema": schema}}
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo", "version": "1"},
        "paths": {"/items": {"get": {"responses": {"200": response}}}},
    }


def test_success_response_without_content_is_hollow_warning() -> None:
    analysis = analyze_response_contracts(_openapi(None))

    assert analysis.metrics.path_operations == 1
    assert analysis.metrics.operations_with_usable_schema == 0
    assert analysis.metrics.hollow_operations == 1
    assert analysis.metrics.field_count == 0
    assert len(analysis.issues) == 1
    assert analysis.issues[0].code is IssueCode.REQUIRED_INFO_MISSING
    assert analysis.issues[0].severity is Severity.WARNING
    assert analysis.issues[0].location == "paths./items.get"
    assert analysis.issues[0].field_path == "responses"


def test_empty_object_response_schema_is_hollow() -> None:
    analysis = analyze_response_contracts(_openapi({"type": "object"}))

    assert analysis.metrics.operations_with_usable_schema == 0
    assert analysis.metrics.hollow_operations == 1
    assert analysis.metrics.field_count == 0
    assert len(analysis.issues) == 1


def test_nested_object_and_array_response_fields_are_counted() -> None:
    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "data": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"code": {"type": "integer"}},
                },
            },
        },
    }

    analysis = analyze_response_contracts(_openapi(schema))

    assert analysis.metrics.operations_with_usable_schema == 1
    assert analysis.metrics.hollow_operations == 0
    assert analysis.metrics.field_count == 3
    assert analysis.issues == []


def test_local_schema_reference_fields_are_counted() -> None:
    openapi = _openapi({"$ref": "#/components/schemas/Item"})
    openapi["components"] = {
        "schemas": {
            "Item": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "details": {"$ref": "#/components/schemas/Details"},
                },
            },
            "Details": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
        }
    }

    analysis = analyze_response_contracts(openapi)

    assert analysis.metrics.operations_with_usable_schema == 1
    assert analysis.metrics.field_count == 2
    assert analysis.issues == []


def test_composed_schema_fields_are_counted() -> None:
    schema = {
        "allOf": [
            {
                "type": "object",
                "properties": {"id": {"type": "string"}},
            },
            {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                    {
                        "type": "object",
                        "properties": {"code": {"type": "integer"}},
                    },
                ]
            },
        ]
    }

    analysis = analyze_response_contracts(_openapi(schema))

    assert analysis.metrics.operations_with_usable_schema == 1
    assert analysis.metrics.field_count == 3
    assert analysis.issues == []


def test_generated_missing_response_placeholder_does_not_duplicate_issue() -> None:
    openapi = _openapi(None)
    openapi["paths"]["/items"]["get"]["responses"] = {
        "default": {
            "description": "來源未提供回應定義",
            "x-loop-status": "missing-source",
        }
    }

    analysis = analyze_response_contracts(openapi)

    assert analysis.metrics.path_operations == 1
    assert analysis.metrics.operations_with_usable_schema == 0
    assert analysis.metrics.hollow_operations == 1
    assert analysis.metrics.field_count == 0
    assert analysis.issues == []
