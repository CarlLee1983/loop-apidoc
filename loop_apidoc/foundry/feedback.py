from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from pydantic import BaseModel

from loop_apidoc.core.conformance import ContractConformance, canonical_digest
from loop_apidoc.core.governance import contract_digest
from loop_apidoc.domain.conformance import (
    CompatibilityAmendment,
    CompatibilityAmendmentProposal,
    EffectiveContract,
    FeedbackAssessment,
    NormativeRelease,
    ObservationBundle,
    normative_release_digest,
)
from loop_apidoc.foundry import paths, query, store
from loop_apidoc.foundry.models import (
    AssetStatus,
    EffectiveAsset,
    EffectiveAssetArtifacts,
    EffectiveCurrentPointer,
    EffectiveProvenance,
    FeedbackCase,
    FeedbackReviewDecision,
    FoundryInputError,
)
from loop_apidoc.privacy import find_sensitive_value


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
    docset = store.load_docset(project_root, docset_id)
    if bundle.base.docset_id != docset.docset_id:
        raise FoundryInputError(
            "feedback bundle docset does not match the requested docset"
        )
    _, governed_release = _load_governed_release(
        project_root, docset_id, bundle.base.asset_id
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
    for value in (bundle, assessment, proposal):
        if value is not None:
            _reject_sensitive_values(value.model_dump(mode="json"))

    proposal_digest = canonical_digest(proposal) if proposal is not None else None
    if proposal is not None:
        if not isinstance(proposal, CompatibilityAmendmentProposal):
            raise FoundryInputError(
                "unsupported compatibility amendment proposal schema"
            )
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
    destination = paths.feedback_case_dir(project_root, docset_id, case.case_id)
    if destination.exists():
        raise FoundryInputError(f"feedback case already exists: {case.case_id}")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{case.case_id}-", dir=parent))
    try:
        _write_model(stage / "observation-bundle.json", bundle)
        _write_model(stage / "feedback-assessment.json", assessment)
        if proposal is not None:
            _write_model(stage / "amendment-proposal.json", proposal)
        _write_model(stage / "case.json", case)
        os.replace(stage, destination)
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return case


def record_feedback_review(
    project_root: Path,
    docset_id: str,
    case_id: str,
    decision: FeedbackReviewDecision,
) -> FeedbackReviewDecision:
    """Record one human decision after revalidating every digest binding."""
    case, bundle, assessment, proposal = _load_bound_case(
        project_root, docset_id, case_id, require_proposal=False
    )
    _validate_decision(decision, case, bundle, assessment, proposal)
    _reject_sensitive_values(decision.model_dump(mode="json"))
    case_dir = paths.feedback_case_dir(project_root, docset_id, case_id)
    _reject_symlink_components(project_root, case_dir, "feedback case")
    review_dir = case_dir / "review"
    _reject_symlink_components(project_root, review_dir, "feedback review")
    review_dir.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(project_root, review_dir, "feedback review")
    destination = review_dir / "decision.json"
    if destination.exists():
        if _read_model(
            FeedbackReviewDecision, destination, "feedback review decision"
        ) == decision:
            return decision
        raise FoundryInputError(f"feedback review already exists: {case_id}")
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".decision-", suffix=".tmp", dir=review_dir
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            stream.write(decision.model_dump_json(indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination, follow_symlinks=False)
    except FileExistsError as exc:
        existing = _read_model(
            FeedbackReviewDecision, destination, "feedback review decision"
        )
        if existing == decision:
            return decision
        raise FoundryInputError(f"feedback review already exists: {case_id}") from exc
    except BaseException:
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return decision


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
    """Publish an approved scoped release; the normative current stays untouched."""
    case, bundle, assessment, proposal = _load_bound_case(
        project_root, docset_id, case_id, require_proposal=True
    )
    assert proposal is not None
    decision_path = (
        paths.feedback_case_dir(project_root, docset_id, case_id)
        / "review"
        / "decision.json"
    )
    decision = _read_model(
        FeedbackReviewDecision, decision_path, "feedback review decision"
    )
    _validate_decision(decision, case, bundle, assessment, proposal)
    if decision.disposition != "approved":
        raise FoundryInputError(
            "feedback review decision does not approve an amendment"
        )
    _validate_amendment(amendment, case, proposal, decision)
    _validate_effective_contract(effective_contract, case, amendment)
    normative_current = store.load_current(project_root, docset_id)
    if normative_current is None or normative_current.current_asset != case.base_asset_id:
        raise FoundryInputError("feedback base is no longer the normative current asset")
    _, governed_release = _load_governed_release(
        project_root, docset_id, case.base_asset_id
    )
    if release != governed_release:
        raise FoundryInputError(
            "normative release does not match the approved base artifacts"
        )
    if release.base != proposal.base:
        raise FoundryInputError("normative release binding is stale")
    if normative_release_digest(release) != proposal.normative_release_digest:
        raise FoundryInputError("normative release evidence binding is stale")
    governed_amendments = query.load_bound_effective_amendments(
        project_root, docset_id, proposal.scope
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

    amendment_path = (
        paths.feedback_case_dir(project_root, docset_id, case_id)
        / "approved-amendment.json"
    )
    _write_once_or_verify(amendment_path, amendment)

    scope_digest = canonical_digest(effective_contract.target)
    _safe_segment(scope_digest, "scope digest")
    effective_asset_id = effective_contract.effective_contract_id
    _safe_segment(effective_asset_id, "effective asset id")
    current = store.load_effective_current(project_root, docset_id, scope_digest)
    predecessor_asset: EffectiveAsset | None = None
    if current is not None:
        if current.scope_digest != scope_digest or current.target != effective_contract.target:
            raise FoundryInputError("effective current pointer target scope is stale")
        _safe_segment(current.current_asset, "effective asset id")
        predecessor_asset, _ = query.load_bound_effective_asset(
            project_root, docset_id, effective_contract.target
        )
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
    destination = paths.effective_asset_dir(
        project_root, docset_id, scope_digest, effective_asset_id
    )
    if destination.exists():
        _verify_existing_effective_asset(
            destination,
            asset=asset,
            effective_contract=effective_contract,
            amendment=amendment,
            provenance=provenance,
        )
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=f".{effective_asset_id}-", dir=destination.parent)
        )
        try:
            artifact_dir = stage / "artifacts"
            artifact_dir.mkdir()
            _write_model(artifact_dir / "effective-contract.json", effective_contract)
            _write_model(artifact_dir / "compatibility-amendment.json", amendment)
            _write_model(
                artifact_dir / "provenance.json",
                provenance,
            )
            _write_model(stage / "asset.json", asset)
            os.replace(stage, destination)
        except BaseException:
            if stage.exists():
                shutil.rmtree(stage)
            raise

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
    )
    return asset


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


