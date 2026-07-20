from __future__ import annotations

from loop_apidoc.evaluation.metrics import evaluate_claims
from loop_apidoc.evaluation.models import ExpectedClaim


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
