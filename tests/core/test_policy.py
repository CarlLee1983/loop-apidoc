from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.core.models import PolicyProfile, ValidationVerdict, Waiver
from loop_apidoc.core.policy import ValidationPolicyEngine
from loop_apidoc.domain.rules import DomainFinding


def _finding(severity: str = "error") -> DomainFinding:
    return DomainFinding(
        code="SCHEMA_REFERENCE_UNRESOLVED",
        message="missing schema",
        location="operations[0]",
        claim_identity="claim-1",
        default_severity=severity,
        root_cause="schema:Missing",
    )


def test_policy_verdict_ignores_runtime_confidence():
    engine = ValidationPolicyEngine()
    profile = PolicyProfile(name="strict")

    low = engine.decide((_finding(),), profile, runtime_confidence=0.01)
    high = engine.decide((_finding(),), profile, runtime_confidence=0.99)

    assert low.verdict is ValidationVerdict.REJECT
    assert low.verdict == high.verdict
    assert len(low.corrections) == 1


def test_active_scoped_waiver_removes_blocking_severity():
    engine = ValidationPolicyEngine()
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    waiver = Waiver(
        id="waiver-1",
        claim_identity="claim-1",
        reason="accepted temporarily",
        approved_by="reviewer",
        expires_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )

    decision = engine.decide(
        (_finding(),), PolicyProfile(name="strict"), waivers=(waiver,), now=now
    )

    assert decision.verdict is ValidationVerdict.ACCEPT
    assert decision.findings[0].severity == "waived"
