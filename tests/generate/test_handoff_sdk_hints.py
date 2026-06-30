from __future__ import annotations

import json

from loop_apidoc.generate.handoff import build_handoff
from loop_apidoc.plan.models import (
    CryptoScheme,
    IntegrationContract,
    NormalizationPlan,
    PlanItemStatus,
)


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="n/a",
        integration=IntegrationContract(
            crypto=[CryptoScheme(status=PlanItemStatus.SUPPORTED, name="TradeInfo", purpose="request")]
        ),
    )


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Pay API", "version": "1.0"},
        "servers": [{"url": "https://api.example.com"}],
        "tags": [{"name": "Payments"}],
        "paths": {
            "/payments": {
                "post": {"operationId": "createPayment", "tags": ["Payments"]}
            }
        },
    }


def _hints(openapi: dict, plan: NormalizationPlan) -> dict:
    out = build_handoff(openapi, plan, {"crypto": [{"name": "TradeInfo"}], "missing": []})
    return json.loads(out["handoff/sdk-hints.json"])


def test_sdk_hints_top_level_keys():
    data = _hints(_openapi(), _plan())
    assert set(data) >= {"version", "contracts", "operation_groups", "implementation_notes", "gaps"}
    assert data["contracts"] == {
        "openapi": "../openapi.yaml",
        "integration": "../integration-contract.json",
    }


def test_sdk_hints_operation_note_shape():
    data = _hints(_openapi(), _plan())
    note = next(n for n in data["implementation_notes"] if n["operation_id"] == "createPayment")
    assert note["method"] == "POST"
    assert note["path"] == "/payments"
    assert note["contract_pointer"] == "../openapi.yaml#/paths/~1payments/post"
    assert "runtime:base_url" in note["requires"]
    assert "crypto:TradeInfo" in note["requires"]


def test_sdk_hints_groups_from_tags():
    data = _hints(_openapi(), _plan())
    group = next(g for g in data["operation_groups"] if g["name"] == "Payments")
    assert "createPayment" in group["operations"]


def test_sdk_hints_does_not_copy_schemas():
    blob = build_handoff(_openapi(), _plan(), {"crypto": [{"name": "TradeInfo"}], "missing": []})[
        "handoff/sdk-hints.json"
    ]
    assert "properties" not in blob
    assert "requestBody" not in blob
