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
    CompatibilityAmendment,
    CompatibilityAmendmentProposal,
    EffectiveContract,
    FeedbackAssessment,
    FeedbackRoute,
    IdentityVersion,
    ImplementationObservation,
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
)
from loop_apidoc.domain.models import (
    ClaimStatus,
    ContractClaim,
    ContractMetadata,
    EvidenceBinding,
    GroundedApiContract,
    Operation,
    Response,
)
from loop_apidoc.domain.evidence import EvidenceBundle, EvidenceFragment
from loop_apidoc.feedback.loader import (
    FeedbackInputError,
    load_approved_contract,
    load_current_scope_amendments,
    load_feedback_assessment,
    load_observation_bundle,
    load_provider_erratum_inputs,
)
from loop_apidoc.feedback.erratum import ProviderErratumMetadata
from loop_apidoc.feedback.report import write_proposal_reports
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
from loop_apidoc.privacy import redact_sensitive

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
                evidence=(
                    EvidenceBinding(
                        fragment_id="normative-fragment",
                        claim_identity="response:charges",
                        claim_path="/responses/200/status_code",
                    ),
                ),
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


def _normative_fragments() -> tuple[EvidenceFragment, ...]:
    return (
        EvidenceFragment(
            id="normative-fragment",
            source_artifact_id="normative-source",
            locator={"kind": "whole_document"},
            fragment_digest="sha256:" + "0" * 64,
        ),
    )


def _assessment(
    bundle: ObservationBundle,
) -> FeedbackAssessment:
    return ContractConformance().assess(
        NormativeRelease(
            base=bundle.base,
            contract=_contract(),
            fragments=_normative_fragments(),
        ),
        bundle,
        provider=bundle.applicability.provider,
        product=bundle.applicability.product,
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
            fragments=_normative_fragments(),
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

    assert case.case_id == assessment.assessment_id
    assert case.status == "candidate"
    assert case.bundle_digest == canonical_digest(bundle)
    assert case.assessment_digest == canonical_digest(assessment)
    case_dir = (
        tmp_path
        / ".foundry/api/docsets/payments/feedback/cases"
        / case.case_id
    )
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


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ("base", "assessment base binding"),
        ("bundle_id", "assessment bundle identity"),
        ("bundle_digest", "assessment observation bundle digest"),
        ("applicability", "assessment applicability"),
        ("policy", "assessment policy"),
        ("redaction", "assessment redaction policy"),
        ("release", "assessment is not bound"),
    ),
)
def test_persist_feedback_case_rejects_stale_assessment_bindings(
    tmp_path: Path, change: str, message: str
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    replacements = {
        "base": {"base": bundle.base.model_copy(update={"asset_id": "other-base"})},
        "bundle_id": {"observation_bundle_id": "other-bundle"},
        "bundle_digest": {"observation_bundle_digest": "sha256:" + "0" * 64},
        "applicability": {
            "applicability": bundle.applicability.model_copy(
                update={"environment": "production"}
            )
        },
        "policy": {"policy_version": "conformance/v0"},
        "redaction": {"redaction_policy_version": "redaction/v0"},
        "release": {"normative_release_digest": "sha256:" + "0" * 64},
    }

    with pytest.raises(FoundryInputError, match=message):
        feedback.persist_feedback_case(
            tmp_path, "payments", bundle, assessment.model_copy(update=replacements[change])
        )


@pytest.mark.parametrize(
    ("bundle_update", "proposal", "message"),
    (
        (
            {"base": _bundle().base.model_copy(update={"docset_id": "other-docset"})},
            None,
            "bundle docset does not match",
        ),
        (
            {"base": _bundle().base.model_copy(update={"contract_digest": "0" * 64})},
            None,
            "not bound to the approved normative base",
        ),
        ({}, object(), "unsupported compatibility amendment proposal schema"),
    ),
)
def test_persist_feedback_case_rejects_unbound_bundle_or_unknown_proposal_schema(
    tmp_path: Path, bundle_update: dict[str, object], proposal: object, message: str
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle().model_copy(update=bundle_update)
    assessment = _assessment(_bundle())

    with pytest.raises(FoundryInputError, match=message):
        feedback.persist_feedback_case(
            tmp_path, "payments", bundle, assessment, proposal
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (b"{not json", "observation bundle is invalid"),
        (b"[]", "observation bundle is invalid"),
    ),
)
def test_load_observation_bundle_reports_safe_schema_errors(
    tmp_path: Path, payload: bytes, message: str
) -> None:
    path = tmp_path / "bundle.json"
    path.write_bytes(payload)

    with pytest.raises(FeedbackInputError, match=message):
        load_observation_bundle(path)


def test_load_observation_bundle_rejects_sensitive_persisted_value(tmp_path: Path) -> None:
    payload = _bundle().model_dump(mode="json")
    payload["observations"][0]["replay"]["steps"] = [
        "Authorization: Bearer guessable-secret"
    ]
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FeedbackInputError, match="raw secret"):
        load_observation_bundle(path)


