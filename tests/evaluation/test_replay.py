from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from loop_apidoc.adapters.runtime import CallableRuntimeAdapter
from loop_apidoc.core.models import ClaimProposal, ExtractionWorkItem, RuntimeResult
from loop_apidoc.domain.evidence import (
    ClaimSupportProposal,
    DerivationStep,
    EvidenceBundle,
    EvidenceFragment,
    FragmentPrecision,
    LineRangeLocator,
    SourceArtifact,
    SupportRelationshipType,
    VerificationMethod,
    WholeDocumentLocator,
    canonical_json,
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


def _relationship_case(
    relationship: SupportRelationshipType,
) -> tuple[EvaluationCase, CallableRuntimeAdapter]:
    """Build one fixed, versioned replay case for a verifier outcome."""
    fragment_id = f"fragment-{relationship.value}"
    # Runtimes can propose only explicit or derived support. Contradiction and
    # insufficiency are deterministic verifier outcomes, not runtime labels.
    proposed_relationship = (
        relationship
        if relationship in {
            SupportRelationshipType.EXPLICIT_SUPPORT,
            SupportRelationshipType.DERIVED_SUPPORT,
        }
        else SupportRelationshipType.EXPLICIT_SUPPORT
    )
    if relationship is SupportRelationshipType.CONTRADICTS:
        fragment = EvidenceFragment(
            id=fragment_id,
            source_artifact_id="artifact-relationships",
            locator=LineRangeLocator(start_line=1, end_line=1),
            fragment_digest=fragment_digest("TWD"),
            normalized_excerpt="TWD",
            semantic_value="TWD",
            semantic_role="currency.value",
            precision=FragmentPrecision.EXACT,
        )
    elif relationship is SupportRelationshipType.INSUFFICIENT:
        # Whole-document references cannot support a material field claim. The
        # runtime proposes explicit support, which deterministic verification
        # must downgrade to insufficient.
        fragment = EvidenceFragment(
            id=fragment_id,
            source_artifact_id="artifact-relationships",
            locator=WholeDocumentLocator(),
            fragment_digest=fragment_digest("Currency: USD"),
            normalized_excerpt="Currency: USD",
            precision=FragmentPrecision.DOCUMENT,
        )
    else:
        fragment = EvidenceFragment(
            id=fragment_id,
            source_artifact_id="artifact-relationships",
            locator=LineRangeLocator(start_line=1, end_line=1),
            fragment_digest=fragment_digest("USD"),
            normalized_excerpt="USD",
            semantic_value="USD",
            semantic_role="currency.value",
            precision=FragmentPrecision.EXACT,
        )

    derivation_steps = ()
    if relationship is SupportRelationshipType.DERIVED_SUPPORT:
        derivation_steps = (
            DerivationStep(
                name="canonical_json",
                version="1",
                input_digests=(fragment_digest("USD"),),
                output_digest=fragment_digest(canonical_json("USD")),
            ),
        )
    proposal = ClaimProposal(
        id=f"proposal-{relationship.value}",
        claim_kind="scalar",
        subject="payment",
        predicate="currency",
        value="USD",
        evidence_refs=(fragment_id,),
        support_proposals=(
            ClaimSupportProposal(
                fragment_id=fragment_id,
                claim_path="",
                proposed_relationship=proposed_relationship,
                verification_method=VerificationMethod.EXACT_NORMALIZED_VALUE,
                derivation_steps=derivation_steps,
            ),
        ),
        runtime_identity="relationship-benchmark",
    )
    bundle = EvidenceBundle(
        source_set_id="relationship-benchmark",
        source_set_version="1",
        artifacts=(
            SourceArtifact(
                id="artifact-relationships",
                source_id="manual.md",
                media_type="text/markdown",
                content_digest="a" * 64,
                acquired_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
            ),
        ),
        fragments=(fragment,),
    )
    case = EvaluationCase(
        id=f"evidence-relationship-{relationship.value}",
        version="1",
        work_item=ExtractionWorkItem(
            task_id="relationship-benchmark",
            evidence_scope=(fragment_id,),
            requested_claim_kinds=("scalar",),
            output_schema="claim-proposal/v1",
            correlation_id=f"relationship-{relationship.value}",
        ),
        expected_claims=(
            ExpectedClaim(
                identity="claim:scalar:payment:currency",
                value="USD",
                evidence_refs=(fragment_id,),
            ),
        ),
        expected_relationships=(
            ExpectedRelationship(
                claim_identity="claim:scalar:payment:currency",
                claim_path="",
                fragment_id=fragment_id,
                relationship=relationship,
            ),
        ),
        evidence_bundle=bundle,
    )
    runtime_result = RuntimeResult(
        claim_proposals=(proposal,),
        runtime_identity="relationship-benchmark",
        runtime_version="1",
    )
    return case, CallableRuntimeAdapter(
        "relationship-benchmark", "1", lambda _work_item: runtime_result
    )


@pytest.mark.parametrize("relationship", list(SupportRelationshipType))
def test_relationship_benchmarks_cover_each_deterministic_outcome(relationship):
    case, runtime = _relationship_case(relationship)

    report = ReplayRunner(
        runtime=runtime,
        domain_pack=ApiDomainRulePack(version="1"),
    ).run(case)

    assert report.case_id == f"evidence-relationship-{relationship.value}"
    assert report.metrics.claim_precision == 1.0
    assert report.metrics.claim_recall == 1.0
    assert report.metrics.relationship_classification_accuracy == 1.0
