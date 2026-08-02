from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from loop_apidoc.core.conformance import ContractConformance, canonical_digest
from loop_apidoc.core.governance import contract_digest
from loop_apidoc.domain.conformance import (
    AmendmentApproval,
    ApplicabilityEnvelope,
    BoundedVerification,
    CompatibilityAmendment,
    CompatibilityAmendmentProposal,
    ConformanceCoverage,
    ConformanceRelationship,
    ConformanceRelationshipType,
    EffectiveContract,
    FeedbackAssessment,
    FeedbackRoute,
    IdentityVersion,
    ImplementationObservation,
    MaterialClaimReference,
    NormativeRelease,
    NormativeBaseBinding,
    ObservationAttempt,
    ObservationBundle,
    ObservationEvidence,
    ObservationKind,
    ObservationLineage,
    ObservationOutcome,
    ReplayRecipe,
    SanitizedObservationFact,
    normative_release_digest,
)
from loop_apidoc.domain.models import (
    ClaimStatus,
    ContractClaim,
    ContractMetadata,
    GroundedApiContract,
    Operation,
    Response,
)
from loop_apidoc.domain.evidence import EvidenceBundle
from loop_apidoc.feedback.loader import (
    load_current_scope_amendments,
)
from loop_apidoc.foundry import feedback, query, register, store
from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifacts,
    AssetStatus,
    AssetValidation,
    CurrentPointer,
    Docset,
    FeedbackReviewDecision,
    FoundryInputError,
)

_NOW = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 8, 2, 10, 5, tzinfo=timezone.utc)


def _sanitized_facts() -> tuple[SanitizedObservationFact, ...]:
    return (
        SanitizedObservationFact(kind=ObservationKind.RESPONSE_STATUS, value="201"),
    )


def _evidence_digest() -> str:
    payload = json.dumps(
        [fact.model_dump(mode="json") for fact in _sanitized_facts()],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _contract() -> GroundedApiContract:
    operation = Operation(
        method="POST",
        path="/charges",
        responses=(Response(status_code="200", description="OK"),),
    )
    return GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="payments",
            title="Payments",
            version="1",
            source_set_id="sources",
            source_set_version="1",
            domain_version="1",
        ),
        operations=(operation,),
        claims=(
            ContractClaim(
                identity="response:charges",
                claim_kind="operation",
                status=ClaimStatus.SUPPORTED,
                value=operation.model_dump(mode="json", exclude={"evidence"}),
            ),
        ),
    )


def _scope() -> ApplicabilityEnvelope:
    return ApplicabilityEnvelope(
        provider="provider",
        product="payments",
        api_version="2026-01",
        environment="sandbox",
        region="tw",
        endpoint_identity="https://sandbox.example.test",
        account_class="merchant",
        feature_flags=("async-capture",),
        authentication_role="server",
        client_version="client/1",
        harness_version="harness/2",
        test_data_class="synthetic",
        observed_from=_NOW,
        observed_until=_LATER,
    )


def _bundle(*, observed: object = "201", suffix: str = "1") -> ObservationBundle:
    return ObservationBundle(
        schema_version="implementation-observation-bundle/v1",
        bundle_id=f"bundle-{suffix}",
        base=NormativeBaseBinding(
            docset_id="payments",
            asset_id="payments-base",
            contract_digest=contract_digest(_contract()),
        ),
        policy_version="conformance/v1",
        redaction_policy_version="redaction/v1",
        producer=IdentityVersion(id="producer", version="1"),
        runner=IdentityVersion(id="runner", version="2"),
        applicability=_scope(),
        observations=(
            ImplementationObservation(
                id=f"observation-{suffix}",
                kind=ObservationKind.RESPONSE_STATUS,
                operation_ref="POST /charges",
                claim_identity="response:charges",
                claim_path="/responses/200/status_code",
                expected="200",
                probe_digest="sha256:" + "c" * 64,
                fixture_digest="sha256:" + "d" * 64,
                lineage=ObservationLineage.INDEPENDENT,
                replay=ReplayRecipe(executor="pytest", steps=("run charge probe",)),
                attempts=(
                    ObservationAttempt(
                        id=f"attempt-{suffix}",
                        observed_at=_NOW,
                        outcome=ObservationOutcome.API_RESPONSE,
                        observed=observed,
                    ),
                ),
                evidence=(
                    ObservationEvidence(
                        fragment_id=f"response-{suffix}",
                        digest=_evidence_digest(),
                        media_type="application/json",
                        size_bytes=42,
                        sanitized_facts=_sanitized_facts(),
                    ),
                ),
            ),
        ),
    )


def _assessment(
    bundle: ObservationBundle, *, assessment_id: str = "assessment-1"
) -> FeedbackAssessment:
    observation = bundle.observations[0]
    relationship = ConformanceRelationship(
        observation_id=observation.id,
        claim_identity="response:charges",
        claim_path="/responses/200/status_code",
        operation_ref="POST /charges",
        kind=ObservationKind.RESPONSE_STATUS,
        claim_kind="operation",
        relationship=ConformanceRelationshipType.CONTRADICTS,
        normative_value="200",
        observed_value=observation.attempts[0].observed,
        evidence_refs=(observation.evidence[0].fragment_id,),
        reason="observed behavior differs",
    )
    return FeedbackAssessment(
        assessment_id=assessment_id,
        base=bundle.base,
        normative_release_digest=normative_release_digest(
            NormativeRelease(base=bundle.base, contract=_contract())
        ),
        observation_bundle_id=bundle.bundle_id,
        observation_bundle_digest=canonical_digest(bundle),
        policy_version=bundle.policy_version,
        redaction_policy_version=bundle.redaction_policy_version,
        producer=bundle.producer,
        runner=bundle.runner,
        applicability=bundle.applicability,
        relationships=(relationship,),
        route=FeedbackRoute.AMENDMENT_PROPOSAL,
        coverage=ConformanceCoverage(
            material_claim_count=1,
            assessed_claim_count=1,
            confirmed_claim_count=0,
            conformance_ratio=0,
            suite_version=bundle.runner.version,
        ),
        open_discrepancy_count=1,
        fully_verified=BoundedVerification(
            verified=False,
            applicability=bundle.applicability,
            as_of=bundle.applicability.observed_until,
            suite_version=bundle.runner.version,
            reasons=("contradiction",),
        ),
    )


def _setup_base(project_root: Path) -> None:
    register.register_docset(
        project_root,
        Docset(
            docset_id="payments",
            title="Payments",
            provider="provider",
            product="payments",
            current_asset="payments-base",
        ),
    )
    _publish_normative_base(project_root, "payments-base", run_id="base-run")


def _publish_normative_base(
    project_root: Path,
    asset_id: str,
    *,
    run_id: str,
) -> None:
    artifacts = AssetArtifacts(
        openapi="artifacts/openapi.yaml",
        provenance="artifacts/provenance.json",
        validation="artifacts/validation/report.json",
    )
    asset = Asset(
        asset_id=asset_id,
        docset_id="payments",
        status=AssetStatus.APPROVED,
        run_id=run_id,
        generated_at=_NOW.isoformat(),
        validation=AssetValidation(ok=True),
        artifacts=artifacts,
        approved_at=_NOW.isoformat(),
        approved_by="normative-reviewer",
    )
    store.save_asset(project_root, asset)
    core_dir = (
        project_root
        / ".foundry/api/docsets/payments/assets"
        / asset_id
        / "artifacts/core"
    )
    core_dir.mkdir(parents=True)
    (core_dir / "contract.json").write_text(
        _contract().model_dump_json(indent=2), encoding="utf-8"
    )
    (core_dir / "evidence.json").write_text(
        EvidenceBundle(
            source_set_id="sources",
            source_set_version="1",
            artifacts=(),
            fragments=(),
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    (core_dir / "relationships.json").write_text("[]", encoding="utf-8")
    store.save_current(
        project_root,
        "payments",
        CurrentPointer(
            current_asset=asset.asset_id,
            status=asset.status,
            validation=asset.validation,
            generated_at=asset.generated_at,
            approved_at=asset.approved_at,
            artifacts=asset.artifacts,
        ),
    )


def test_persist_feedback_case_writes_immutable_inputs_without_changing_normative_current(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    normative_current = (
        tmp_path / ".foundry/api/docsets/payments/current.json"
    ).read_bytes()

    case = feedback.persist_feedback_case(tmp_path, "payments", bundle, assessment)

    assert case.case_id == "assessment-1"
    assert case.status == "candidate"
    assert case.bundle_digest == canonical_digest(bundle)
    assert case.assessment_digest == canonical_digest(assessment)
    case_dir = tmp_path / ".foundry/api/docsets/payments/feedback/cases/assessment-1"
    assert (case_dir / "case.json").is_file()
    assert (case_dir / "observation-bundle.json").read_bytes() == (
        bundle.model_dump_json(indent=2).encode()
    )
    assert (case_dir / "feedback-assessment.json").is_file()
    assert (
        tmp_path / ".foundry/api/docsets/payments/current.json"
    ).read_bytes() == normative_current

    with pytest.raises(FoundryInputError, match="already exists"):
        feedback.persist_feedback_case(tmp_path, "payments", bundle, assessment)


def test_feedback_review_rejects_raw_secret_fields(tmp_path: Path) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal).model_copy(
        update={"rationale": "Authorization: Bearer guessable-secret"}
    )

    with pytest.raises(FoundryInputError, match="secret"):
        feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)

    low_entropy = _decision(case, proposal).model_copy(
        update={"rationale": "client_secret=abc"}
    )
    with pytest.raises(FoundryInputError, match="secret"):
        feedback.record_feedback_review(
            tmp_path, "payments", case.case_id, low_entropy
        )

    for raw_pii in ("Customer phone 0912-345-678", "National ID A123456789"):
        pii = _decision(case, proposal).model_copy(
            update={"rationale": raw_pii}
        )
        with pytest.raises(FoundryInputError, match="PII"):
            feedback.record_feedback_review(
                tmp_path, "payments", case.case_id, pii
            )

    assert not (
        tmp_path
        / ".foundry/api/docsets/payments/feedback/cases/assessment-1/review/decision.json"
    ).exists()


@pytest.mark.parametrize(
    "raw_pii",
    (
        "Replay with SSN 123-45-6789",
        "Replay with card 4111 1111 1111 1111",
        "Replay with passport number AB1234567",
    ),
)
def test_feedback_submit_rejects_free_text_pii(
    tmp_path: Path, raw_pii: str
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    observation = bundle.observations[0].model_copy(
        update={"replay": ReplayRecipe(executor="pytest", steps=(raw_pii,))}
    )
    bundle = bundle.model_copy(update={"observations": (observation,)})
    assessment = _assessment(bundle)

    with pytest.raises(FoundryInputError, match="PII"):
        feedback.persist_feedback_case(tmp_path, "payments", bundle, assessment)

    assert not (
        tmp_path / ".foundry/api/docsets/payments/feedback/cases/assessment-1"
    ).exists()


def _proposal(
    bundle: ObservationBundle,
    assessment: FeedbackAssessment,
    *,
    proposal_id: str = "proposal-1",
    created_at: datetime = _LATER,
) -> CompatibilityAmendmentProposal:
    relationship = assessment.relationships[0]
    return CompatibilityAmendmentProposal(
        proposal_id=proposal_id,
        base=bundle.base,
        normative_release_digest=assessment.normative_release_digest,
        assessment_id=assessment.assessment_id,
        assessment_digest=canonical_digest(assessment),
        observation_bundle_id=bundle.bundle_id,
        observation_bundle_digest=canonical_digest(bundle),
        policy_version=bundle.policy_version,
        redaction_policy_version=bundle.redaction_policy_version,
        target=MaterialClaimReference(
            claim_identity="response:charges",
            claim_path="/responses/200/status_code",
        ),
        claim_kind="operation",
        normative_value="200",
        proposed_value="201",
        scope=bundle.applicability,
        observation_ids=(relationship.observation_id,),
        observation_evidence_refs=relationship.evidence_refs,
        producer=bundle.producer,
        runner=bundle.runner,
        created_at=created_at,
    )


def _decision(
    case,
    proposal: CompatibilityAmendmentProposal,
    *,
    approver: str = "reviewer",
    proposal_digest: str | None = None,
    decided_at: datetime = _LATER,
    expires_at: datetime | None = None,
) -> FeedbackReviewDecision:
    return FeedbackReviewDecision(
        case_id=case.case_id,
        disposition="approved",
        approved_by=IdentityVersion(id=approver, version="1"),
        decided_at=decided_at,
        expires_at=expires_at or decided_at + timedelta(days=30),
        base_asset_id=case.base_asset_id,
        base_contract_digest=case.base_contract_digest,
        bundle_id=case.bundle_id,
        bundle_digest=case.bundle_digest,
        redaction_policy_version=case.redaction_policy_version,
        policy_version=case.policy_version,
        assessment_id=case.assessment_id,
        assessment_digest=case.assessment_digest,
        proposal_id=proposal.proposal_id,
        proposal_digest=proposal_digest or canonical_digest(proposal),
    )


def _amendment(
    proposal: CompatibilityAmendmentProposal,
    decision: FeedbackReviewDecision,
    *,
    amendment_id: str = "amendment-1",
) -> CompatibilityAmendment:
    return CompatibilityAmendment(
        amendment_id=amendment_id,
        proposal=proposal,
        approval=AmendmentApproval(
            approval_id=f"approval-{amendment_id}",
            approved_by=decision.approved_by,
            approved_at=decision.decided_at,
            base_asset_id=decision.base_asset_id,
            assessment_id=decision.assessment_id,
            observation_bundle_id=decision.bundle_id,
            proposal_digest=decision.proposal_digest,
            assessment_digest=decision.assessment_digest,
            observation_bundle_digest=decision.bundle_digest,
            base_contract_digest=decision.base_contract_digest,
            policy_version=decision.policy_version,
            redaction_policy_version=decision.redaction_policy_version,
        ),
        expires_at=decision.expires_at,
    )


def _effective(
    amendment: CompatibilityAmendment,
    *,
    at: datetime | None = None,
) -> EffectiveContract:
    return ContractConformance().compose(
        _release(amendment),
        (amendment,),
        target=amendment.proposal.scope,
        now=at or amendment.approval.approved_at,
    )


def _release(amendment: CompatibilityAmendment) -> NormativeRelease:
    return NormativeRelease(base=amendment.proposal.base, contract=_contract())


def test_review_rejects_stale_digest_and_self_approval(tmp_path: Path) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )

    with pytest.raises(FoundryInputError, match="stale"):
        feedback.record_feedback_review(
            tmp_path,
            "payments",
            case.case_id,
            _decision(case, proposal, proposal_digest="0" * 64),
        )
    with pytest.raises(FoundryInputError, match="producer or runner"):
        feedback.record_feedback_review(
            tmp_path,
            "payments",
            case.case_id,
            _decision(case, proposal, approver="producer"),
        )


def test_non_approval_review_records_corrective_route_without_proposal(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, None
    )
    decision = FeedbackReviewDecision(
        case_id=case.case_id,
        disposition="needs_evidence",
        approved_by=IdentityVersion(id="reviewer", version="1"),
        decided_at=_LATER,
        base_asset_id=case.base_asset_id,
        base_contract_digest=case.base_contract_digest,
        bundle_id=case.bundle_id,
        bundle_digest=case.bundle_digest,
        redaction_policy_version=case.redaction_policy_version,
        policy_version=case.policy_version,
        assessment_id=case.assessment_id,
        assessment_digest=case.assessment_digest,
        requested_route=FeedbackRoute.PROVIDER_CLARIFICATION,
        rationale="Request provider confirmation before any amendment.",
    )

    assert (
        feedback.record_feedback_review(
            tmp_path, "payments", case.case_id, decision
        )
        == decision
    )


def test_non_approval_review_cannot_precede_observation_completion(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, None
    )
    decision = FeedbackReviewDecision(
        case_id=case.case_id,
        disposition="needs_evidence",
        approved_by=IdentityVersion(id="reviewer", version="1"),
        decided_at=bundle.applicability.observed_until - timedelta(seconds=1),
        base_asset_id=case.base_asset_id,
        base_contract_digest=case.base_contract_digest,
        bundle_id=case.bundle_id,
        bundle_digest=case.bundle_digest,
        redaction_policy_version=case.redaction_policy_version,
        policy_version=case.policy_version,
        assessment_id=case.assessment_id,
        assessment_digest=case.assessment_digest,
        requested_route=FeedbackRoute.NEEDS_EVIDENCE,
    )

    with pytest.raises(FoundryInputError, match="observation completion"):
        feedback.record_feedback_review(
            tmp_path, "payments", case.case_id, decision
        )


def test_approval_persists_amendment_and_queries_exact_scoped_effective_asset(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    assert (
        feedback.record_feedback_review(
            tmp_path, "payments", case.case_id, decision
        )
        == decision
    )
    amendment = _amendment(proposal, decision)
    effective = _effective(amendment)

    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        effective,
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    assert (
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            effective,
            release=_release(amendment),
            composition_amendments=(amendment,),
        )
        == asset
    )

    loaded = query.load_current_effective_asset(
        tmp_path, "payments", _scope(), now=_LATER
    )
    assert loaded == asset
    assert loaded.base_asset_id == "payments-base"
    assert loaded.applied_amendment_ids == ("amendment-1",)
    assert loaded.stale_amendment_count == 0
    assert load_current_scope_amendments(
        tmp_path, "payments", _scope()
    ) == (amendment,)
    with pytest.raises(FoundryInputError, match="not yet approved"):
        query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=_NOW
        )
    case_dir = tmp_path / ".foundry/api/docsets/payments/feedback/cases/assessment-1"
    assert (case_dir / "approved-amendment.json").is_file()
    effective_path = query.resolve_current_effective_artifact(
        tmp_path, "payments", _scope(), "effective_contract", now=_LATER
    )
    assert (
        EffectiveContract.model_validate_json(
            effective_path.read_text(encoding="utf-8")
        )
        == effective
    )
    with pytest.raises(FoundryInputError, match="no current effective asset"):
        query.load_current_effective_asset(
            tmp_path,
            "payments",
            _scope().model_copy(update={"environment": "production"}),
            now=_LATER,
        )
    with pytest.raises(FoundryInputError, match="expired"):
        query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=decision.expires_at
        )
    normative_pointer = store.load_current(tmp_path, "payments")
    assert normative_pointer is not None
    store.save_current(
        tmp_path,
        "payments",
        normative_pointer.model_copy(update={"current_asset": "new-normative-base"}),
    )
    with pytest.raises(FoundryInputError, match="no longer normative current"):
        query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=_LATER
        )
    store.save_current(tmp_path, "payments", normative_pointer)
    pointer = store.load_effective_current(
        tmp_path, "payments", loaded.scope_digest
    )
    assert pointer is not None
    store.save_effective_current(
        tmp_path,
        "payments",
        loaded.scope_digest,
        pointer.model_copy(update={"stale_amendment_count": 1}),
    )
    with pytest.raises(FoundryInputError, match="digest is stale"):
        query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=_LATER
        )
