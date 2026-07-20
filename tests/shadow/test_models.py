from __future__ import annotations

from loop_apidoc.core.models import (
    GroundedClaim,
    ValidationDecision,
    ValidationVerdict,
)
from loop_apidoc.domain.models import ClaimStatus
from loop_apidoc.run.models import RunStatus
from loop_apidoc.shadow.models import (
    ArchitectureMode,
    BridgeDiagnostic,
    ShadowStage,
    compare_results,
)
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def test_architecture_mode_and_stage_are_string_enums():
    assert ArchitectureMode.LEGACY.value == "legacy"
    assert ArchitectureMode.SHADOW.value == "shadow"
    assert ShadowStage.BRIDGE.value == "bridge"


def test_comparison_matches_nonblocking_semantics_and_sorts_codes():
    comparison = compare_results(
        legacy_report=ValidationReport(
            issues=[
                Issue(
                    code=IssueCode.SOURCE_UNVERIFIED,
                    severity=Severity.WARNING,
                    location="z",
                    evidence="source",
                    suggested_fix="review",
                ),
                Issue(
                    code=IssueCode.REQUIRED_INFO_MISSING,
                    severity=Severity.WARNING,
                    location="a",
                    evidence="source",
                    suggested_fix="review",
                ),
            ]
        ),
        legacy_status=RunStatus.PASSED,
        decision=ValidationDecision(
            verdict=ValidationVerdict.REVIEW,
            policy_profile="shadow",
        ),
        claims=(
            GroundedClaim(
                id="claim-1",
                canonical_identity="claim:operation:GET /ping:definition",
                claim_kind="operation",
                status=ClaimStatus.SUPPORTED,
            ),
            GroundedClaim(
                id="claim-2",
                canonical_identity="claim:schema:Payload:definition",
                claim_kind="schema",
                status=ClaimStatus.UNVERIFIED,
            ),
        ),
        diagnostics=(
            BridgeDiagnostic(
                code="CITATION_UNRESOLVED",
                message="missing.md is not acquired",
                plan_location="endpoints[0]",
                manifest_source="missing.md",
            ),
        ),
    )

    assert comparison.verdict_match is True
    assert comparison.legacy_status == "passed"
    assert comparison.legacy_error_count == 0
    assert comparison.legacy_warning_count == 2
    assert comparison.legacy_issue_codes == (
        "REQUIRED_INFO_MISSING",
        "SOURCE_UNVERIFIED",
    )
    assert comparison.core_verdict == "review"
    assert comparison.claim_counts.supported == 1
    assert comparison.claim_counts.unverified == 1
    assert comparison.diagnostics[0].code == "CITATION_UNRESOLVED"


def test_comparison_treats_core_reject_as_blocking():
    comparison = compare_results(
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        decision=ValidationDecision(
            verdict=ValidationVerdict.REJECT,
            policy_profile="shadow",
        ),
        claims=(),
        diagnostics=(),
    )

    assert comparison.verdict_match is False
