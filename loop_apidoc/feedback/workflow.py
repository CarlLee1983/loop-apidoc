from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loop_apidoc.core.conformance import ContractConformance, canonical_digest
from loop_apidoc.domain.conformance import (
    ApplicabilityEnvelope,
    AmendmentApproval,
    CompatibilityAmendment,
    CompatibilityAmendmentProposal,
    EffectiveContract,
    FeedbackAssessment,
    FeedbackRoute,
    IdentityVersion,
    NormativeRelease,
    ObservationBundle,
)
from loop_apidoc.feedback.erratum import (
    ProviderErratumHandoff,
    ProviderErratumMetadata,
    build_provider_erratum_handoff,
)
from loop_apidoc.feedback.errors import FeedbackInputError
from loop_apidoc.feedback.identifiers import require_safe_identifier
from loop_apidoc.foundry import feedback as foundry_feedback
from loop_apidoc.foundry import normative as foundry_normative
from loop_apidoc.foundry import query as foundry_query
from loop_apidoc.foundry.models import (
    Asset,
    Docset,
    EffectiveAsset,
    FeedbackCase,
    FeedbackReviewDecision,
    FoundryInputError,
)


@dataclass(frozen=True)
class AssessFeedbackCommand:
    project_root: Path
    docset_id: str
    asset_id: str
    bundle: ObservationBundle


@dataclass(frozen=True)
class AssessFeedbackResult:
    asset: Asset
    release: NormativeRelease
    bundle: ObservationBundle
    assessment: FeedbackAssessment


@dataclass(frozen=True)
class ProposeFeedbackCommand:
    assessment: FeedbackAssessment
    at: datetime


@dataclass(frozen=True)
class ProposeFeedbackResult:
    proposals: tuple[CompatibilityAmendmentProposal, ...]


@dataclass(frozen=True)
class SubmitFeedbackCommand:
    project_root: Path
    docset_id: str
    bundle: ObservationBundle
    assessment: FeedbackAssessment
    proposal: CompatibilityAmendmentProposal | None = None


@dataclass(frozen=True)
class SubmitFeedbackResult:
    case: FeedbackCase


@dataclass(frozen=True)
class ApproveFeedbackCommand:
    project_root: Path
    docset_id: str
    case_id: str
    approver: IdentityVersion
    decided_at: datetime
    expires_at: datetime
    rationale: str | None = None
    revalidation_triggers: tuple[str, ...] = ()
    supersedes_amendment: str | None = None


@dataclass(frozen=True)
class ApproveFeedbackResult:
    decision: FeedbackReviewDecision
    amendment: CompatibilityAmendment
    effective: EffectiveContract
    asset: EffectiveAsset


@dataclass(frozen=True)
class ReviewFeedbackCommand:
    project_root: Path
    docset_id: str
    case_id: str
    reviewer: IdentityVersion
    decided_at: datetime
    disposition: str
    requested_route: FeedbackRoute
    rationale: str | None = None


@dataclass(frozen=True)
class ReviewFeedbackResult:
    decision: FeedbackReviewDecision


@dataclass(frozen=True)
class ComposeFeedbackCommand:
    project_root: Path
    docset_id: str
    asset_id: str
    target: ApplicabilityEnvelope
    amendments: tuple[CompatibilityAmendment, ...]
    at: datetime


@dataclass(frozen=True)
class ComposeFeedbackResult:
    effective: EffectiveContract


@dataclass(frozen=True)
class CurrentFeedbackCommand:
    project_root: Path
    docset_id: str
    target: ApplicabilityEnvelope
    at: datetime


@dataclass(frozen=True)
class CurrentFeedbackResult:
    asset: EffectiveAsset


@dataclass(frozen=True)
class ProviderErratumCommand:
    metadata: ProviderErratumMetadata
    artifact_digest: str


@dataclass(frozen=True)
class ProviderErratumResult:
    handoff: ProviderErratumHandoff


