from __future__ import annotations

from datetime import datetime

from loop_apidoc.core.models import (
    CorrectionRequest,
    PolicyFinding,
    PolicyProfile,
    ValidationDecision,
    ValidationVerdict,
    Waiver,
)
from loop_apidoc.domain.rules import DomainFinding


class ValidationPolicyEngine:
    def decide(
        self,
        findings: tuple[DomainFinding, ...],
        profile: PolicyProfile,
        *,
        waivers: tuple[Waiver, ...] = (),
        now: datetime | None = None,
        runtime_confidence: float | None = None,
    ) -> ValidationDecision:
        del runtime_confidence
        if waivers and now is None:
            raise ValueError("waiver evaluation requires an injected current time")
        overrides = dict(profile.severity_overrides)
        policy_findings: list[PolicyFinding] = []
        for finding in findings:
            severity = overrides.get(finding.code, finding.default_severity)
            waiver = (
                _matching_waiver(finding, waivers, now)
                if profile.allow_waivers and waivers and now is not None
                else None
            )
            if waiver is not None:
                severity = "waived"
            policy_findings.append(
                PolicyFinding(
                    code=finding.code,
                    message=finding.message,
                    location=finding.location,
                    severity=severity,
                    claim_identity=finding.claim_identity,
                    root_cause=finding.root_cause,
                    waiver_id=waiver.id if waiver else None,
                )
            )
        blocking = any(item.severity == "error" for item in policy_findings)
        warnings = any(item.severity == "warning" for item in policy_findings)
        verdict = (
            ValidationVerdict.REJECT
            if blocking
            else ValidationVerdict.REVIEW
            if warnings and profile.human_review_on_warnings
            else ValidationVerdict.ACCEPT
        )
        corrections = _corrections(policy_findings) if blocking else ()
        return ValidationDecision(
            verdict=verdict,
            policy_profile=profile.name,
            findings=tuple(policy_findings),
            corrections=corrections,
        )


def _matching_waiver(
    finding: DomainFinding,
    waivers: tuple[Waiver, ...],
    now: datetime,
) -> Waiver | None:
    for waiver in waivers:
        if waiver.expires_at > now and waiver.claim_identity == finding.claim_identity:
            if not waiver.scope or finding.location in waiver.scope:
                return waiver
    return None


def _corrections(findings: list[PolicyFinding]) -> tuple[CorrectionRequest, ...]:
    grouped: dict[str, set[str]] = {}
    for finding in findings:
        if finding.severity != "error":
            continue
        root = finding.root_cause or finding.claim_identity or finding.location
        grouped.setdefault(root, set()).add(finding.code)
    return tuple(
        CorrectionRequest(root_cause=root, finding_codes=tuple(sorted(codes)))
        for root, codes in sorted(grouped.items())
    )
