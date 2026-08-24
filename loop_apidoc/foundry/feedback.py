from __future__ import annotations

import os
from pathlib import Path

from loop_apidoc.core.conformance import canonical_digest
from loop_apidoc.domain.conformance import (
    CompatibilityAmendmentProposal,
    FeedbackAssessment,
    ObservationBundle,
    normative_release_digest,
)
from . import (
    descriptor_io,
    descriptor_namespace,
    governed as governed_io,
    head_io,
    normative,
    store,
)
from .effective_approval import approve_feedback_case  # noqa: F401 - public facade
from .feedback_binding import (
    _load_bound_case,
    _reject_sensitive_values,
    _safe_segment,
    _validate_decision,
    _validate_deterministic_feedback,
    _validate_proposal,
)
from .feedback_binding import (  # noqa: F401 - public legacy feedback facade
    load_bound_feedback_case,
    load_governed_feedback_review_decision,
)
from .models import Docset, FeedbackCase, FeedbackReviewDecision, FoundryInputError, FoundryPublicationError


def persist_feedback_case(
    project_root: Path,
    docset_id: str,
    bundle: ObservationBundle,
    assessment: FeedbackAssessment,
    proposal: CompatibilityAmendmentProposal | None = None,
) -> FeedbackCase:
    """Persist one immutable, digest-bound case without changing governed pointers."""
    _safe_segment(docset_id, "docset id")
    _safe_segment(assessment.assessment_id, "assessment id")
    _safe_segment(bundle.base.asset_id, "asset id")
    if proposal is not None and not isinstance(proposal, CompatibilityAmendmentProposal):
        raise FoundryInputError(
            "unsupported compatibility amendment proposal schema"
        )
    for value in (bundle, assessment, proposal):
        if value is not None:
            _reject_sensitive_values(value.model_dump(mode="json"))

    transaction = store.begin_governance_transaction(project_root, docset_id)
    cases_fd = stage_fd = -1
    stage_name: str | None = None
    stage_identity: tuple[int, int] | None = None
    published_identity: tuple[int, int] | None = None
    publication = store.AssetPublication()
    docset_snapshot: head_io.HeadSnapshot | None = None
    case: FeedbackCase | None = None
    try:
        docset_snapshot, docset = head_io.read_head_model_snapshot_relative(
            transaction.docset_fd,
            Docset,
            "docset.json",
            "docset.json",
        )
        if bundle.base.docset_id != docset.docset_id:
            raise FoundryInputError(
                "feedback bundle docset does not match the requested docset"
            )
        _, _, governed_release = normative.load_approved_contract_snapshot_relative(
            transaction.docset_fd,
            docset_id,
            bundle.base.asset_id,
            docset=docset,
        )
        if governed_release.base != bundle.base:
            raise FoundryInputError(
                "feedback bundle is not bound to the approved normative base"
            )
        bundle_digest = canonical_digest(bundle)
        if assessment.base != bundle.base:
            raise FoundryInputError("assessment base binding does not match the bundle")
        if assessment.observation_bundle_id != bundle.bundle_id:
            raise FoundryInputError("assessment bundle identity does not match the bundle")
        if assessment.observation_bundle_digest != bundle_digest:
            raise FoundryInputError("assessment observation bundle digest is stale")
        if assessment.applicability != bundle.applicability:
            raise FoundryInputError("assessment applicability does not match the bundle")
        if assessment.policy_version != bundle.policy_version:
            raise FoundryInputError("assessment policy does not match the bundle")
        if assessment.redaction_policy_version != bundle.redaction_policy_version:
            raise FoundryInputError("assessment redaction policy does not match the bundle")
        if assessment.normative_release_digest != normative_release_digest(
            governed_release
        ):
            raise FoundryInputError(
                "assessment is not bound to the approved normative base release"
            )
        _validate_deterministic_feedback(
            docset,
            governed_release,
            bundle,
            assessment,
            proposal,
        )

        proposal_digest = canonical_digest(proposal) if proposal is not None else None
        if proposal is not None:
            _validate_proposal(proposal, bundle, assessment)
        case = FeedbackCase(
            case_id=assessment.assessment_id,
            docset_id=docset_id,
            base_asset_id=bundle.base.asset_id,
            base_contract_digest=bundle.base.contract_digest,
            bundle_id=bundle.bundle_id,
            bundle_digest=bundle_digest,
            assessment_id=assessment.assessment_id,
            assessment_digest=canonical_digest(assessment),
            proposal_digest=proposal_digest,
            policy_version=bundle.policy_version,
            redaction_policy_version=bundle.redaction_policy_version,
        )
        assert docset_snapshot is not None
        head_io.validate_head_snapshot_relative(
            transaction.docset_fd,
            "docset.json",
            docset_snapshot,
        )
        cases_fd = descriptor_namespace.ensure_directory_relative(
            transaction.docset_fd, "feedback/cases"
        )
        transaction.own_fd(cases_fd)
        if (
            descriptor_namespace.entry_identity_relative(cases_fd, case.case_id)
            is not None
        ):
            raise FoundryInputError(f"feedback case already exists: {case.case_id}")
        stage_name, stage_fd, stage_identity = (
            descriptor_namespace.create_owned_directory_relative(
                cases_fd, prefix=f".{case.case_id}-"
            )
        )
        descriptor_io.write_model_relative(
            stage_fd, "observation-bundle.json", bundle
        )
        descriptor_io.write_model_relative(
            stage_fd, "feedback-assessment.json", assessment
        )
        if proposal is not None:
            descriptor_io.write_model_relative(
                stage_fd, "amendment-proposal.json", proposal
            )
        descriptor_io.write_model_relative(stage_fd, "case.json", case)
        head_io.validate_head_snapshot_relative(
            transaction.docset_fd,
            "docset.json",
            docset_snapshot,
        )
        descriptor_namespace.validate_directory_relative(
            transaction.docset_fd, "feedback/cases", cases_fd
        )
        store.publish_asset(
            Path(stage_name),
            Path(case.case_id),
            outcome=publication,
            parent_fd=cases_fd,
            expected_identity=stage_identity,
        )
        assert publication.identity is not None
        published_identity = publication.identity
        descriptor_namespace.validate_directory_relative(
            transaction.docset_fd, "feedback/cases", cases_fd
        )
        head_io.validate_head_snapshot_relative(
            transaction.docset_fd,
            "docset.json",
            docset_snapshot,
        )
        governed_io.validate_governance_namespace(
            transaction.project_root,
            docset_id,
            root_fd=transaction.root_fd,
            api_fd=transaction.api_fd,
            docset_fd=transaction.docset_fd,
            assets_fd=transaction.assets_fd,
        )
    except BaseException as primary:
        try:
            if publication.owned_root:
                if publication.identity is None:
                    raise FoundryPublicationError(
                        "feedback case publication ownership is unavailable"
                    )
                descriptor_namespace.remove_owned_entry_relative(
                    cases_fd, case.case_id, publication.identity
                )
            elif published_identity is not None:
                descriptor_namespace.remove_owned_entry_relative(
                    cases_fd, case.case_id, published_identity
                )
            elif stage_name is not None and stage_identity is not None:
                descriptor_namespace.remove_owned_entry_relative(
                    cases_fd, stage_name, stage_identity
                )
        except BaseException as cleanup_error:
            transaction.abandon()
            raise FoundryPublicationError(
                "feedback case publication failed and recovery is required: "
                f"{cleanup_error}"
            ) from primary
        try:
            transaction.close()
        except FoundryPublicationError:
            transaction.force_close()
        raise
    finally:
        if stage_fd >= 0:
            os.close(stage_fd)
    try:
        transaction.close()
    except FoundryPublicationError as lock_error:
        try:
            assert published_identity is not None
            descriptor_namespace.remove_owned_entry_relative(
                cases_fd, case.case_id, published_identity
            )
        except BaseException as cleanup_error:
            transaction.abandon()
            raise FoundryPublicationError(
                "feedback case lock cleanup failed and recovery is required: "
                f"{cleanup_error}"
            ) from lock_error
        transaction.force_close()
        raise
    assert case is not None
    return case