class FeedbackWorkflow:
    """Application boundary for deterministic feedback and Foundry persistence."""

    def assess(self, command: AssessFeedbackCommand) -> AssessFeedbackResult:
        require_safe_identifier(command.docset_id, "docset id")
        require_safe_identifier(command.asset_id, "asset id")
        asset, docset, release = self._load_release(
            command.project_root,
            command.docset_id,
            command.asset_id,
        )
        if command.bundle.base.asset_id != asset.asset_id:
            raise FeedbackInputError(
                "observation bundle asset does not match the requested base release"
            )
        assessment = self._assess(release, docset, command.bundle)
        return AssessFeedbackResult(
            asset=asset,
            release=release,
            bundle=command.bundle,
            assessment=assessment,
        )

    def propose(self, command: ProposeFeedbackCommand) -> ProposeFeedbackResult:
        return ProposeFeedbackResult(
            proposals=ContractConformance().propose(command.assessment, now=command.at)
        )

    def submit(self, command: SubmitFeedbackCommand) -> SubmitFeedbackResult:
        require_safe_identifier(command.docset_id, "docset id")
        _, docset, release = self._load_release(
            command.project_root,
            command.docset_id,
            command.bundle.base.asset_id,
        )
        deterministic_assessment = self._assess(release, docset, command.bundle)
        if command.assessment != deterministic_assessment:
            raise FeedbackInputError(
                "submitted assessment does not match deterministic reassessment"
            )
        if command.proposal is not None:
            proposals = ContractConformance().propose(
                command.assessment,
                now=command.proposal.created_at,
            )
            if command.proposal not in proposals:
                raise FeedbackInputError(
                    "submitted amendment does not match deterministic proposal"
                )
        case = foundry_feedback.persist_feedback_case(
            command.project_root,
            command.docset_id,
            command.bundle,
            command.assessment,
            command.proposal,
        )
        return SubmitFeedbackResult(case=case)

    def review(self, command: ReviewFeedbackCommand) -> ReviewFeedbackResult:
        require_safe_identifier(command.docset_id, "docset id")
        require_safe_identifier(command.case_id, "case id")
        if command.disposition not in {"rejected", "needs_evidence"}:
            raise FeedbackInputError("disposition must be rejected or needs_evidence")
        case, bundle, assessment, proposal = foundry_feedback.load_bound_feedback_case(
            command.project_root,
            command.docset_id,
            command.case_id,
            require_proposal=False,
        )
        _, docset, release = self._load_release(
            command.project_root,
            command.docset_id,
            case.base_asset_id,
        )
        if assessment != self._assess(release, docset, bundle):
            raise FeedbackInputError(
                "persisted assessment does not match deterministic reassessment"
            )
        decision = FeedbackReviewDecision(
            case_id=case.case_id,
            disposition=command.disposition,
            approved_by=command.reviewer,
            decided_at=command.decided_at,
            base_asset_id=case.base_asset_id,
            base_contract_digest=case.base_contract_digest,
            bundle_id=case.bundle_id,
            bundle_digest=case.bundle_digest,
            redaction_policy_version=case.redaction_policy_version,
            policy_version=case.policy_version,
            assessment_id=case.assessment_id,
            assessment_digest=case.assessment_digest,
            proposal_id=proposal.proposal_id if proposal is not None else None,
            proposal_digest=case.proposal_digest,
            requested_route=command.requested_route,
            rationale=command.rationale,
        )
        foundry_feedback.record_feedback_review(
            command.project_root,
            command.docset_id,
            command.case_id,
            decision,
        )
        return ReviewFeedbackResult(decision=decision)

    def approve(self, command: ApproveFeedbackCommand) -> ApproveFeedbackResult:
        require_safe_identifier(command.docset_id, "docset id")
        require_safe_identifier(command.case_id, "case id")
        case, bundle, assessment, proposal = foundry_feedback.load_bound_feedback_case(
            command.project_root,
            command.docset_id,
            command.case_id,
            require_proposal=True,
        )
        assert proposal is not None
        _, docset, release = self._load_release(
            command.project_root,
            command.docset_id,
            case.base_asset_id,
        )
        deterministic_assessment = self._assess(release, docset, bundle)
        if assessment != deterministic_assessment:
            raise FeedbackInputError(
                "persisted assessment does not match deterministic reassessment"
            )
        if proposal not in ContractConformance().propose(
            assessment,
            now=proposal.created_at,
        ):
            raise FeedbackInputError(
                "persisted amendment does not match deterministic proposal"
            )
        decision = self._approval_decision(command, case, proposal)
        amendment = self._amendment(command, case, proposal)
        prior_amendments = self._current_scope_amendments(
            command.project_root,
            command.docset_id,
            proposal.scope,
        )
        prior_by_id = {prior.amendment_id: prior for prior in prior_amendments}
        if amendment.amendment_id in prior_by_id:
            if prior_by_id[amendment.amendment_id] != amendment:
                raise FeedbackInputError(
                    "current scope contains a different amendment with the same id"
                )
            composition_amendments = prior_amendments
        else:
            composition_amendments = (*prior_amendments, amendment)
        effective = ContractConformance().compose(
            release,
            composition_amendments,
            target=proposal.scope,
            now=command.decided_at,
        )
        if assessment.producer != bundle.producer or assessment.runner != bundle.runner:
            raise FeedbackInputError("feedback assessment actor binding is stale")
        existing_decision = foundry_feedback.load_governed_feedback_review_decision(
            command.project_root,
            command.docset_id,
            command.case_id,
        )
        if existing_decision is not None:
            if existing_decision != decision:
                raise FeedbackInputError(
                    "feedback review already exists with a different decision"
                )
        else:
            foundry_feedback.record_feedback_review(
                command.project_root,
                command.docset_id,
                command.case_id,
                decision,
            )
        asset = foundry_feedback.approve_feedback_case(
            command.project_root,
            command.docset_id,
            command.case_id,
            amendment,
            effective,
            release=release,
            composition_amendments=composition_amendments,
        )
        return ApproveFeedbackResult(
            decision=decision,
            amendment=amendment,
            effective=effective,
            asset=asset,
        )

    def compose(self, command: ComposeFeedbackCommand) -> ComposeFeedbackResult:
        require_safe_identifier(command.docset_id, "docset id")
        require_safe_identifier(command.asset_id, "asset id")
        _, _, release = self._load_release(
            command.project_root,
            command.docset_id,
            command.asset_id,
        )
        return ComposeFeedbackResult(
            effective=ContractConformance().compose(
                release,
                command.amendments,
                target=command.target,
                now=command.at,
            )
        )

    def current(self, command: CurrentFeedbackCommand) -> CurrentFeedbackResult:
        require_safe_identifier(command.docset_id, "docset id")
        return CurrentFeedbackResult(
            asset=foundry_query.load_current_effective_asset(
                command.project_root,
                command.docset_id,
                command.target,
                now=command.at,
            )
        )

    def provider_erratum(
        self,
        command: ProviderErratumCommand,
    ) -> ProviderErratumResult:
        return ProviderErratumResult(
            handoff=build_provider_erratum_handoff(
                command.metadata,
                command.artifact_digest,
            )
        )

    @staticmethod
    def _load_release(
        project_root: Path,
        docset_id: str,
        asset_id: str,
    ) -> tuple[Asset, Docset, NormativeRelease]:
        try:
            return foundry_normative.load_approved_contract_snapshot(
                project_root,
                docset_id,
                asset_id,
            )
        except FoundryInputError as exc:
            raise FeedbackInputError(str(exc)) from exc

    @staticmethod
    def _assess(
        release: NormativeRelease,
        docset: Docset,
        bundle: ObservationBundle,
    ) -> FeedbackAssessment:
        return ContractConformance().assess(
            release,
            bundle,
            provider=docset.provider,
            product=docset.product,
        )

    @staticmethod
    def _current_scope_amendments(
        project_root: Path,
        docset_id: str,
        target: ApplicabilityEnvelope,
    ) -> tuple[CompatibilityAmendment, ...]:
        try:
            return foundry_query.load_bound_effective_amendments(
                project_root,
                docset_id,
                target,
            )
        except FoundryInputError as exc:
            raise FeedbackInputError(str(exc)) from exc

    @staticmethod
    def _approval_decision(
        command: ApproveFeedbackCommand,
        case: FeedbackCase,
        proposal: CompatibilityAmendmentProposal,
    ) -> FeedbackReviewDecision:
        return FeedbackReviewDecision(
            case_id=case.case_id,
            disposition="approved",
            approved_by=command.approver,
            decided_at=command.decided_at,
            expires_at=command.expires_at,
            base_asset_id=case.base_asset_id,
            base_contract_digest=case.base_contract_digest,
            bundle_id=case.bundle_id,
            bundle_digest=case.bundle_digest,
            redaction_policy_version=case.redaction_policy_version,
            policy_version=case.policy_version,
            assessment_id=case.assessment_id,
            assessment_digest=case.assessment_digest,
            proposal_id=proposal.proposal_id,
            proposal_digest=case.proposal_digest,
            rationale=command.rationale,
        )

    @staticmethod
    def _amendment(
        command: ApproveFeedbackCommand,
        case: FeedbackCase,
        proposal: CompatibilityAmendmentProposal,
    ) -> CompatibilityAmendment:
        approval_id = "approval-" + canonical_digest(
            {
                "case_id": case.case_id,
                "proposal_digest": case.proposal_digest,
                "approved_by": command.approver,
                "approved_at": command.decided_at,
            }
        )[:20]
        revalidation_triggers = tuple(sorted(set(command.revalidation_triggers)))
        amendment_id = "amendment-" + canonical_digest(
            {
                "approval_id": approval_id,
                "proposal_digest": case.proposal_digest,
                "expires_at": command.expires_at,
                "revalidation_triggers": revalidation_triggers,
                "supersedes": command.supersedes_amendment,
            }
        )[:20]
        return CompatibilityAmendment(
            amendment_id=amendment_id,
            proposal=proposal,
            approval=AmendmentApproval(
                approval_id=approval_id,
                approved_by=command.approver,
                approved_at=command.decided_at,
                base_asset_id=case.base_asset_id,
                assessment_id=case.assessment_id,
                observation_bundle_id=case.bundle_id,
                proposal_digest=case.proposal_digest,
                assessment_digest=case.assessment_digest,
                observation_bundle_digest=case.bundle_digest,
                base_contract_digest=case.base_contract_digest,
                policy_version=case.policy_version,
                redaction_policy_version=case.redaction_policy_version,
            ),
            expires_at=command.expires_at,
            revalidation_triggers=revalidation_triggers,
            supersedes=command.supersedes_amendment,
        )
