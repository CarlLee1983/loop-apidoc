from __future__ import annotations

from loop_apidoc.operation_identity import (
    endpoint_identity,
    expand_methods,
    extraction_identities,
)


def test_neutral_operation_identity_owns_shared_extraction_shape():
    inventory = {
        "endpoints": [
            {"methods": ["get", "POST"], "path": "/payments"},
            {"method": "POST", "path": None, "summary": "Payment\n result"},
        ]
    }
    endpoint_files = [
        ("ep0.json", {"method": "GET", "path": "/payments"}),
        ("ep1.json", {"method": "POST", "path": "/payments"}),
        ("ep2.json", {"method": "POST", "path": None, "summary": "Payment result"}),
    ]

    assert [entry["method"] for entry in expand_methods(inventory["endpoints"])] == [
        "GET",
        "POST",
        "POST",
    ]
    assert extraction_identities(inventory, endpoint_files) == {
        "GET /payments",
        "POST /payments",
        "POST (webhook) Payment result",
    }
    assert endpoint_identity.__module__ == "loop_apidoc.operation_identity"


def test_agentcli_identity_remains_a_compatibility_reexport():
    from loop_apidoc.agentcli.identity import endpoint_identity as legacy_endpoint_identity

    assert legacy_endpoint_identity is endpoint_identity
