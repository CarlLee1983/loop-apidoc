from __future__ import annotations

import inspect
from datetime import datetime, timezone

from loop_apidoc.adapters.runtime import CallableRuntimeAdapter
from loop_apidoc.core.models import ClaimProposal, ExtractionWorkItem, RuntimeResult
from loop_apidoc.domain.evidence import (
    ClaimSupportProposal,
    EvidenceBundle,
    EvidenceFragment,
    FragmentPrecision,
    LineRangeLocator,
    SourceArtifact,
    SupportRelationshipType,
    VerificationMethod,
    fragment_digest,
)
from loop_apidoc.domain.rules import ApiDomainRulePack
from loop_apidoc.evaluation.models import (
    EvaluationCase,
    ExpectedClaim,
    ExpectedRelationship,
)
from loop_apidoc.evaluation.replay import ReplayRunner


def test_replay_runner_has_no_production_mutation_ports():
    assert set(inspect.signature(ReplayRunner).parameters) == {"runtime", "domain_pack"}


def test_replay_is_reproducible_for_fixed_runtime_result():
    result = RuntimeResult(
        claim_proposals=(
            ClaimProposal(
                id="p1",
                claim_kind="operation",
                subject="GET /health",
                predicate="exists",
                value=True,
                evidence_refs=("fragment-1",),
                runtime_identity="parser",
            ),
        ),
        runtime_identity="parser",
        runtime_version="1",
    )
    runtime = CallableRuntimeAdapter("parser", "1", lambda _: result)
    case = EvaluationCase(
        id="case-1",
        version="1",
        work_item=ExtractionWorkItem(
            task_id="task",
            evidence_scope=("fragment-1",),
            requested_claim_kinds=("operation",),
            output_schema="claim-proposal/v1",
            correlation_id="correlation",
        ),
        expected_claims=(
            ExpectedClaim(
                identity="claim:operation:GET /health:exists",
                value=True,
                evidence_refs=("fragment-1",),
            ),
        ),
    )
    runner = ReplayRunner(runtime=runtime, domain_pack=ApiDomainRulePack(version="1"))

    assert runner.run(case) == runner.run(case)
    assert runner.run(case).metrics.claim_recall == 1.0


def test_replay_uses_deterministic_verifier_when_case_supplies_evidence():
    fragment = EvidenceFragment(
        id="fragment-1",
        source_artifact_id="artifact-1",
        locator=LineRangeLocator(start_line=1, end_line=1),
        fragment_digest=fragment_digest("healthy"),
        normalized_excerpt="healthy",
        semantic_value="healthy",
        semantic_role="status.value",
        precision=FragmentPrecision.EXACT,
    )
    bundle = EvidenceBundle(
        source_set_id="sources",
        source_set_version="1",
        artifacts=(
            SourceArtifact(
                id="artifact-1",
                source_id="manual",
                media_type="text/markdown",
                content_digest="a" * 64,
                acquired_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
            ),
        ),
        fragments=(fragment,),
    )
    result = RuntimeResult(
        claim_proposals=(
            ClaimProposal(
                id="p1",
                claim_kind="scalar",
                subject="health",
                predicate="status",
                value="healthy",
                evidence_refs=("fragment-1",),
                support_proposals=(
                    ClaimSupportProposal(
                        fragment_id="fragment-1",
                        claim_path="",
                        proposed_relationship=(
                            SupportRelationshipType.EXPLICIT_SUPPORT
                        ),
                        verification_method=(
                            VerificationMethod.EXACT_NORMALIZED_VALUE
                        ),
                    ),
                ),
                runtime_identity="parser",
            ),
        ),
        runtime_identity="parser",
        runtime_version="1",
    )
    case = EvaluationCase(
        id="case-semantic",
        version="1",
        work_item=ExtractionWorkItem(
            task_id="task",
            evidence_scope=("fragment-1",),
            requested_claim_kinds=("scalar",),
            output_schema="claim-proposal/v1",
            correlation_id="correlation",
        ),
        expected_claims=(
            ExpectedClaim(
                identity="claim:scalar:health:status",
                value="healthy",
                evidence_refs=("fragment-1",),
            ),
        ),
        expected_relationships=(
            ExpectedRelationship(
                claim_identity="claim:scalar:health:status",
                claim_path="",
                fragment_id="fragment-1",
                relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
            ),
        ),
        evidence_bundle=bundle,
    )
    runner = ReplayRunner(
        runtime=CallableRuntimeAdapter("parser", "1", lambda _: result),
        domain_pack=ApiDomainRulePack(version="1"),
    )

    report = runner.run(case)

    assert report.metrics.semantic_support_precision == 1.0
    assert report.metrics.semantic_support_recall == 1.0
    assert report.metrics.claim_path_coverage == 1.0
