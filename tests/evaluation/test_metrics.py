from __future__ import annotations

from loop_apidoc.domain.evidence import SupportRelationshipType
from loop_apidoc.evaluation.metrics import evaluate_claims, evaluate_relationships
from loop_apidoc.evaluation.models import ExpectedClaim, ExpectedRelationship


def test_claim_precision_and_recall_are_independent_metrics():
    expected = (ExpectedClaim(identity="a", value=True),)
    observed = (
        ExpectedClaim(identity="a", value=True),
        ExpectedClaim(identity="b", value=True),
    )

    report = evaluate_claims(expected, observed)

    assert report.claim_precision == 0.5
    assert report.claim_recall == 1.0
    assert report.unsupported_assertion_rate == 0.5


def _relationship(
    relationship: SupportRelationshipType,
    *,
    fragment_id: str = "fragment-summary",
) -> ExpectedRelationship:
    return ExpectedRelationship(
        claim_identity="claim:operation:GET /health:definition",
        claim_path="/summary",
        fragment_id=fragment_id,
        relationship=relationship,
    )


def test_relationship_metrics_distinguish_reference_from_support():
    expected = (_relationship(SupportRelationshipType.EXPLICIT_SUPPORT),)
    observed = (_relationship(SupportRelationshipType.INSUFFICIENT),)

    report = evaluate_relationships(expected, observed)

    assert report.semantic_support_precision == 0.0
    assert report.semantic_support_recall == 0.0
    assert report.claim_path_coverage == 0.0


def test_contradiction_detection_recall_counts_exact_mismatch():
    contradiction = _relationship(
        SupportRelationshipType.CONTRADICTS,
        fragment_id="fragment-currency",
    )

    report = evaluate_relationships((contradiction,), (contradiction,))

    assert report.contradiction_detection_recall == 1.0


def test_multiple_fragments_supporting_one_path_are_scored_independently():
    expected = (
        _relationship(
            SupportRelationshipType.EXPLICIT_SUPPORT,
            fragment_id="fragment-a",
        ),
        _relationship(
            SupportRelationshipType.EXPLICIT_SUPPORT,
            fragment_id="fragment-b",
        ),
    )

    report = evaluate_relationships(expected, expected[:1])

    assert report.semantic_support_precision == 1.0
    assert report.semantic_support_recall == 0.5
    assert report.claim_path_coverage == 1.0
