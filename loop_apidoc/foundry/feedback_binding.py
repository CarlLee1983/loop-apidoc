"""Immutable feedback-case loading and binding validation.

These read-side and deterministic checks are shared by case persistence,
review recording, and Effective-asset approval. Keeping them separate from the
publication workflow makes those three write paths smaller without weakening
their common binding rules.
"""

from __future__ import annotations

from pathlib import Path

from loop_apidoc.core.conformance import (
    ConformanceInputError,
    ContractConformance,
    canonical_digest,
)
from loop_apidoc.core.governance import contract_digest
from loop_apidoc.domain.conformance import (
    CompatibilityAmendment,
    CompatibilityAmendmentProposal,
    EffectiveContract,
    FeedbackAssessment,
    NormativeRelease,
    ObservationBundle,
)
from loop_apidoc.privacy import find_sensitive_value

from . import normative, store
from .models import FeedbackCase, FeedbackReviewDecision, FoundryInputError


def load_bound_feedback_case(
    project_root: Path,
    docset_id: str,
    case_id: str,
    *,
    require_proposal: bool,
    case_parent_fd: int | None = None,
) -> tuple[
    FeedbackCase,
    ObservationBundle,
    FeedbackAssessment,
    CompatibilityAmendmentProposal | None,
]:
    """Load one immutable case and verify every stored digest binding."""
    _safe_segment(docset_id, "docset id")
    _safe_segment(case_id, "case id")
    if case_parent_fd is None:
        with store.open_governed_docset(project_root, docset_id) as governed:
            with governed.open_directory(f"feedback/cases/{case_id}") as case_dir:
                result = load_bound_feedback_case(
                    project_root,
                    docset_id,
                    case_id,
                    require_proposal=require_proposal,
                    case_parent_fd=case_dir.descriptor,
                )
                case_dir.validate()
                governed.validate()
                return result
    case = store.read_model_relative(
        case_parent_fd,
        FeedbackCase,
        "case.json",
        "feedback case manifest",
    )
    assert case is not None
    if case.docset_id != docset_id or case.case_id != case_id:
        raise FoundryInputError("feedback case identity does not match its path")
    bundle = store.read_model_relative(
        case_parent_fd,
        ObservationBundle,
        "observation-bundle.json",
        "observation bundle",
    )
    assessment = store.read_model_relative(
        case_parent_fd,
        FeedbackAssessment,
        "feedback-assessment.json",
        "feedback assessment",
    )
    proposal = store.read_model_relative(
        case_parent_fd,
        CompatibilityAmendmentProposal,
        "amendment-proposal.json",
        "compatibility amendment proposal",
        optional=True,
    )
    assert bundle is not None
    assert assessment is not None
    if require_proposal and proposal is None:
        raise FoundryInputError("feedback case has no amendment proposal")
    if canonical_digest(bundle) != case.bundle_digest:
        raise FoundryInputError("feedback case observation bundle digest is stale")
    if canonical_digest(assessment) != case.assessment_digest:
        raise FoundryInputError("feedback case assessment digest is stale")
    actual_proposal_digest = (
        canonical_digest(proposal) if proposal is not None else None
    )
    if actual_proposal_digest != case.proposal_digest:
        raise FoundryInputError("feedback case amendment proposal digest is stale")
    return case, bundle, assessment, proposal


def load_governed_feedback_review_decision(
    project_root: Path,
    docset_id: str,
    case_id: str,
) -> FeedbackReviewDecision | None:
    """Load one case's immutable review through the pinned governance view."""
    _safe_segment(docset_id, "docset id")
    _safe_segment(case_id, "case id")
    with store.open_governed_docset(project_root, docset_id) as governed:
        with governed.open_directory(f"feedback/cases/{case_id}") as case_dir:
            case, bundle, assessment, proposal = load_bound_feedback_case(
                project_root,
                docset_id,
                case_id,
                require_proposal=False,
                case_parent_fd=case_dir.descriptor,
            )
            decision = store.read_model_relative(
                case_dir.descriptor,
                FeedbackReviewDecision,
                "review/decision.json",
                "feedback review decision",
                optional=True,
            )
            if decision is not None:
                _validate_decision(decision, case, bundle, assessment, proposal)
            case_dir.validate()
            governed.validate()
            return decision


def _load_bound_case(
    project_root: Path,
    docset_id: str,
    case_id: str,
    *,
    require_proposal: bool,
    case_parent_fd: int | None = None,
) -> tuple[
    FeedbackCase,
    ObservationBundle,
    FeedbackAssessment,
    CompatibilityAmendmentProposal | None,
]:
    """Compatibility wrapper for the internal pre-existing helper name."""
    return load_bound_feedback_case(
        project_root,
        docset_id,
        case_id,
        require_proposal=require_proposal,
        case_parent_fd=case_parent_fd,
    )


def _validate_decision(
    decision: FeedbackReviewDecision,
    case: FeedbackCase,
    bundle: ObservationBundle,
    assessment: FeedbackAssessment,
    proposal: CompatibilityAmendmentProposal | None,
) -> None:
    expected = {
        "case_id": case.case_id,
        "base_asset_id": case.base_asset_id,
        "base_contract_digest": case.base_contract_digest,
        "bundle_id": case.bundle_id,
        "bundle_digest": case.bundle_digest,
        "redaction_policy_version": case.redaction_policy_version,
        "policy_version": case.policy_version,
        "assessment_id": case.assessment_id,
        "assessment_digest": case.assessment_digest,
        "proposal_id": proposal.proposal_id if proposal is not None else None,
        "proposal_digest": case.proposal_digest,
    }
    for field, value in expected.items():
        if getattr(decision, field) != value:
            raise FoundryInputError(f"feedback review decision has stale {field}")
    if decision.decided_at < bundle.applicability.observed_until:
        raise FoundryInputError(
            "feedback review decision must not precede observation completion"
        )
    if proposal is not None and decision.decided_at < proposal.created_at:
        raise FoundryInputError(
            "feedback review decision must not precede proposal creation"
        )
    if decision.approved_by.id in {bundle.producer.id, bundle.runner.id}:
        raise FoundryInputError(
            "feedback approver cannot be the feedback producer or runner"
        )
    if assessment.producer != bundle.producer or assessment.runner != bundle.runner:
        raise FoundryInputError("feedback assessment actor binding is stale")


