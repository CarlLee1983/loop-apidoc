from __future__ import annotations

import pytest

from loop_apidoc.domain.claim_paths import (
    ClaimPathError,
    claim_value_at,
    material_claim_paths,
)


def test_operation_paths_are_keyed_by_parameter_and_response_identity():
    value = {
        "method": "POST",
        "path": "/payments",
        "parameters": [
            {"name": "currency", "location": "query", "required": True},
            {"name": "amount", "location": "query", "required": True},
        ],
        "responses": [{"status_code": "200", "description": "OK"}],
    }

    assert material_claim_paths("operation", value) == (
        "/method",
        "/parameters/query/amount/name",
        "/parameters/query/amount/required",
        "/parameters/query/currency/name",
        "/parameters/query/currency/required",
        "/path",
        "/responses/200/description",
        "/responses/200/status_code",
    )
    assert (
        claim_value_at("operation", value, "/parameters/query/amount/required") is True
    )


def test_dynamic_segments_use_rfc6901_escaping():
    value = {"name": "Envelope", "fields": [{"name": "a/b~c", "type": "string"}]}

    assert "/fields/a~1b~0c/type" in material_claim_paths("schema", value)
    assert claim_value_at("schema", value, "/fields/a~1b~0c/type") == "string"


def test_reordering_semantic_collections_does_not_change_paths():
    first = {
        "method": "GET",
        "path": "/items",
        "parameters": [
            {"name": "limit", "location": "query", "required": False},
            {"name": "cursor", "location": "query", "required": False},
        ],
    }
    second = {**first, "parameters": list(reversed(first["parameters"]))}

    assert material_claim_paths("operation", first) == material_claim_paths(
        "operation", second
    )


def test_absent_optional_and_empty_collections_are_not_material():
    assert material_claim_paths(
        "operation",
        {
            "method": "GET",
            "path": "/health",
            "summary": None,
            "parameters": [],
            "responses": [],
        },
    ) == ("/method", "/path")


def test_scalar_claim_uses_root_path():
    assert material_claim_paths("custom", "USD") == ("",)
    assert claim_value_at("custom", "USD", "") == "USD"


def test_unknown_path_fails_closed():
    with pytest.raises(ClaimPathError, match="unknown material claim path"):
        claim_value_at("operation", {"method": "GET", "path": "/"}, "/summary")
