from __future__ import annotations

import pytest
from pydantic import ValidationError

from loop_apidoc.domain.models import GroundedApiContract


def _metadata() -> dict[str, str]:
    return {
        "contract_id": "payment-demo",
        "title": "Payment Demo",
        "version": "1",
        "source_set_id": "sources",
        "source_set_version": "1",
        "domain_version": "1",
    }


def test_legacy_payment_collections_round_trip_through_the_payment_profile() -> None:
    legacy = {
        "metadata": _metadata(),
        "amount_directions": [
            {
                "operation_ref": "operation:POST:/deposit",
                "balance_effect": "credit",
                "amount_sign": "positive",
                "precision": "12,4",
            }
        ],
        "line_currency_policies": [
            {
                "scope": "Agent line",
                "policy": "single",
                "currency_binding": "agent",
                "operation_refs": ["operation:POST:/deposit"],
            }
        ],
    }

    contract = GroundedApiContract.model_validate(legacy)

    assert contract.payment_profile is not None
    assert contract.payment_profile.amount_directions[0].balance_effect == "credit"
    assert contract.payment_profile.line_currency_policies[0].policy == "single"
    dumped = contract.model_dump(mode="json", exclude_defaults=True)
    assert dumped["amount_directions"] == legacy["amount_directions"]
    assert dumped["line_currency_policies"] == legacy["line_currency_policies"]
    assert "payment_profile" not in dumped


def test_contract_rejects_two_payment_profile_representations() -> None:
    payload = {
        "metadata": _metadata(),
        "payment_profile": {
            "amount_directions": [{"balance_effect": "credit"}],
        },
        "amount_directions": [{"balance_effect": "debit"}],
    }

    with pytest.raises(ValidationError, match="cannot be combined"):
        GroundedApiContract.model_validate(payload)
