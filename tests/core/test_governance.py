from __future__ import annotations

from datetime import datetime, timezone

import pytest

from loop_apidoc.core.governance import (
    ApprovalRejected,
    approve_release,
    make_candidate_release,
    publish_release,
)
from loop_apidoc.core.models import (
    Actor,
    ActorKind,
    ApprovalDecision,
    ReleaseStatus,
    ValidationDecision,
    ValidationVerdict,
)
from loop_apidoc.domain.models import ContractMetadata, GroundedApiContract


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def _contract() -> GroundedApiContract:
    return GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="contract-1",
            title="Demo",
            version="1",
            source_set_id="sources",
            source_set_version="1",
            domain_version="1",
        )
    )


def _candidate():
    return make_candidate_release(
        _contract(),
        ValidationDecision(verdict=ValidationVerdict.ACCEPT, policy_profile="strict"),
        runtime_identities=("runtime-a",),
        core_version="1",
        policy_version="1",
        projection_versions=(("openapi", "1"),),
        now=NOW,
    )


def test_runtime_cannot_approve_its_own_release():
    approval = ApprovalDecision(
        approved=True,
        actor=Actor(id="runtime-a", kind=ActorKind.RUNTIME),
        decided_at=NOW,
    )

    with pytest.raises(ApprovalRejected):
        approve_release(_candidate(), approval)


def test_approved_release_can_publish_without_mutating_candidate():
    candidate = _candidate()
    approved = approve_release(
        candidate,
        ApprovalDecision(
            approved=True,
            actor=Actor(id="reviewer", kind=ActorKind.APPROVER),
            decided_at=NOW,
        ),
    )
    published = publish_release(approved, ("artifact://openapi",), NOW)

    assert candidate.status is ReleaseStatus.CANDIDATE
    assert approved.status is ReleaseStatus.APPROVED
    assert published.status is ReleaseStatus.PUBLISHED
    assert published.release_id == candidate.release_id


def test_release_identity_uses_canonical_contract_json():
    from loop_apidoc.domain.models import ClaimStatus, ContractClaim

    first = _contract().model_copy(
        update={
            "claims": (
                ContractClaim(
                    identity="claim-1",
                    status=ClaimStatus.UNVERIFIED,
                    value={"a": 1, "b": 2},
                ),
            )
        }
    )
    second = _contract().model_copy(
        update={
            "claims": (
                ContractClaim(
                    identity="claim-1",
                    status=ClaimStatus.UNVERIFIED,
                    value={"b": 2, "a": 1},
                ),
            )
        }
    )
    decision = ValidationDecision(
        verdict=ValidationVerdict.ACCEPT,
        policy_profile="strict",
    )

    releases = [
        make_candidate_release(
            contract,
            decision,
            runtime_identities=(),
            core_version="1",
            policy_version="1",
            projection_versions=(),
            now=NOW,
        )
        for contract in (first, second)
    ]

    assert releases[0].release_id == releases[1].release_id
