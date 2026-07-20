from __future__ import annotations

from typing import Any

from loop_apidoc.core.models import ExtractionWorkItem, FrozenModel


class ExpectedClaim(FrozenModel):
    identity: str
    value: Any
    evidence_refs: tuple[str, ...] = ()


class EvaluationCase(FrozenModel):
    id: str
    version: str
    work_item: ExtractionWorkItem
    expected_claims: tuple[ExpectedClaim, ...] = ()
    expected_missing: tuple[str, ...] = ()
    expected_conflicts: tuple[str, ...] = ()
    risk_classification: str = "standard"
    evaluator_version: str = "1"


class MetricReport(FrozenModel):
    claim_precision: float
    claim_recall: float
    unsupported_assertion_rate: float
    evidence_reference_correctness: float
    field_omission_rate: float
    conflict_detection_recall: float


class ReplayReport(FrozenModel):
    case_id: str
    case_version: str
    runtime_identity: str
    runtime_version: str
    domain_version: str
    metrics: MetricReport
    cost: float | None = None
    latency_ms: float | None = None
    diagnostics: tuple[str, ...] = ()


class ReplayComparison(FrozenModel):
    baseline_runtime: str
    candidate_runtime: str
    precision_delta: float
    recall_delta: float
    cost_delta: float | None = None
    latency_delta_ms: float | None = None