def _verify_existing_effective_asset(
    destination: Path,
    *,
    asset: EffectiveAsset,
    effective_contract: EffectiveContract,
    amendment: CompatibilityAmendment,
    provenance: EffectiveProvenance,
) -> None:
    expected = (
        (EffectiveAsset, destination / "asset.json", asset),
        (
            EffectiveContract,
            destination / "artifacts" / "effective-contract.json",
            effective_contract,
        ),
        (
            CompatibilityAmendment,
            destination / "artifacts" / "compatibility-amendment.json",
            amendment,
        ),
        (
            EffectiveProvenance,
            destination / "artifacts" / "provenance.json",
            provenance,
        ),
    )
    for model_type, path, value in expected:
        if _read_model(model_type, path, path.name) != value:
            raise FoundryInputError(
                f"immutable effective asset differs: {asset.effective_asset_id}"
            )


def _load_bound_case(
    project_root: Path,
    docset_id: str,
    case_id: str,
    *,
    require_proposal: bool,
) -> tuple[
    FeedbackCase,
    ObservationBundle,
    FeedbackAssessment,
    CompatibilityAmendmentProposal | None,
]:
    _safe_segment(docset_id, "docset id")
    _safe_segment(case_id, "case id")
    case = store.load_feedback_case(project_root, docset_id, case_id)
    if case.docset_id != docset_id or case.case_id != case_id:
        raise FoundryInputError("feedback case identity does not match its path")
    case_dir = paths.feedback_case_dir(project_root, docset_id, case_id)
    bundle = _read_model(
        ObservationBundle, case_dir / "observation-bundle.json", "observation bundle"
    )
    assessment = _read_model(
        FeedbackAssessment,
        case_dir / "feedback-assessment.json",
        "feedback assessment",
    )
    proposal_path = case_dir / "amendment-proposal.json"
    proposal = (
        _read_model(
            CompatibilityAmendmentProposal,
            proposal_path,
            "compatibility amendment proposal",
        )
        if proposal_path.is_file()
        else None
    )
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


def _read_model(model_type, path: Path, label: str):
    if not path.is_file() or path.is_symlink():
        raise FoundryInputError(f"required {label} is missing or unsafe")
    try:
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FoundryInputError(f"{label} is invalid: {str(exc)[:200]}") from exc


def _write_once_or_verify(path: Path, model: BaseModel) -> None:
    if path.exists():
        existing = _read_model(type(model), path, path.name)
        if existing != model:
            raise FoundryInputError(f"immutable persisted file differs: {path.name}")
        return
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        _write_model(temporary, model)
        if path.exists():
            raise FoundryInputError(
                f"immutable persisted file already exists: {path.name}"
            )
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _write_model(path: Path, model: BaseModel) -> None:
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _safe_segment(value: str, label: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise FoundryInputError(f"unsafe {label}: {value!r}")


def _reject_symlink_components(
    project_root: Path, path: Path, label: str
) -> None:
    root = project_root.resolve()
    try:
        relative = path.relative_to(project_root)
    except ValueError as exc:
        raise FoundryInputError(f"unsafe {label} path") from exc
    current = project_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise FoundryInputError(f"unsafe symlink in {label} path")
    if path.exists():
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise FoundryInputError(f"unsafe {label} path") from exc


def _reject_sensitive_values(value: object, *, path: str = "$") -> None:
    finding = find_sensitive_value(value, path=path)
    if finding is not None:
        kind, finding_path = finding
        raise FoundryInputError(f"raw {kind} is forbidden at {finding_path}")


def _load_governed_release(
    project_root: Path, docset_id: str, asset_id: str
):
    from loop_apidoc.feedback.loader import (
        FeedbackInputError,
        load_approved_contract,
    )

    try:
        return load_approved_contract(project_root, docset_id, asset_id)
    except FeedbackInputError as exc:
        raise FoundryInputError(
            f"approved normative base is invalid: {exc}"
        ) from exc
