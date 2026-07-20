from __future__ import annotations

from loop_apidoc.core.ports import RuntimePort
from loop_apidoc.domain.identity import canonical_claim_identity
from loop_apidoc.domain.rules import ApiDomainRulePack
from loop_apidoc.evaluation.metrics import evaluate_claims
from loop_apidoc.evaluation.models import (
    EvaluationCase,
    ExpectedClaim,
    ReplayComparison,
    ReplayReport,
)


class ReplayRunner:
    def __init__(self, runtime: RuntimePort, domain_pack: ApiDomainRulePack) -> None:
        self.runtime = runtime
        self.domain_pack = domain_pack

    def run(self, case: EvaluationCase) -> ReplayReport:
        result = self.runtime.propose(case.work_item)
        observed = tuple(
            ExpectedClaim(
                identity=canonical_claim_identity(
                    proposal.claim_kind,
                    proposal.subject,
                    proposal.predicate,
                ),
                value=proposal.value,
                evidence_refs=proposal.evidence_refs,
            )
            for proposal in result.claim_proposals
        )
        metrics = evaluate_claims(case.expected_claims, observed)
        return ReplayReport(
            case_id=case.id,
            case_version=case.version,
            runtime_identity=result.runtime_identity,
            runtime_version=result.runtime_version,
            domain_version=self.domain_pack.version,
            metrics=metrics,
            cost=result.resource_usage.cost,
            latency_ms=result.resource_usage.latency_ms,
            diagnostics=result.diagnostics,
        )


def compare_replays(
    baseline: ReplayReport,
    candidate: ReplayReport,
) -> ReplayComparison:
    return ReplayComparison(
        baseline_runtime=baseline.runtime_identity,
        candidate_runtime=candidate.runtime_identity,
        precision_delta=(
            candidate.metrics.claim_precision - baseline.metrics.claim_precision
        ),
        recall_delta=candidate.metrics.claim_recall - baseline.metrics.claim_recall,
        cost_delta=_delta(candidate.cost, baseline.cost),
        latency_delta_ms=_delta(candidate.latency_ms, baseline.latency_ms),
    )


def _delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline
