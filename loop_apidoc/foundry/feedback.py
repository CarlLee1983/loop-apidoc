from __future__ import annotations

import os
from pathlib import Path

from loop_apidoc.core.conformance import ContractConformance, canonical_digest
from loop_apidoc.domain.conformance import (
    CompatibilityAmendment,
    CompatibilityAmendmentProposal,
    EffectiveContract,
    FeedbackAssessment,
    NormativeRelease,
    ObservationBundle,
    normative_release_digest,
)
from . import normative, query, store
from .feedback_binding import (
    _load_bound_case,
    _reject_sensitive_values,
    _safe_segment,
    _validate_amendment,
    _validate_decision,
    _validate_deterministic_feedback,
    _validate_effective_contract,
    _validate_proposal,
)
from .feedback_binding import (  # noqa: F401 - public legacy feedback facade
    load_bound_feedback_case,
    load_governed_feedback_review_decision,
)
from .models import (
    AssetStatus,
    EffectiveAsset,
    EffectiveAssetArtifacts,
    EffectiveCurrentPointer,
    EffectiveProvenance,
    Docset,
    FeedbackCase,
    FeedbackReviewDecision,
    FoundryCurrentStaleError,
    FoundryInputError,
    FoundryPublicationError,
)


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
    docset_snapshot: store.HeadSnapshot | None = None
    case: FeedbackCase | None = None
    try:
        docset_snapshot, docset = store.read_head_model_snapshot_relative(
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
        store.validate_head_snapshot_relative(
            transaction.docset_fd,
            "docset.json",
            docset_snapshot,
        )
        cases_fd = store.ensure_directory_relative(
            transaction.docset_fd, "feedback/cases"
        )
        transaction.own_fd(cases_fd)
        if store.entry_identity_relative(cases_fd, case.case_id) is not None:
            raise FoundryInputError(f"feedback case already exists: {case.case_id}")
        stage_name, stage_fd, stage_identity = store.create_owned_directory_relative(
            cases_fd, prefix=f".{case.case_id}-"
        )
        store.write_model_relative(stage_fd, "observation-bundle.json", bundle)
        store.write_model_relative(stage_fd, "feedback-assessment.json", assessment)
        if proposal is not None:
            store.write_model_relative(stage_fd, "amendment-proposal.json", proposal)
        store.write_model_relative(stage_fd, "case.json", case)
        store.validate_head_snapshot_relative(
            transaction.docset_fd,
            "docset.json",
            docset_snapshot,
        )
        store.validate_directory_relative(
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
        store.validate_directory_relative(
            transaction.docset_fd, "feedback/cases", cases_fd
        )
        store.validate_head_snapshot_relative(
            transaction.docset_fd,
            "docset.json",
            docset_snapshot,
        )
        store.validate_governance_namespace(
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
                store.remove_owned_entry_relative(
                    cases_fd, case.case_id, publication.identity
                )
            elif published_identity is not None:
                store.remove_owned_entry_relative(
                    cases_fd, case.case_id, published_identity
                )
            elif stage_name is not None and stage_identity is not None:
                store.remove_owned_entry_relative(cases_fd, stage_name, stage_identity)
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
            store.remove_owned_entry_relative(cases_fd, case.case_id, published_identity)
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
    publication = store.ImmutableEntryPublication()
    try:
        try:
            cases_fd = store.open_directory_relative(
                transaction.docset_fd, "feedback/cases"
            )
        except OSError as exc:
            raise FoundryInputError("feedback case directory is unsafe") from exc
        transaction.own_fd(cases_fd)
        try:
            case_fd = store.open_directory_relative(cases_fd, case_id)
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
        store.validate_directory_relative(cases_fd, case_id, case_fd)
        review_fd = store.ensure_directory_relative(case_fd, "review")
        transaction.own_fd(review_fd)
        store.validate_directory_relative(case_fd, "review", review_fd)
        existed, identity = store.write_once_model_relative(
            review_fd, "decision.json", decision, outcome=publication
        )
        if not existed:
            created_identity = identity
        store.validate_directory_relative(cases_fd, case_id, case_fd)
        store.validate_directory_relative(case_fd, "review", review_fd)
        store.validate_governance_namespace(
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
                store.remove_owned_entry_relative(
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
                store.remove_owned_entry_relative(
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


def _approve_feedback_case_locked(
    project_root: Path,
    docset_id: str,
    case_id: str,
    amendment: CompatibilityAmendment,
    effective_contract: EffectiveContract,
    *,
    release: NormativeRelease,
    composition_amendments: tuple[CompatibilityAmendment, ...],
    root_parent_fd: int,
    api_parent_fd: int,
    docset_parent_fd: int,
    case_parent_fd: int,
    scope_parent_fd: int,
    effective_assets_fd: int,
    current_snapshot: store.HeadSnapshot,
    owned_outputs: list[tuple[int, str, tuple[int, int], str]],
) -> EffectiveAsset:
    """Publish an approved scoped release; the normative current stays untouched."""
    case, bundle, assessment, proposal = _load_bound_case(
        project_root,
        docset_id,
        case_id,
        require_proposal=True,
        case_parent_fd=case_parent_fd,
    )
    assert proposal is not None
    decision = store.read_model_relative(
        case_parent_fd,
        FeedbackReviewDecision,
        "review/decision.json",
        "feedback review decision",
    )
    assert decision is not None
    _validate_decision(decision, case, bundle, assessment, proposal)
    if decision.disposition != "approved":
        raise FoundryInputError(
            "feedback review decision does not approve an amendment"
        )
    _validate_amendment(amendment, case, proposal, decision)
    _validate_effective_contract(effective_contract, case, amendment)
    scope_digest = canonical_digest(effective_contract.target)
    _safe_segment(scope_digest, "scope digest")
    current = _effective_current_from_snapshot(current_snapshot)
    if current is not None and (
        current.scope_digest != scope_digest
        or current.target != effective_contract.target
    ):
        raise FoundryInputError("effective current pointer target scope is stale")
    predecessor_asset: EffectiveAsset | None = None
    try:
        with store.open_pinned_governed_docset(
            project_root,
            docset_id,
            root_fd=root_parent_fd,
            api_fd=api_parent_fd,
            docset_fd=docset_parent_fd,
        ) as governed:
            docset, _, normative_current = query._read_bound_current_from(
                governed,
                docset_id,
            )
            if normative_current.asset_id != case.base_asset_id:
                raise FoundryInputError(
                    "feedback base is no longer the normative current asset"
                )
            _, _, governed_release = normative.load_approved_contract_snapshot_relative(
                governed.docset_fd,
                docset_id,
                case.base_asset_id,
                docset=docset,
            )
            with governed.open_directory(
                f"effective/scopes/{scope_digest}"
            ) as scope:
                if not os.path.samestat(
                    os.fstat(scope.descriptor), os.fstat(scope_parent_fd)
                ):
                    raise FoundryPublicationError(
                        "governed transaction namespace changed during operation"
                    )
                if current is None:
                    governed_amendments = ()
                else:
                    predecessor = query._read_bound_effective_from(
                        scope,
                        docset_id,
                        effective_contract.target,
                        pointer=current,
                    )
                    predecessor_asset = predecessor.asset
                    governed_amendments = query._read_effective_lineage_from(
                        scope,
                        docset_id,
                        effective_contract.target,
                        predecessor,
                    )
                scope.validate()
            governed.validate()
    except FoundryCurrentStaleError as exc:
        raise FoundryInputError(
            "feedback base is no longer the normative current asset"
        ) from exc
    if release != governed_release:
        raise FoundryInputError(
            "normative release does not match the approved base artifacts"
        )
    if release.base != proposal.base:
        raise FoundryInputError("normative release binding is stale")
    if normative_release_digest(release) != proposal.normative_release_digest:
        raise FoundryInputError("normative release evidence binding is stale")
    _validate_deterministic_feedback(
        docset,
        release,
        bundle,
        assessment,
        proposal,
    )
    governed_by_id = {
        governed.amendment_id: governed for governed in governed_amendments
    }
    existing = governed_by_id.get(amendment.amendment_id)
    if existing is not None and existing != amendment:
        raise FoundryInputError(
            "governed amendment lineage contains a different amendment with the same id"
        )
    if existing is None:
        governed_by_id[amendment.amendment_id] = amendment
    expected_amendments = tuple(
        governed_by_id[key] for key in sorted(governed_by_id)
    )
    supplied_by_id = {
        supplied.amendment_id: supplied for supplied in composition_amendments
    }
    if (
        len(supplied_by_id) != len(composition_amendments)
        or supplied_by_id != governed_by_id
    ):
        raise FoundryInputError(
            "composition does not match the governed amendment lineage"
        )
    expected_effective = ContractConformance().compose(
        release,
        expected_amendments,
        target=proposal.scope,
        now=effective_contract.as_of,
    )
    if expected_effective != effective_contract:
        raise FoundryInputError(
            "effective contract does not match deterministic composition"
        )
    _reject_sensitive_values(amendment.model_dump(mode="json"))

    amendment_relative = f"feedback/cases/{case_id}/approved-amendment.json"
    store.validate_directory_relative(
        docset_parent_fd, f"feedback/cases/{case_id}", case_parent_fd
    )
    amendment_snapshot: store.HeadSnapshot
    if existing is not None:
        # A repeat Effective release may reuse this case's amendment only after
        # the same amendment is already present in the governed scope lineage.
        # An equal-content leaf alone is never a retry receipt: it could have
        # been pre-planted before this case was first approved.
        amendment_snapshot, stored_amendment = (
            store.read_head_model_snapshot_relative(
                case_parent_fd,
                CompatibilityAmendment,
                "approved-amendment.json",
                "approved amendment",
            )
        )
        if stored_amendment != amendment:
            raise FoundryInputError("approved amendment does not match this case")
        store.validate_head_snapshot_relative(
            case_parent_fd,
            "approved-amendment.json",
            amendment_snapshot,
        )
    else:
        amendment_publication = store.ImmutableEntryPublication()
        try:
            _created, identity = store.write_once_model_relative(
                case_parent_fd,
                "approved-amendment.json",
                amendment,
                outcome=amendment_publication,
            )
        except BaseException as primary:
            if amendment_publication.owned_entry:
                if amendment_publication.identity is None:
                    failure = FoundryPublicationError(
                        "approved amendment ownership is unavailable"
                    )
                    failure.recovery_required = True  # type: ignore[attr-defined]
                    raise failure from primary
                owned_outputs.append(
                    (
                        case_parent_fd,
                        "approved-amendment.json",
                        amendment_publication.identity,
                        amendment_relative,
                    )
                )
            raise
        owned_outputs.append(
            (case_parent_fd, "approved-amendment.json", identity, amendment_relative)
        )
        amendment_snapshot, stored_amendment = store.read_head_model_snapshot_relative(
            case_parent_fd,
            CompatibilityAmendment,
            "approved-amendment.json",
            "approved amendment",
        )
        if stored_amendment != amendment:
            raise FoundryPublicationError(
                "approved amendment changed during publication"
            )

    effective_asset_id = effective_contract.effective_contract_id
    _safe_segment(effective_asset_id, "effective asset id")
    if (
        existing is not None
        and current is not None
        and current.current_asset == effective_asset_id
    ):
        raise FoundryInputError(
            "governed immutable output already exists: effective asset"
        )
    if current is not None:
        _safe_segment(current.current_asset, "effective asset id")
    supersedes = (
        predecessor_asset.effective_asset_id
        if predecessor_asset is not None
        else None
    )
    supersedes_asset_digest = (
        canonical_digest(predecessor_asset)
        if predecessor_asset is not None
        else None
    )
    if supersedes == effective_asset_id:
        assert predecessor_asset is not None
        supersedes = predecessor_asset.supersedes
        supersedes_asset_digest = predecessor_asset.supersedes_asset_digest
    artifacts = EffectiveAssetArtifacts(
        effective_contract="artifacts/effective-contract.json",
        compatibility_amendment="artifacts/compatibility-amendment.json",
        provenance="artifacts/provenance.json",
    )
    effective_contract_digest = canonical_digest(effective_contract)
    amendment_digest = canonical_digest(amendment)
    provenance = _effective_provenance(case, effective_contract, amendment)
    asset = EffectiveAsset(
        effective_asset_id=effective_asset_id,
        docset_id=docset_id,
        scope_digest=scope_digest,
        target=effective_contract.target,
        status=AssetStatus.APPROVED,
        base_asset_id=case.base_asset_id,
        base_contract_digest=case.base_contract_digest,
        effective_contract_digest=effective_contract_digest,
        compatibility_amendment_digest=amendment_digest,
        provenance_digest=canonical_digest(provenance),
        applied_amendment_ids=effective_contract.applied_amendment_ids,
        supersedes=supersedes,
        supersedes_asset_digest=supersedes_asset_digest,
        approved_at=decision.decided_at,
        valid_until=effective_contract.valid_until,
        approved_by=decision.approved_by,
        open_discrepancy_count=effective_contract.open_discrepancy_count,
        stale_amendment_count=len(effective_contract.stale_amendment_ids),
        untested_material_claim_count=(
            effective_contract.untested_material_claim_count
        ),
        unresolved_contradiction_count=(
            effective_contract.unresolved_contradiction_count
        ),
        artifacts=artifacts,
    )
    assets_relative = f"effective/scopes/{scope_digest}/assets"
    destination_relative = f"{assets_relative}/{effective_asset_id}"
    destination_existed = (
        store.entry_identity_relative(effective_assets_fd, effective_asset_id)
        is not None
    )
    if destination_existed:
        _verify_existing_effective_asset(
            effective_assets_fd,
            effective_asset_id,
            asset=asset,
            effective_contract=effective_contract,
            amendment=amendment,
            provenance=provenance,
        )
    else:
        publication = store.AssetPublication()
        stage_name, stage_fd, stage_identity = store.create_owned_directory_relative(
            effective_assets_fd, prefix=f".{effective_asset_id}-"
        )
        try:
            artifact_fd = store.ensure_directory_relative(stage_fd, "artifacts")
            os.close(artifact_fd)
            store.write_model_relative(
                stage_fd, "artifacts/effective-contract.json", effective_contract
            )
            store.write_model_relative(
                stage_fd, "artifacts/compatibility-amendment.json", amendment
            )
            store.write_model_relative(
                stage_fd, "artifacts/provenance.json", provenance
            )
            store.write_model_relative(stage_fd, "asset.json", asset)
            store.validate_directory_relative(
                docset_parent_fd, assets_relative, effective_assets_fd
            )
            store.publish_asset(
                Path(stage_name),
                Path(effective_asset_id),
                outcome=publication,
                parent_fd=effective_assets_fd,
                expected_identity=stage_identity,
            )
        except BaseException:
            if publication.owned_root and publication.identity is not None:
                owned_outputs.append(
                    (
                        effective_assets_fd,
                        effective_asset_id,
                        publication.identity,
                        destination_relative,
                    )
                )
            store.remove_owned_entry_relative(
                effective_assets_fd, stage_name, stage_identity
            )
            raise
        finally:
            os.close(stage_fd)
        if publication.identity is not None:
            owned_outputs.append(
                (
                    effective_assets_fd,
                    effective_asset_id,
                    publication.identity,
                    destination_relative,
                )
            )

    store.validate_head_snapshot_relative(
        case_parent_fd,
        "approved-amendment.json",
        amendment_snapshot,
    )
    # This is the sole externally consumed promotion signal and therefore last.
    store.save_effective_current(
        project_root,
        docset_id,
        scope_digest,
        EffectiveCurrentPointer(
            current_asset=asset.effective_asset_id,
            effective_asset_digest=canonical_digest(asset),
            scope_digest=scope_digest,
            target=asset.target,
            base_asset_id=asset.base_asset_id,
            effective_contract_digest=asset.effective_contract_digest,
            compatibility_amendment_digest=(
                asset.compatibility_amendment_digest
            ),
            provenance_digest=asset.provenance_digest,
            approved_at=asset.approved_at,
            valid_until=asset.valid_until,
            open_discrepancy_count=asset.open_discrepancy_count,
            stale_amendment_count=asset.stale_amendment_count,
            untested_material_claim_count=asset.untested_material_claim_count,
            unresolved_contradiction_count=(
                asset.unresolved_contradiction_count
            ),
            artifacts=asset.artifacts,
        ),
        parent_fd=docset_parent_fd,
        scope_parent_fd=scope_parent_fd,
        outcome=current_snapshot,
    )
    store.validate_head_snapshot_relative(
        case_parent_fd,
        "approved-amendment.json",
        amendment_snapshot,
    )
    return asset


def approve_feedback_case(
    project_root: Path,
    docset_id: str,
    case_id: str,
    amendment: CompatibilityAmendment,
    effective_contract: EffectiveContract,
    *,
    release: NormativeRelease,
    composition_amendments: tuple[CompatibilityAmendment, ...],
) -> EffectiveAsset:
    """Publish feedback-derived state under the same docset governance lock."""
    _safe_segment(case_id, "case id")
    _safe_segment(effective_contract.effective_contract_id, "effective asset id")
    transaction = store.begin_governance_transaction(project_root, docset_id)
    scope_digest = canonical_digest(effective_contract.target)
    current_snapshot: store.HeadSnapshot | None = None
    preflight_complete = False
    owned_outputs: list[tuple[int, str, tuple[int, int], str]] = []
    scope_parent_fd = case_parent_fd = effective_assets_fd = -1
    try:
        scope_parent_fd = store.ensure_directory_relative(
            transaction.docset_fd, f"effective/scopes/{scope_digest}"
        )
        transaction.own_fd(scope_parent_fd)
        effective_assets_fd = store.ensure_directory_relative(
            scope_parent_fd, "assets"
        )
        transaction.own_fd(effective_assets_fd)
        case_parent_fd = store.open_directory_relative(
            transaction.docset_fd, f"feedback/cases/{case_id}"
        )
        transaction.own_fd(case_parent_fd)
        current_snapshot = store.read_head_snapshot_relative(
            scope_parent_fd, "current.json"
        )
        preflight_complete = True
        assert current_snapshot is not None
        asset = _approve_feedback_case_locked(
            transaction.project_root,
            docset_id,
            case_id,
            amendment,
            effective_contract,
            release=release,
            composition_amendments=composition_amendments,
            root_parent_fd=transaction.root_fd,
            api_parent_fd=transaction.api_fd,
            docset_parent_fd=transaction.docset_fd,
            case_parent_fd=case_parent_fd,
            scope_parent_fd=scope_parent_fd,
            effective_assets_fd=effective_assets_fd,
            current_snapshot=current_snapshot,
            owned_outputs=owned_outputs,
        )
        store.validate_directory_relative(
            transaction.docset_fd,
            f"feedback/cases/{case_id}",
            case_parent_fd,
        )
        store.validate_directory_relative(
            transaction.docset_fd,
            f"effective/scopes/{scope_digest}",
            scope_parent_fd,
        )
        store.validate_directory_relative(
            scope_parent_fd, "assets", effective_assets_fd
        )
        store.validate_governance_namespace(
            transaction.project_root,
            docset_id,
            root_fd=transaction.root_fd,
            api_fd=transaction.api_fd,
            docset_fd=transaction.docset_fd,
            assets_fd=transaction.assets_fd,
        )
    except BaseException as primary:
        if getattr(primary, "recovery_required", False):
            transaction.abandon()
            raise
        failures = (
            _rollback_feedback_outputs(
                transaction,
                current_parent_fd=scope_parent_fd,
                current_snapshot=current_snapshot,
                owned_outputs=owned_outputs,
            )
            if preflight_complete
            else []
        )
        if failures:
            transaction.abandon()
            details = "; ".join(
                f"{label}: {type(error).__name__}: {error}"
                for label, error in failures
            )
            raise FoundryPublicationError(
                f"feedback approval failed: {primary}; "
                f"rollback/cleanup failures: {details}"
            ) from primary
        try:
            transaction.close()
        except FoundryPublicationError:
            transaction.force_close()
        raise
    try:
        transaction.close()
    except FoundryPublicationError as lock_error:
        failures = _rollback_feedback_outputs(
            transaction,
            current_parent_fd=scope_parent_fd,
            current_snapshot=current_snapshot,
            owned_outputs=owned_outputs,
        )
        if failures:
            transaction.abandon()
            details = "; ".join(
                f"{label}: {type(error).__name__}: {error}"
                for label, error in failures
            )
            raise FoundryPublicationError(
                f"feedback lock cleanup failed: {lock_error}; "
                f"rollback/cleanup failures: {details}"
            ) from lock_error
        transaction.force_close()
        raise
    return asset


def _rollback_feedback_outputs(
    transaction: store.GovernanceTransaction,
    *,
    current_parent_fd: int,
    current_snapshot: store.HeadSnapshot | None,
    owned_outputs: list[tuple[int, str, tuple[int, int], str]],
) -> list[tuple[str, BaseException]]:
    failures: list[tuple[str, BaseException]] = []
    if current_snapshot is not None:
        try:
            store.restore_head_relative(
                current_parent_fd, "current.json", current_snapshot
            )
        except BaseException as exc:
            failures.append(("effective current", exc))
            return failures
    for parent_fd, name, identity, label in reversed(owned_outputs):
        try:
            store.remove_owned_entry_relative(parent_fd, name, identity)
        except BaseException as exc:
            failures.append((label, exc))
    return failures


def _effective_provenance(
    case: FeedbackCase,
    effective_contract: EffectiveContract,
    amendment: CompatibilityAmendment,
) -> EffectiveProvenance:
    return EffectiveProvenance(
        base_asset_id=case.base_asset_id,
        base_contract_digest=case.base_contract_digest,
        effective_contract_digest=canonical_digest(effective_contract),
        amendment_ids=effective_contract.applied_amendment_ids,
        approval_id=amendment.approval.approval_id,
        assessment_digest=case.assessment_digest,
        observation_bundle_digest=case.bundle_digest,
    )


def _effective_current_from_snapshot(
    snapshot: store.HeadSnapshot,
) -> EffectiveCurrentPointer | None:
    """Parse the one scope head captured before feedback approval started."""
    if snapshot.content is None:
        return None
    try:
        return EffectiveCurrentPointer.model_validate_json(snapshot.content)
    except ValueError as exc:
        raise FoundryInputError("effective current pointer is invalid") from exc


def _verify_existing_effective_asset(
    effective_assets_fd: int,
    effective_asset_id: str,
    *,
    asset: EffectiveAsset,
    effective_contract: EffectiveContract,
    amendment: CompatibilityAmendment,
    provenance: EffectiveProvenance,
) -> None:
    root_fd = store.open_directory_relative(effective_assets_fd, effective_asset_id)
    try:
        expected = (
            (EffectiveAsset, "asset.json", asset),
            (
                EffectiveContract,
                "artifacts/effective-contract.json",
                effective_contract,
            ),
            (
                CompatibilityAmendment,
                "artifacts/compatibility-amendment.json",
                amendment,
            ),
            (EffectiveProvenance, "artifacts/provenance.json", provenance),
        )
        for model_type, relative, value in expected:
            actual = store.read_model_relative(
                root_fd, model_type, relative, relative
            )
            if actual != value:
                raise FoundryInputError(
                    f"immutable effective asset differs: {asset.effective_asset_id}"
                )
    finally:
        os.close(root_fd)