def _validate_proposal(
    proposal: CompatibilityAmendmentProposal,
    bundle: ObservationBundle,
    assessment: FeedbackAssessment,
) -> None:
    bindings = {
        "base": (proposal.base, bundle.base),
        "normative release digest": (
            proposal.normative_release_digest,
            assessment.normative_release_digest,
        ),
        "assessment id": (proposal.assessment_id, assessment.assessment_id),
        "assessment digest": (
            proposal.assessment_digest,
            canonical_digest(assessment),
        ),
        "observation bundle id": (
            proposal.observation_bundle_id,
            bundle.bundle_id,
        ),
        "observation bundle digest": (
            proposal.observation_bundle_digest,
            canonical_digest(bundle),
        ),
        "policy version": (proposal.policy_version, bundle.policy_version),
        "redaction policy version": (
            proposal.redaction_policy_version,
            bundle.redaction_policy_version,
        ),
        "scope": (proposal.scope, bundle.applicability),
        "producer": (proposal.producer, bundle.producer),
        "runner": (proposal.runner, bundle.runner),
    }
    for label, (actual, expected) in bindings.items():
        if actual != expected:
            raise FoundryInputError(
                f"compatibility amendment proposal has stale {label}"
            )


def _validate_deterministic_feedback(
    docset,
    release: NormativeRelease,
    bundle: ObservationBundle,
    assessment: FeedbackAssessment,
    proposal: CompatibilityAmendmentProposal | None,
) -> None:
    """Re-derive feedback before any governed case or release can be accepted."""
    try:
        expected_assessment = ContractConformance().assess(
            release,
            bundle,
            provider=docset.provider,
            product=docset.product,
        )
    except ConformanceInputError as exc:
        raise FoundryInputError(
            f"feedback assessment is not deterministic: {exc}"
        ) from exc
    if assessment != expected_assessment:
        raise FoundryInputError(
            "feedback assessment does not match deterministic reassessment"
        )
    if proposal is None:
        return
    try:
        expected_proposals = ContractConformance().propose(
            expected_assessment,
            now=proposal.created_at,
        )
    except ConformanceInputError as exc:
        raise FoundryInputError(
            f"feedback proposal is not deterministic: {exc}"
        ) from exc
    if proposal not in expected_proposals:
        raise FoundryInputError(
            "feedback proposal does not match deterministic proposal"
        )


def _validate_amendment(
    amendment: CompatibilityAmendment,
    case: FeedbackCase,
    proposal: CompatibilityAmendmentProposal,
    decision: FeedbackReviewDecision,
) -> None:
    approval = amendment.approval
    if amendment.proposal != proposal:
        raise FoundryInputError("approved amendment proposal is stale")
    bindings = {
        "base asset id": (approval.base_asset_id, case.base_asset_id),
        "assessment id": (approval.assessment_id, case.assessment_id),
        "observation bundle id": (approval.observation_bundle_id, case.bundle_id),
        "proposal digest": (approval.proposal_digest, decision.proposal_digest),
        "assessment digest": (approval.assessment_digest, case.assessment_digest),
        "observation bundle digest": (
            approval.observation_bundle_digest,
            case.bundle_digest,
        ),
        "base contract digest": (
            approval.base_contract_digest,
            case.base_contract_digest,
        ),
        "policy version": (approval.policy_version, case.policy_version),
        "redaction policy version": (
            approval.redaction_policy_version,
            case.redaction_policy_version,
        ),
        "approver": (approval.approved_by, decision.approved_by),
        "approval time": (approval.approved_at, decision.decided_at),
        "expiry": (amendment.expires_at, decision.expires_at),
    }
    for label, (actual, expected) in bindings.items():
        if actual != expected:
            raise FoundryInputError(f"approved amendment has stale {label}")


def _validate_effective_contract(
    effective: EffectiveContract,
    case: FeedbackCase,
    amendment: CompatibilityAmendment,
) -> None:
    if effective.base != amendment.proposal.base:
        raise FoundryInputError("effective contract base binding is stale")
    if effective.target != amendment.proposal.scope:
        raise FoundryInputError(
            "effective contract target scope does not match amendment"
        )
    if amendment.amendment_id not in effective.applied_amendment_ids:
        raise FoundryInputError("effective contract omits the approved amendment")
    if contract_digest(effective.normative_contract) != case.base_contract_digest:
        raise FoundryInputError("effective contract normative base digest is stale")


def _safe_segment(value: str, label: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise FoundryInputError(f"unsafe {label}: {value!r}")


def _reject_sensitive_values(value: object, *, path: str = "$") -> None:
    finding = find_sensitive_value(value, path=path)
    if finding is not None:
        kind, finding_path = finding
        raise FoundryInputError(f"raw {kind} is forbidden at {finding_path}")


def _load_governed_release(
    project_root: Path, docset_id: str, asset_id: str
) -> tuple[object, NormativeRelease]:
    try:
        return normative.load_approved_contract(project_root, docset_id, asset_id)
    except FoundryInputError as exc:
        raise FoundryInputError(
            f"approved normative base is invalid: {exc}"
        ) from exc