def record_feedback_review(
    project_root: Path,
    docset_id: str,
    case_id: str,
    decision: FeedbackReviewDecision,
) -> FeedbackReviewDecision:
    """Record one human decision after revalidating every digest binding."""
    _safe_segment(case_id, "case id")
    transaction = store.begin_governance_transaction(project_root, docset_id)
    cases_fd = case_fd = review_fd = -1
    created_identity: tuple[int, int] | None = None
    publication = descriptor_io.ImmutableEntryPublication()
    try:
        try:
            cases_fd = descriptor_namespace.open_directory_relative(
                transaction.docset_fd, "feedback/cases"
            )
        except OSError as exc:
            raise FoundryInputError("feedback case directory is unsafe") from exc
        transaction.own_fd(cases_fd)
        try:
            case_fd = descriptor_namespace.open_directory_relative(cases_fd, case_id)
        except OSError as exc:
            raise FoundryInputError("feedback case directory is unsafe") from exc
        transaction.own_fd(case_fd)
        case, bundle, assessment, proposal = _load_bound_case(
            project_root,
            docset_id,
            case_id,
            require_proposal=False,
            case_parent_fd=case_fd,
        )
        _validate_decision(decision, case, bundle, assessment, proposal)
        _reject_sensitive_values(decision.model_dump(mode="json"))
        descriptor_namespace.validate_directory_relative(cases_fd, case_id, case_fd)
        review_fd = descriptor_namespace.ensure_directory_relative(case_fd, "review")
        transaction.own_fd(review_fd)
        descriptor_namespace.validate_directory_relative(case_fd, "review", review_fd)
        existed, identity = descriptor_io.write_once_model_relative(
            review_fd, "decision.json", decision, outcome=publication
        )
        if not existed:
            created_identity = identity
        descriptor_namespace.validate_directory_relative(cases_fd, case_id, case_fd)
        descriptor_namespace.validate_directory_relative(case_fd, "review", review_fd)
        governed_io.validate_governance_namespace(
            transaction.project_root,
            docset_id,
            root_fd=transaction.root_fd,
            api_fd=transaction.api_fd,
            docset_fd=transaction.docset_fd,
            assets_fd=transaction.assets_fd,
        )
    except BaseException:
        cleanup_identity = (
            publication.identity if publication.owned_entry else created_identity
        )
        if cleanup_identity is not None:
            try:
                descriptor_namespace.remove_owned_entry_relative(
                    review_fd, "decision.json", cleanup_identity
                )
            except BaseException:
                transaction.abandon()
                raise
        try:
            transaction.close()
        except FoundryPublicationError:
            transaction.force_close()
        raise
    try:
        transaction.close()
    except FoundryPublicationError as lock_error:
        try:
            if created_identity is not None:
                descriptor_namespace.remove_owned_entry_relative(
                    review_fd, "decision.json", created_identity
                )
        except BaseException as cleanup_error:
            transaction.abandon()
            raise FoundryPublicationError(
                "feedback review lock cleanup failed and recovery is required: "
                f"{cleanup_error}"
            ) from lock_error
        transaction.force_close()
        raise
    return decision
