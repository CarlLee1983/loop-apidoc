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


def test_interaction_paths_are_specific_to_the_explicit_transport_binding():
    graphql = {
        "identity": "interaction:graphql:query:product",
        "mode": "request_reply",
        "binding": {
            "transport": "graphql",
            "operation_kind": "query",
            "root_field": "product",
        },
    }
    asyncapi = {
        "identity": "interaction:asyncapi:orders.status.changed",
        "mode": "subscribe",
        "binding": {
            "transport": "asyncapi",
            "channel": "orders.status.changed",
            "direction": "subscribe",
            "message_name": "OrderStatusChanged",
        },
    }

    assert material_claim_paths("interaction", graphql) == (
        "/binding/operation_kind",
        "/binding/root_field",
        "/binding/transport",
        "/identity",
        "/mode",
    )
    assert material_claim_paths("interaction", asyncapi) == (
        "/binding/channel",
        "/binding/direction",
        "/binding/message_name",
        "/binding/transport",
        "/identity",
        "/mode",
    )
    assert (
        claim_value_at("interaction", asyncapi, "/binding/channel")
        == "orders.status.changed"
    )


def test_operational_applicability_has_stable_material_paths():
    value = {
        "topic": "Cancel amount",
        "detail": "Use the wager amount.",
        "applies_to": [
            {"operation": "POST /cancel", "field": "request.amount"}
        ],
    }

    assert material_claim_paths("operational_constraint", value) == (
        "/applies_to/POST ~1cancel#request.amount/field",
        "/applies_to/POST ~1cancel#request.amount/operation",
        "/detail",
        "/topic",
    )
    assert claim_value_at(
        "operational_constraint",
        value,
        "/applies_to/POST ~1cancel#request.amount/field",
    ) == "request.amount"


def test_domain_semantics_have_stable_material_claim_paths():
    operation = "operation:POST:/deposit"

    assert material_claim_paths(
        "transport_policy",
        {
            "name": "HTTP defaults",
            "protocol": "HTTPS",
            "methods": ["POST"],
            "operation_refs": [operation],
        },
    ) == (
        "/methods/POST",
        "/name",
        "/operation_refs/operation:POST:~1deposit",
        "/protocol",
    )
    assert material_claim_paths(
        "amount_direction",
        {
            "operation_ref": operation,
            "balance_effect": "credit",
            "amount_sign": "positive",
            "precision": "12,4",
        },
    ) == (
        "/amount_sign",
        "/balance_effect",
        "/operation_ref",
        "/precision",
    )
    assert material_claim_paths(
        "idempotency_rule",
        {
            "operation_refs": [operation],
            "code": "9",
            "meaning": "Duplicate transaction.",
            "action": "Treat as processed.",
        },
    ) == (
        "/action",
        "/code",
        "/meaning",
        "/operation_refs/operation:POST:~1deposit",
    )
    assert material_claim_paths(
        "line_currency_policy",
        {
            "scope": "Agent line",
            "policy": "single",
            "currency_binding": "agent",
            "operation_refs": [operation],
        },
    ) == (
        "/currency_binding",
        "/operation_refs/operation:POST:~1deposit",
        "/policy",
        "/scope",
    )
    assert claim_value_at(
        "line_currency_policy",
        {"policy": "single"},
        "/policy",
    ) == "single"


def test_unknown_path_fails_closed():
    with pytest.raises(ClaimPathError, match="unknown material claim path"):
        claim_value_at("operation", {"method": "GET", "path": "/"}, "/summary")
