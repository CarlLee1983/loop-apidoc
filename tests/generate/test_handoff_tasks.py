from __future__ import annotations

from loop_apidoc.generate.handoff import build_handoff
from loop_apidoc.plan.models import (
    ContractTestCase,
    CryptoScheme,
    IntegrationContract,
    KeySource,
    MissingItem,
    NormalizationPlan,
    PlanItemStatus,
    SourceConflict,
    UnverifiedItem,
)


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="n/a",
        missing_items=[MissingItem(area="crypto", detail="source does not state AES padding for TradeInfo")],
        source_conflicts=[SourceConflict(area="auth", detail="two base URLs disagree")],
        unverified_items=[UnverifiedItem(area="rate_limit", detail="rate limit not stated in source")],
        integration=IntegrationContract(
            crypto=[
                CryptoScheme(
                    status=PlanItemStatus.SUPPORTED,
                    name="TradeInfo",
                    purpose="request",
                    key_source=KeySource(key="HASH_KEY", iv="HASH_IV"),
                )
            ],
            test_cases=[
                ContractTestCase(
                    status=PlanItemStatus.SUPPORTED,
                    name="happy_path",
                    operation_ref="post_payments",
                )
            ],
        ),
    )


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Pay API", "version": "1.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {"/payments": {"post": {"operationId": "createPayment"}}},
        "components": {
            "securitySchemes": {"merchantKey": {"type": "apiKey", "in": "header", "name": "X-Key"}}
        },
    }


def _tasks() -> str:
    return build_handoff(_openapi(), _plan(), {"crypto": [{"name": "TradeInfo"}], "missing": [{"area": "auth", "detail": "rate limit not stated"}]})[
        "handoff/integration-tasks.md"
    ]


def test_tasks_run_context_links():
    md = _tasks()
    assert "../openapi.yaml" in md
    assert "../integration-contract.json" in md
    assert "../validation/report.md" in md


def test_tasks_implementation_order_has_pointer():
    md = _tasks()
    assert "createPayment" in md
    assert "../openapi.yaml#/paths/~1payments/post" in md


def test_tasks_runtime_config_base_url_and_auth():
    md = _tasks()
    assert "base_url" in md
    assert "merchantKey" in md  # auth variable from security scheme


def test_tasks_crypto_and_blockers():
    md = _tasks()
    assert "../integration-contract.json#/crypto/0" in md
    assert "Conflict" in md      # source_conflicts
    assert "Blocked" in md       # missing_items
    assert "Unverified" in md    # unverified_items
    assert "Gap" in md           # integration["missing"]
    assert "AES padding" in md
    assert "../integration-contract.json#/test_cases/0" in md  # test_cases rendered


def test_tasks_no_schema_tables():
    md = _tasks()
    # navigation only — never a request-body field table / response schema copy
    assert "properties" not in md
    assert "| Field | Type |" not in md
