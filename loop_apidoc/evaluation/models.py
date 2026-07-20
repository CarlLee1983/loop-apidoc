from __future__ import annotations

from typing import Any

from loop_apidoc.core.models import EvidenceBundle, ExtractionWorkItem, FrozenModel
from loop_apidoc.domain.evidence import SupportRelationshipType


class ExpectedClaim(FrozenModel):
    identity: str
    value: Any
    evidence_refs: tuple[str, ...] = ()


class ExpectedRelationship(FrozenModel):
    claim_identity: str
    claim_path: str
    fragment_id: str
    relationship: SupportRelationshipType


class EvaluationCase(FrozenModel):
    id: str
    version: str
    work_item: ExtractionWorkItem
    expected_claims: tuple[ExpectedClaim, ...] = ()
    expected_relationships: tuple[ExpectedRelationship, ...] = ()
    evidence_bundle: EvidenceBundle | None = None
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
    semantic_support_precision: float = 1.0
    semantic_support_recall: float = 1.0
    claim_path_coverage: float = 1.0
    contradiction_detection_recall: float = 1.0


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
