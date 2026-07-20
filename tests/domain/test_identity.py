from __future__ import annotations

import pytest
from pydantic import ValidationError

from loop_apidoc.domain.identity import (
    DomainIdentityError,
    canonical_claim_identity,
    canonical_operation_identity,
    canonical_schema_identity,
)
from loop_apidoc.domain.models import ContractMetadata, GroundedApiContract


def test_operation_identity_is_stable_across_method_case():
    assert (
        canonical_operation_identity("post", "/payments") == "operation:POST:/payments"
    )


def test_identity_rejects_non_rooted_path():
    with pytest.raises(DomainIdentityError):
        canonical_operation_identity("GET", "payments")


def test_schema_and_claim_identities_are_order_independent():
    assert canonical_schema_identity(" Payment ") == "schema:Payment"
    assert canonical_claim_identity("field", " Payment.amount ", "type") == (
        "claim:field:Payment.amount:type"
    )


def test_contract_is_immutable():
    contract = GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="contract-1",
            title="Payments",
            version="1",
            source_set_id="sources",
            source_set_version="1",
            domain_version="1",
        )
    )

    with pytest.raises(ValidationError):
        contract.operations = ()
