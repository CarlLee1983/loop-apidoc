from __future__ import annotations

from loop_apidoc.core.models import ClaimProposal
from loop_apidoc.core.reconciliation import reconcile_claims
from loop_apidoc.domain.models import ClaimStatus


def _proposal(
    proposal_id: str,
    value: object,
    evidence_refs: tuple[str, ...],
    runtime: str = "runtime-a",
) -> ClaimProposal:
    return ClaimProposal(
        id=proposal_id,
        claim_kind="operation",
        subject="POST /payments",
        predicate="exists",
        value=value,
        evidence_refs=evidence_refs,
        runtime_identity=runtime,
    )


def test_runtime_consensus_without_valid_evidence_remains_unverified():
    proposals = (
        _proposal("p1", True, ("missing",), "runtime-a"),
        _proposal("p2", True, ("missing",), "runtime-b"),
    )

    claims = reconcile_claims(proposals, evidence_fragment_ids=frozenset())

    assert claims[0].status is ClaimStatus.UNVERIFIED


def test_incompatible_supported_values_are_conflicting():
    proposals = (
        _proposal("p1", {"summary": "A"}, ("fragment-a",)),
        _proposal("p2", {"summary": "B"}, ("fragment-b",)),
    )

    claims = reconcile_claims(
        proposals,
        evidence_fragment_ids=frozenset({"fragment-a", "fragment-b"}),
    )

    assert claims[0].status is ClaimStatus.CONFLICTING
    assert len(claims[0].value) == 2


def test_supported_duplicates_merge_evidence_and_ignore_confidence():
    proposals = (
        _proposal("p1", True, ("fragment-a",)),
        _proposal("p2", True, ("fragment-b",), "runtime-b"),
    )

    claims = reconcile_claims(
        proposals,
        evidence_fragment_ids=frozenset({"fragment-a", "fragment-b"}),
    )

    assert claims[0].status is ClaimStatus.SUPPORTED
    assert claims[0].evidence_refs == ("fragment-a", "fragment-b")