def test_feedback_loaders_reject_unsafe_or_oversized_persisted_inputs(tmp_path: Path) -> None:
    target = tmp_path / "bundle.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "bundle-link.json"
    link.symlink_to(target)
    with pytest.raises(FeedbackInputError, match="must not be a symlink"):
        load_observation_bundle(link)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(FeedbackInputError, match="exceeds the"):
        load_observation_bundle(oversized)

    with pytest.raises(FeedbackInputError, match="feedback assessment is invalid"):
        load_feedback_assessment(target)


@pytest.mark.parametrize(
    ("artifact_name", "digest", "message"),
    (
        ("other.txt", "sha256:" + "0" * 64, "filename does not match"),
        ("erratum.txt", "sha256:" + "0" * 64, "digest mismatch"),
    ),
)
def test_provider_erratum_loader_binds_the_declared_artifact(
    tmp_path: Path, artifact_name: str, digest: str, message: str
) -> None:
    artifact = tmp_path / "erratum.txt"
    artifact.write_text("supplier correction", encoding="utf-8")
    metadata = ProviderErratumMetadata(
        schema_version="provider-erratum/v1",
        erratum_id="erratum-1",
        docset_id="payments",
        base_asset_id="payments-base",
        provider="provider",
        product="payments",
        artifact_name=artifact_name,
        artifact_digest=digest,
        issued_at=_NOW,
    )
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(metadata.model_dump_json(), encoding="utf-8")

    with pytest.raises(FeedbackInputError, match=message):
        load_provider_erratum_inputs(metadata_path, artifact)


def test_load_approved_contract_returns_immutable_release_from_governed_artifacts(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)

    asset, release = load_approved_contract(tmp_path, "payments", "payments-base")

    assert asset.asset_id == "payments-base"
    assert release.base.contract_digest == contract_digest(_contract())
    assert release.contract == _contract()
    assert release.fragments == _normative_fragments()


@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("missing_asset", "required file missing"),
        ("unapproved_asset", "requires an approved normative asset"),
        ("missing_approval", "missing approval lineage"),
        ("invalid_contract", "Canonical Contract artifact is invalid"),
        ("wrong_contract_identity", "Canonical Contract identity"),
        ("invalid_evidence", "Canonical evidence artifacts are invalid"),
        ("wrong_source_set", "evidence bundle does not match"),
        ("wrong_fragment_digest", "evidence fragment digest mismatch"),
    ),
)
def test_load_approved_contract_fails_closed_for_governed_artifact_corruption(
    tmp_path: Path, corruption: str, message: str
) -> None:
    _setup_base(tmp_path)
    asset_id = "payments-base"
    core_dir = (
        tmp_path
        / ".foundry/api/docsets/payments/assets"
        / asset_id
        / "artifacts/core"
    )
    contract_path = core_dir / "contract.json"
    evidence_path = core_dir / "evidence.json"

    if corruption == "missing_asset":
        asset_id = "missing-asset"
    elif corruption == "unapproved_asset":
        asset = store.load_asset(tmp_path, "payments", asset_id)
        store.save_asset(tmp_path, asset.model_copy(update={"status": AssetStatus.CANDIDATE}))
    elif corruption == "missing_approval":
        asset = store.load_asset(tmp_path, "payments", asset_id)
        store.save_asset(
            tmp_path,
            asset.model_copy(update={"approved_at": None, "approved_by": None}),
        )
    elif corruption == "invalid_contract":
        contract_path.write_text("{not json", encoding="utf-8")
    elif corruption == "wrong_contract_identity":
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
        payload["metadata"]["contract_id"] = "other-docset"
        contract_path.write_text(json.dumps(payload), encoding="utf-8")
    elif corruption == "invalid_evidence":
        evidence_path.write_text("{not json", encoding="utf-8")
    elif corruption == "wrong_source_set":
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        payload["source_set_id"] = "other-sources"
        evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    elif corruption == "wrong_fragment_digest":
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        payload["fragments"][0]["normalized_excerpt"] = "documented response"
        payload["fragments"][0]["fragment_digest"] = "sha256:" + "0" * 64
        evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FeedbackInputError, match=message):
        load_approved_contract(tmp_path, "payments", asset_id)


