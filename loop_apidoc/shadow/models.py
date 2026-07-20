from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from loop_apidoc.core.models import (
    DomainEvent,
    EvidenceBundle,
    GroundedClaim,
    RuntimeResult,
    SourceSet,
    ValidationDecision,
    ValidationVerdict,
    WorkflowRecord,
)
from loop_apidoc.domain.models import (
    ClaimStatus,
    FrozenModel,
    GroundedApiContract,
)
from loop_apidoc.validate.models import ValidationReport

if TYPE_CHECKING:
    from loop_apidoc.run.models import RunStatus


class ArchitectureMode(str, Enum):
    LEGACY = "legacy"
    SHADOW = "shadow"


class ShadowStage(str, Enum):
    BRIDGE = "bridge"
    SERVICE = "service"
    COMPARISON = "comparison"
    REPORT = "report"


class BridgeDiagnostic(FrozenModel):
    code: str
    message: str
    plan_location: str | None = None
    manifest_source: str | None = None
    query_id: str | None = None
    answer_path: str | None = None


class ClaimCounts(FrozenModel):
    supported: int = 0
    missing: int = 0
    conflicting: int = 0
    unverified: int = 0
    waived: int = 0
    superseded: int = 0


class ShadowComparison(FrozenModel):
    legacy_status: str
    legacy_error_count: int
    legacy_warning_count: int
    legacy_issue_codes: tuple[str, ...]
    core_verdict: str
    core_finding_codes: tuple[str, ...]
    verdict_match: bool
    only_in_legacy: tuple[str, ...]
    only_in_core: tuple[str, ...]
    claim_counts: ClaimCounts
    diagnostics: tuple[BridgeDiagnostic, ...] = ()


class ShadowExecutionSummary(FrozenModel):
    status: str
    core_dir: str
    comparison_path: str | None = None
    error_path: str | None = None
    stage: ShadowStage | None = None
    exception_type: str | None = None
    message: str | None = None


class ShadowArtifacts(FrozenModel):
    source_set: SourceSet
    evidence: EvidenceBundle
    runtime_result: RuntimeResult
    claims: tuple[GroundedClaim, ...]
    contract: GroundedApiContract
    decision: ValidationDecision
    workflow: WorkflowRecord
    events: tuple[DomainEvent, ...]
    comparison: ShadowComparison
    artifact_publications: int = 0
    approval_requests: int = 0


def compare_results(
    *,
    legacy_report: ValidationReport,
    legacy_status: RunStatus,
    decision: ValidationDecision,
    claims: tuple[GroundedClaim, ...],
    diagnostics: tuple[BridgeDiagnostic, ...],
) -> ShadowComparison:
    legacy_codes = tuple(sorted({issue.code.value for issue in legacy_report.issues}))
    core_codes = tuple(sorted({finding.code for finding in decision.findings}))
    counts = {status.value: 0 for status in ClaimStatus}
    for claim in claims:
        counts[claim.status.value] += 1
    return ShadowComparison(
        legacy_status=legacy_status.value,
        legacy_error_count=len(legacy_report.errors()),
        legacy_warning_count=len(legacy_report.warnings()),
        legacy_issue_codes=legacy_codes,
        core_verdict=decision.verdict.value,
        core_finding_codes=core_codes,
        verdict_match=legacy_report.ok
        == (decision.verdict is not ValidationVerdict.REJECT),
        only_in_legacy=tuple(sorted(set(legacy_codes) - set(core_codes))),
        only_in_core=tuple(sorted(set(core_codes) - set(legacy_codes))),
        claim_counts=ClaimCounts(**counts),
        diagnostics=diagnostics,
    )