@pytest.mark.parametrize("unsafe_id", ("", ".", "..", "nested/docset"))
def test_load_approved_contract_rejects_unsafe_docset_identity(
    tmp_path: Path, unsafe_id: str
) -> None:
    with pytest.raises(FeedbackInputError, match="unsafe docset id"):
        load_approved_contract(tmp_path, unsafe_id, "payments-base")


@pytest.mark.parametrize(
    "sensitive_key",
    (
        "accessToken",
        "clientSecret",
        "setCookie",
        "token",
        "x-api-key",
        "accesstoken",
        "clientsecret",
    ),
)
def test_persist_feedback_case_rejects_conventional_sensitive_key_spellings(
    tmp_path: Path, sensitive_key: str
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    relationship = assessment.relationships[0].model_copy(
        update={"normative_value": {sensitive_key: "guessable-secret"}}
    )
    assessment = assessment.model_copy(update={"relationships": (relationship,)})

    with pytest.raises(FoundryInputError, match="secret"):
        feedback.persist_feedback_case(tmp_path, "payments", bundle, assessment)

    assert not (
        tmp_path
        / ".foundry/api/docsets/payments/feedback/cases"
        / assessment.assessment_id
    ).exists()


def test_sensitive_key_spellings_use_the_same_display_redaction_policy() -> None:
    sensitive = {
        key: "guessable-secret"
        for key in ("accessToken", "x-api-key", "accesstoken")
    }

    assert redact_sensitive(sensitive) == {
        key: "[redacted]" for key in sensitive
    }


def test_proposal_markdown_redacts_sensitive_values_without_changing_json(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment).model_copy(
        update={
            "normative_value": {"accessToken": "normative-secret"},
            "proposed_value": {"clientsecret": "proposed-secret"},
        }
    )

    output_dir = tmp_path / "proposal-report"
    write_proposal_reports((proposal,), output_dir)

    markdown = (output_dir / "amendment-proposals.md").read_text(encoding="utf-8")
    machine_json = (output_dir / "amendment-proposals.json").read_text(
        encoding="utf-8"
    )
    assert "[redacted]" in markdown
    assert "normative-secret" not in markdown
    assert "proposed-secret" not in markdown
    assert "normative-secret" in machine_json
    assert "proposed-secret" in machine_json


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
        / ".foundry/api/docsets/payments/feedback/cases"
        / case.case_id
        / "review/decision.json"
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
        tmp_path
        / ".foundry/api/docsets/payments/feedback/cases"
        / assessment.assessment_id
    ).exists()


def _proposal(
    bundle: ObservationBundle,
    assessment: FeedbackAssessment,
    *,
    created_at: datetime = _LATER,
) -> CompatibilityAmendmentProposal:
    proposals = ContractConformance().propose(assessment, now=created_at)
    assert len(proposals) == 1
    return proposals[0]


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
    return NormativeRelease(
        base=amendment.proposal.base,
        contract=_contract(),
        fragments=_normative_fragments(),
    )


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
    case_dir = (
        tmp_path
        / ".foundry/api/docsets/payments/feedback/cases"
        / case.case_id
    )
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


@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("non_approval_decision", "does not approve an amendment"),
        ("normative_current", "no longer the normative current"),
        ("release", "does not match the approved base artifacts"),
        ("composition", "composition does not match"),
        ("effective", "does not match deterministic composition"),
    ),
)
def test_approve_feedback_case_rejects_stale_governance_bindings(
    tmp_path: Path, corruption: str, message: str
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(tmp_path, "payments", bundle, assessment, proposal)
    decision = _decision(case, proposal)
    amendment = _amendment(proposal, decision)
    release = _release(amendment)
    effective = _effective(amendment)
    composition = (amendment,)

    if corruption == "non_approval_decision":
        decision = decision.model_copy(
            update={
                "disposition": "needs_evidence",
                "requested_route": FeedbackRoute.NEEDS_EVIDENCE,
            }
        )
    elif corruption == "normative_current":
        current = store.load_current(tmp_path, "payments")
        assert current is not None
        store.save_current(tmp_path, "payments", current.model_copy(update={"current_asset": "other-base"}))
    elif corruption == "release":
        release = release.model_copy(update={"fragments": ()})
    elif corruption == "composition":
        composition = ()
    elif corruption == "effective":
        effective = effective.model_copy(update={"open_discrepancy_count": 99})

    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    with pytest.raises(FoundryInputError, match=message):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            effective,
            release=release,
            composition_amendments=composition,
        )
