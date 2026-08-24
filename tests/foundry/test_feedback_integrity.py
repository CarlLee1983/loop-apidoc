from __future__ import annotations

import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pytest

import loop_apidoc.foundry as foundry
from loop_apidoc.core.conformance import ContractConformance, canonical_digest
from loop_apidoc.core.governance import contract_digest
from loop_apidoc.domain.conformance import (
    CompatibilityAmendment,
    MaterialClaimReference,
    NormativeBaseBinding,
)
from loop_apidoc.feedback.loader import FeedbackInputError, load_current_scope_amendments
from loop_apidoc.foundry import (
    feedback,
    paths,
    query,
    store,
)
from loop_apidoc.foundry.models import (
    AssetStatus,
    EffectiveProvenance,
    FoundryInputError,
    FoundryPublicationError,
)
from tests.foundry.test_feedback import (
    _LATER,
    _amendment,
    _assessment,
    _bundle,
    _contract,
    _decision,
    _effective,
    _proposal,
    _publish_normative_base,
    _release,
    _scope,
    _setup_base,
)

def test_approval_rejects_unreviewed_extra_amendment(tmp_path: Path) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    amendment = _amendment(proposal, decision)
    rogue_proposal = proposal.model_copy(
        update={
            "proposal_id": "rogue-proposal",
            "target": MaterialClaimReference(
                claim_identity="response:charges", claim_path="/method"
            ),
            "normative_value": "POST",
            "proposed_value": "PATCH",
        }
    )
    rogue = amendment.model_copy(
        update={
            "amendment_id": "rogue-amendment",
            "proposal": rogue_proposal,
            "approval": amendment.approval.model_copy(
                update={
                    "approval_id": "rogue-approval",
                    "proposal_digest": canonical_digest(rogue_proposal),
                }
            ),
        }
    )
    forged_effective = ContractConformance().compose(
        _release(amendment),
        (amendment, rogue),
        target=_scope(),
        now=_LATER,
    )

    with pytest.raises(FoundryInputError, match="governed amendment lineage"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            forged_effective,
            release=_release(amendment),
            composition_amendments=(amendment, rogue),
        )


def test_submit_rejects_release_not_bound_to_approved_asset(tmp_path: Path) -> None:
    _setup_base(tmp_path)
    forged_contract = _contract().model_copy(
        update={
            "metadata": _contract().metadata.model_copy(
                update={"version": "forged"}
            )
        }
    )
    forged_base = NormativeBaseBinding(
        docset_id="payments",
        asset_id="payments-base",
        contract_digest=contract_digest(forged_contract),
    )
    bundle = _bundle().model_copy(update={"base": forged_base})
    assessment = _assessment(_bundle())

    with pytest.raises(FoundryInputError, match="approved normative base"):
        feedback.persist_feedback_case(
            tmp_path, "payments", bundle, assessment
        )


def test_persist_feedback_case_rejects_proposal_not_derived_from_assessment(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    forged = proposal.model_copy(
        update={"proposal_id": "forged-proposal", "proposed_value": "418"}
    )

    with pytest.raises(FoundryInputError, match="deterministic proposal"):
        feedback.persist_feedback_case(
            tmp_path, "payments", bundle, assessment, forged
        )

    assert not (
        tmp_path
        / ".foundry/api/docsets/payments/feedback/cases"
        / assessment.assessment_id
    ).exists()


def test_persist_feedback_case_rejects_assessment_not_derived_from_bundle(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    forged_relationship = assessment.relationships[0].model_copy(
        update={"observed_value": "418"}
    )
    forged = assessment.model_copy(
        update={
            "assessment_id": "forged-assessment",
            "relationships": (forged_relationship,),
        }
    )

    with pytest.raises(FoundryInputError, match="deterministic reassessment"):
        feedback.persist_feedback_case(tmp_path, "payments", bundle, forged)

    assert not (
        tmp_path
        / ".foundry/api/docsets/payments/feedback/cases"
        / forged.assessment_id
    ).exists()


def test_persist_feedback_case_rejects_docset_head_replacement_after_reassessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assessment metadata and the destination must remain one pinned snapshot."""
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    docset_path = paths.docset_manifest_path(tmp_path, "payments")
    original_validate = feedback._validate_deterministic_feedback
    replaced = False

    def validate_then_replace(*args: object, **kwargs: object) -> None:
        nonlocal replaced
        original_validate(*args, **kwargs)  # type: ignore[arg-type]
        replacement = tmp_path / "replacement-docset.json"
        docset = store.load_docset(tmp_path, "payments")
        replacement.write_text(
            docset.model_copy(update={"provider": "substituted-provider"}).model_dump_json(
                indent=2
            ),
            encoding="utf-8",
        )
        os.replace(replacement, docset_path)
        replaced = True

    monkeypatch.setattr(feedback, "_validate_deterministic_feedback", validate_then_replace)

    with pytest.raises(FoundryPublicationError, match="head identity changed"):
        feedback.persist_feedback_case(tmp_path, "payments", bundle, assessment)

    assert replaced
    assert not paths.feedback_case_dir(
        tmp_path, "payments", assessment.assessment_id
    ).exists()
    assert not (paths.docset_dir(tmp_path, "payments") / ".governance.lock").exists()
    assert not (tmp_path / ".foundry/api/.catalog-governance.lock").exists()


def test_review_rejects_symlinked_destination_directory(tmp_path: Path) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    external = tmp_path / "external-review"
    external.mkdir()
    review_dir = (
        tmp_path
        / ".foundry/api/docsets/payments/feedback/cases"
        / case.case_id
        / "review"
    )
    review_dir.symlink_to(external, target_is_directory=True)

    with pytest.raises(FoundryInputError, match="unsafe.*review"):
        feedback.record_feedback_review(
            tmp_path,
            "payments",
            case.case_id,
            _decision(case, proposal),
        )

    assert not (external / "decision.json").exists()


@pytest.mark.parametrize("ancestor", ("feedback", "feedback/cases"))
def test_submit_rejects_symlinked_feedback_ancestor_without_external_write(
    tmp_path: Path, ancestor: str
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    external = tmp_path / "external-feedback"
    external.mkdir()
    docset_dir = paths.docset_dir(tmp_path, "payments")
    link = docset_dir / ancestor
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(external, target_is_directory=True)

    with pytest.raises(FoundryInputError, match="unsafe.*feedback|governance ancestor"):
        feedback.persist_feedback_case(tmp_path, "payments", bundle, assessment)

    assert not any(external.iterdir())


def test_review_rejects_case_directory_swap_before_governed_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    case_dir = paths.feedback_case_dir(tmp_path, "payments", case.case_id)
    moved_case = tmp_path / "moved-case"
    original_validate = store.validate_directory_relative
    swapped = False

    def swap_before_validate(
        parent_fd: int, name: str, expected_fd: int
    ) -> None:
        nonlocal swapped
        if not swapped and name.endswith(case.case_id):
            swapped = True
            case_dir.rename(moved_case)
            case_dir.mkdir()
        original_validate(parent_fd, name, expected_fd)

    monkeypatch.setattr(store, "validate_directory_relative", swap_before_validate)

    with pytest.raises(FoundryPublicationError, match="namespace changed"):
        feedback.record_feedback_review(
            tmp_path, "payments", case.case_id, _decision(case, proposal)
        )

    assert not (moved_case / "review" / "decision.json").exists()
    assert not (case_dir / "review" / "decision.json").exists()


def test_submit_rejects_governed_ancestor_swap_to_external_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    foundry_root = tmp_path / ".foundry"
    moved_root = tmp_path.parent / f"{tmp_path.name}-moved-foundry"
    original_validate = store.validate_governance_namespace
    swapped = False

    def swap_before_namespace_validation(*args: object, **kwargs: object) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            foundry_root.rename(moved_root)
            foundry_root.symlink_to(moved_root, target_is_directory=True)
        original_validate(*args, **kwargs)

    monkeypatch.setattr(
        store, "validate_governance_namespace", swap_before_namespace_validation
    )

    try:
        with pytest.raises(FoundryPublicationError, match="namespace changed"):
            feedback.persist_feedback_case(tmp_path, "payments", bundle, assessment)

        assert not (
            moved_root
            / "api/docsets/payments/feedback/cases"
            / assessment.assessment_id
        ).exists()
    finally:
        if foundry_root.is_symlink():
            foundry_root.unlink()
        if moved_root.exists():
            moved_root.rename(foundry_root)


def test_review_rejects_governed_ancestor_swap_to_external_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    foundry_root = tmp_path / ".foundry"
    moved_root = tmp_path.parent / f"{tmp_path.name}-moved-foundry"
    original_validate = store.validate_governance_namespace
    swapped = False

    def swap_before_namespace_validation(*args: object, **kwargs: object) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            foundry_root.rename(moved_root)
            foundry_root.symlink_to(moved_root, target_is_directory=True)
        original_validate(*args, **kwargs)

    monkeypatch.setattr(
        store, "validate_governance_namespace", swap_before_namespace_validation
    )

    try:
        with pytest.raises(FoundryPublicationError, match="namespace changed"):
            feedback.record_feedback_review(
                tmp_path, "payments", case.case_id, _decision(case, proposal)
            )

        assert not (
            moved_root
            / "api/docsets/payments/feedback/cases"
            / case.case_id
            / "review/decision.json"
        ).exists()
    finally:
        if foundry_root.is_symlink():
            foundry_root.unlink()
        if moved_root.exists():
            moved_root.rename(foundry_root)


@pytest.mark.parametrize("replaced_root", ("scope", "asset"))
def test_effective_queries_reject_symlinked_governed_roots(
    tmp_path: Path, replaced_root: str
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
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    scope_root = (
        paths.docset_dir(tmp_path, "payments")
        / "effective/scopes"
        / asset.scope_digest
    )
    governed_root = (
        scope_root
        if replaced_root == "scope"
        else scope_root / "assets" / asset.effective_asset_id
    )
    external = tmp_path / f"external-{replaced_root}"
    governed_root.rename(external)
    governed_root.symlink_to(external, target_is_directory=True)

    for operation in (
        lambda: query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=_LATER
        ),
        lambda: query.load_bound_effective_asset(tmp_path, "payments", _scope()),
        lambda: query.load_bound_effective_amendments(
            tmp_path, "payments", _scope()
        ),
        lambda: query.read_current_effective_artifact(
            tmp_path,
            "payments",
            _scope(),
            "effective_contract",
            now=_LATER,
        ),
    ):
        with pytest.raises(FoundryInputError, match="unsafe"):
            operation()


@pytest.mark.parametrize("operation", ("current", "bound", "lineage"))
def test_effective_queries_bind_scope_before_reading_its_current_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """A pointer cannot authorize an equal-content scope substituted afterwards."""
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    scope_root = (
        paths.docset_dir(tmp_path, "payments")
        / "effective/scopes"
        / asset.scope_digest
    )
    foreign_root = tmp_path / f"foreign-scope-{operation}"
    moved_root = tmp_path / f"moved-scope-{operation}"
    shutil.copytree(scope_root, foreign_root)
    original_read_pointer = query._read_effective_pointer_from
    swapped = False

    def read_then_replace(*args: object, **kwargs: object):
        nonlocal swapped
        pointer = original_read_pointer(*args, **kwargs)  # type: ignore[arg-type]
        if not swapped:
            scope_root.rename(moved_root)
            foreign_root.rename(scope_root)
            swapped = True
        return pointer

    monkeypatch.setattr(query, "_read_effective_pointer_from", read_then_replace)

    with pytest.raises(FoundryInputError, match="effective governed path is unsafe"):
        if operation == "current":
            query.load_current_effective_asset(
                tmp_path, "payments", _scope(), now=_LATER
            )
        elif operation == "bound":
            query.load_bound_effective_asset(tmp_path, "payments", _scope())
        else:
            query.load_bound_effective_amendments(tmp_path, "payments", _scope())

    assert swapped


def test_effective_artifact_path_resolver_is_not_a_public_api() -> None:
    assert not hasattr(foundry, "resolve_current_effective_artifact")


def test_effective_artifact_reader_returns_verified_bytes_after_root_repoint(
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
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    resolved = query.read_current_effective_artifact(
        tmp_path,
        "payments",
        _scope(),
        "effective_contract",
        now=_LATER,
    )
    expected_bytes = resolved
    assert isinstance(resolved, bytes)
    assert resolved == query.read_current_effective_artifact(
        tmp_path,
        "payments",
        _scope(),
        "effective_contract",
        now=_LATER,
    )
    asset_root = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / asset.scope_digest
        / "assets"
        / asset.effective_asset_id
    )
    redirected_root = tmp_path.parent / f"{tmp_path.name}-redirected-effective"
    asset_root.rename(redirected_root)
    asset_root.symlink_to(redirected_root, target_is_directory=True)
    try:
        (redirected_root / asset.artifacts.effective_contract).write_bytes(
            b'{"attacker": true}'
        )

        assert resolved == expected_bytes
    finally:
        if asset_root.is_symlink():
            asset_root.unlink()
        redirected_root.rename(asset_root)


def test_effective_artifact_reader_returns_the_captured_bytes_after_path_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    artifact_path = (
        paths.docset_dir(tmp_path, "payments")
        / "effective/scopes"
        / asset.scope_digest
        / "assets"
        / asset.effective_asset_id
        / asset.artifacts.effective_contract
    )
    expected_bytes = artifact_path.read_bytes()
    original_read = query._read_bound_effective_from

    def capture_then_replace(*args: object, **kwargs: object):
        snapshot = original_read(*args, **kwargs)  # type: ignore[arg-type]
        artifact_path.write_bytes(b'{"attacker": true}')
        return snapshot

    monkeypatch.setattr(query, "_read_bound_effective_from", capture_then_replace)

    assert query.read_current_effective_artifact(
        tmp_path,
        "payments",
        _scope(),
        "effective_contract",
        now=_LATER,
    ) == expected_bytes


def test_direct_effective_current_writer_rejects_symlinked_scope(
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
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    pointer = store.load_effective_current(tmp_path, "payments", asset.scope_digest)
    assert pointer is not None
    scope_root = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / asset.scope_digest
    )
    external_scope = tmp_path.parent / f"{tmp_path.name}-external-scope"
    scope_root.rename(external_scope)
    scope_root.symlink_to(external_scope, target_is_directory=True)
    prior_current = (external_scope / "current.json").read_bytes()
    try:
        with pytest.raises(FoundryInputError, match="unsafe"):
            store.save_effective_current(
                tmp_path,
                "payments",
                asset.scope_digest,
                pointer.model_copy(update={"stale_amendment_count": 1}),
            )
        assert (external_scope / "current.json").read_bytes() == prior_current
    finally:
        if scope_root.is_symlink():
            scope_root.unlink()
        external_scope.rename(scope_root)


def test_direct_effective_current_writer_restores_head_after_scope_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    pointer = store.load_effective_current(tmp_path, "payments", asset.scope_digest)
    assert pointer is not None
    scope_root = (
        paths.docset_dir(tmp_path, "payments")
        / "effective/scopes"
        / asset.scope_digest
    )
    external_scope = tmp_path.parent / f"{tmp_path.name}-moved-scope"
    prior_current = (scope_root / "current.json").read_bytes()
    original_write = store._atomic_write_model_relative
    moved = False

    def write_then_replace_scope(
        parent_fd: int,
        name: str,
        model: object,
        *,
        prefix: str,
        outcome: store.HeadSnapshot | None = None,
    ) -> None:
        nonlocal moved
        original_write(
            parent_fd,
            name,
            model,
            prefix=prefix,
            outcome=outcome,
        )  # type: ignore[arg-type]
        if name == "current.json" and not moved:
            moved = True
            scope_root.rename(external_scope)
            scope_root.symlink_to(external_scope, target_is_directory=True)

    monkeypatch.setattr(store, "_atomic_write_model_relative", write_then_replace_scope)
    try:
        with pytest.raises(FoundryPublicationError, match="namespace changed"):
            store.save_effective_current(
                tmp_path,
                "payments",
                asset.scope_digest,
                pointer.model_copy(update={"stale_amendment_count": 1}),
            )
        assert moved
        assert (external_scope / "current.json").read_bytes() == prior_current
    finally:
        if scope_root.is_symlink():
            scope_root.unlink()
        if external_scope.exists():
            external_scope.rename(scope_root)


def test_feedback_case_post_publish_failure_removes_owned_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    original_publish = store.publish_asset

    def publish_then_fail(*args: object, **kwargs: object) -> object:
        original_publish(*args, **kwargs)
        raise OSError("injected post-publish failure")

    monkeypatch.setattr(store, "publish_asset", publish_then_fail)

    with pytest.raises(OSError, match="post-publish failure"):
        feedback.persist_feedback_case(
            tmp_path, "payments", bundle, assessment, proposal
        )

    assert not paths.feedback_case_dir(tmp_path, "payments", assessment.assessment_id).exists()
    assert not (paths.docset_dir(tmp_path, "payments") / ".governance.lock").exists()
    assert not (tmp_path / ".foundry/api/.catalog-governance.lock").exists()


def test_feedback_review_post_write_failure_removes_owned_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    original_write = store.write_once_model_relative

    def write_then_fail(*args: object, **kwargs: object) -> object:
        original_write(*args, **kwargs)
        raise OSError("injected post-write failure")

    monkeypatch.setattr(store, "write_once_model_relative", write_then_fail)

    with pytest.raises(OSError, match="post-write failure"):
        feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)

    decision_path = paths.feedback_case_dir(
        tmp_path, "payments", case.case_id
    ) / "review/decision.json"
    assert not decision_path.exists()
    assert not (paths.docset_dir(tmp_path, "payments") / ".governance.lock").exists()
    assert not (tmp_path / ".foundry/api/.catalog-governance.lock").exists()


def test_review_write_once_is_atomic_across_concurrent_writers(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decisions = tuple(
        _decision(case, proposal, approver=f"reviewer-{index}").model_copy(
            update={"rationale": f"review-{index}-" + "x" * 10_000_000}
        )
        for index in range(8)
    )
    barrier = Barrier(len(decisions))

    def record(decision):
        barrier.wait()
        try:
            feedback.record_feedback_review(
                tmp_path, "payments", case.case_id, decision
            )
        except FoundryInputError:
            return "rejected"
        except BaseException as exc:  # pragma: no cover - diagnostic failure result
            return type(exc).__name__
        return "written"

    with ThreadPoolExecutor(max_workers=len(decisions)) as executor:
        outcomes = tuple(executor.map(record, decisions))

    assert outcomes.count("written") == 1
    assert outcomes.count("rejected") == len(decisions) - 1


def test_current_rejects_tampered_amendment_artifact(tmp_path: Path) -> None:
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    amendment_path = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / asset.scope_digest
        / "assets"
        / asset.effective_asset_id
        / asset.artifacts.compatibility_amendment
    )
    stored = CompatibilityAmendment.model_validate_json(amendment_path.read_bytes())
    amendment_path.write_text(
        stored.model_copy(update={"amendment_id": "tampered"}).model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(FoundryInputError, match="amendment artifact digest is stale"):
        query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=_LATER
        )


@pytest.mark.parametrize("tamper", ["nonapproved_status", "unknown_metadata"])
def test_current_rejects_semantically_invalid_effective_asset(
    tmp_path: Path, tamper: str
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
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    asset_path = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / asset.scope_digest
        / "assets"
        / asset.effective_asset_id
        / "asset.json"
    )
    expected = "[Ee]xtra inputs are not permitted"
    if tamper == "nonapproved_status":
        candidate = asset.model_copy(update={"status": AssetStatus.CANDIDATE})
        asset_path.write_text(candidate.model_dump_json(), encoding="utf-8")
        pointer = store.load_effective_current(
            tmp_path, "payments", asset.scope_digest
        )
        assert pointer is not None
        store.save_effective_current(
            tmp_path,
            "payments",
            asset.scope_digest,
            pointer.model_copy(
                update={"effective_asset_digest": canonical_digest(candidate)}
            ),
        )
        expected = "not approved"
    else:
        payload = json.loads(asset_path.read_text(encoding="utf-8"))
        payload["untrusted_metadata"] = "secret-bearing attacker field"
        asset_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FoundryInputError, match=expected):
        query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=_LATER
        )


def test_current_rejects_rehashed_provenance_that_disagrees_with_approval(
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
    amendment = _amendment(proposal, decision)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    asset_dir = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / asset.scope_digest
        / "assets"
        / asset.effective_asset_id
    )
    provenance_path = asset_dir / asset.artifacts.provenance
    provenance = EffectiveProvenance.model_validate_json(
        provenance_path.read_bytes()
    ).model_copy(update={"approval_id": "forged-approval"})
    provenance_path.write_text(provenance.model_dump_json(), encoding="utf-8")
    forged_asset = asset.model_copy(
        update={"provenance_digest": canonical_digest(provenance)}
    )
    (asset_dir / "asset.json").write_text(
        forged_asset.model_dump_json(), encoding="utf-8"
    )
    pointer = store.load_effective_current(
        tmp_path, "payments", asset.scope_digest
    )
    assert pointer is not None
    store.save_effective_current(
        tmp_path,
        "payments",
        asset.scope_digest,
        pointer.model_copy(
            update={
                "effective_asset_digest": canonical_digest(forged_asset),
                "provenance_digest": forged_asset.provenance_digest,
            }
        ),
    )

    with pytest.raises(FoundryInputError, match="provenance approval lineage"):
        query.load_current_effective_asset(
            tmp_path, "payments", _scope(), now=_LATER
        )


def test_effective_release_supersedes_only_exact_scope_without_mutating_prior_bytes(
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
    amendment = _amendment(proposal, decision)
    first = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    first_dir = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / first.scope_digest
        / "assets"
        / first.effective_asset_id
    )
    prior_bytes = {
        path.relative_to(first_dir): path.read_bytes()
        for path in first_dir.rglob("*")
        if path.is_file()
    }

    second = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment, at=_LATER + timedelta(minutes=1)),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )

    assert second.supersedes == first.effective_asset_id
    assert (
        query.load_current_effective_asset(
            tmp_path,
            "payments",
            _scope(),
            now=_LATER + timedelta(minutes=1),
        ).effective_asset_id
        == second.effective_asset_id
    )
    assert {
        path.relative_to(first_dir): path.read_bytes()
        for path in first_dir.rglob("*")
        if path.is_file()
    } == prior_bytes
    assert store.load_current(tmp_path, "payments").current_asset == "payments-base"
    assert load_current_scope_amendments(
        tmp_path, "payments", _scope()
    ) == (amendment,)

    current = store.load_effective_current(
        tmp_path, "payments", second.scope_digest
    )
    assert current is not None
    store.save_effective_current(
        tmp_path,
        "payments",
        second.scope_digest,
        current.model_copy(update={"current_asset": first.effective_asset_id}),
    )
    forged_successor = _effective(
        amendment, at=_LATER + timedelta(minutes=2)
    )
    with pytest.raises(FoundryInputError, match="current asset digest is stale"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            forged_successor,
            release=_release(amendment),
            composition_amendments=(amendment,),
        )


def test_new_reviewed_amendment_can_replace_expired_current_lineage(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    first_bundle = _bundle()
    first_assessment = _assessment(first_bundle)
    first_proposal = _proposal(first_bundle, first_assessment)
    first_case = feedback.persist_feedback_case(
        tmp_path, "payments", first_bundle, first_assessment, first_proposal
    )
    first_decision = _decision(
        first_case,
        first_proposal,
        expires_at=_LATER + timedelta(minutes=1),
    )
    feedback.record_feedback_review(
        tmp_path, "payments", first_case.case_id, first_decision
    )
    first_amendment = _amendment(first_proposal, first_decision)
    first = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        first_case.case_id,
        first_amendment,
        _effective(first_amendment),
        release=_release(first_amendment),
        composition_amendments=(first_amendment,),
    )

    second_time = _LATER + timedelta(minutes=2)
    second_bundle = _bundle(suffix="2")
    second_assessment = _assessment(second_bundle)
    second_proposal = _proposal(
        second_bundle,
        second_assessment,
        created_at=second_time,
    )
    second_case = feedback.persist_feedback_case(
        tmp_path, "payments", second_bundle, second_assessment, second_proposal
    )
    second_decision = _decision(
        second_case, second_proposal, decided_at=second_time
    )
    feedback.record_feedback_review(
        tmp_path, "payments", second_case.case_id, second_decision
    )
    second_amendment = _amendment(
        second_proposal, second_decision, amendment_id="amendment-2"
    ).model_copy(update={"supersedes": first_amendment.amendment_id})
    effective = ContractConformance().compose(
        _release(second_amendment),
        (first_amendment, second_amendment),
        target=_scope(),
        now=second_time,
    )

    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        second_case.case_id,
        second_amendment,
        effective,
        release=_release(second_amendment),
        composition_amendments=(first_amendment, second_amendment),
    )

    assert asset.applied_amendment_ids == ("amendment-2",)
    assert asset.open_discrepancy_count > 0
    assert query.load_current_effective_asset(
        tmp_path, "payments", _scope(), now=second_time
    ) == asset

    first_asset_path = (
        tmp_path
        / ".foundry/api/docsets/payments/effective/scopes"
        / first.scope_digest
        / "assets"
        / first.effective_asset_id
        / "asset.json"
    )
    first_asset_payload = json.loads(first_asset_path.read_text(encoding="utf-8"))
    first_asset_payload["approved_by"] = {"id": "forged", "version": "1"}
    first_asset_path.write_text(
        json.dumps(first_asset_payload),
        encoding="utf-8",
    )
    with pytest.raises(FeedbackInputError, match="predecessor asset digest"):
        load_current_scope_amendments(tmp_path, "payments", _scope())
    with pytest.raises(FoundryInputError, match="predecessor asset digest"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            second_case.case_id,
            second_amendment,
            ContractConformance().compose(
                _release(second_amendment),
                (first_amendment, second_amendment),
                target=_scope(),
                now=second_time + timedelta(minutes=1),
            ),
            release=_release(second_amendment),
            composition_amendments=(first_amendment, second_amendment),
        )


def test_normative_drift_surfaces_stale_amendment_count_in_current_asset(
    tmp_path: Path,
) -> None:
    _setup_base(tmp_path)
    first_bundle = _bundle()
    first_assessment = _assessment(first_bundle)
    first_proposal = _proposal(first_bundle, first_assessment)
    first_case = feedback.persist_feedback_case(
        tmp_path, "payments", first_bundle, first_assessment, first_proposal
    )
    first_decision = _decision(first_case, first_proposal)
    feedback.record_feedback_review(
        tmp_path, "payments", first_case.case_id, first_decision
    )
    first_amendment = _amendment(first_proposal, first_decision)
    feedback.approve_feedback_case(
        tmp_path,
        "payments",
        first_case.case_id,
        first_amendment,
        _effective(first_amendment),
        release=_release(first_amendment),
        composition_amendments=(first_amendment,),
    )

    _publish_normative_base(tmp_path, "payments-base-2", run_id="base-run-2")
    second_time = _LATER + timedelta(minutes=2)
    second_base = NormativeBaseBinding(
        docset_id="payments",
        asset_id="payments-base-2",
        contract_digest=contract_digest(_contract()),
    )
    second_bundle = _bundle(suffix="2").model_copy(
        update={"base": second_base}
    )
    second_assessment = _assessment(second_bundle)
    second_proposal = _proposal(
        second_bundle,
        second_assessment,
        created_at=second_time,
    )
    second_case = feedback.persist_feedback_case(
        tmp_path, "payments", second_bundle, second_assessment, second_proposal
    )
    second_decision = _decision(
        second_case, second_proposal, decided_at=second_time
    )
    feedback.record_feedback_review(
        tmp_path, "payments", second_case.case_id, second_decision
    )
    second_amendment = _amendment(
        second_proposal, second_decision, amendment_id="amendment-2"
    )
    second_release = _release(second_amendment)
    effective = ContractConformance().compose(
        second_release,
        (first_amendment, second_amendment),
        target=_scope(),
        now=second_time,
    )

    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        second_case.case_id,
        second_amendment,
        effective,
        release=second_release,
        composition_amendments=(first_amendment, second_amendment),
    )

    assert effective.stale_amendment_ids == ("amendment-1",)
    assert asset.stale_amendment_count == 1
    assert query.load_current_effective_asset(
        tmp_path, "payments", _scope(), now=second_time
    ).stale_amendment_count == 1


def test_effective_approval_rejects_a_preplanted_equal_case_amendment(
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
    amendment = _amendment(proposal, decision)
    approved_amendment = (
        paths.feedback_case_dir(tmp_path, "payments", case.case_id)
        / "approved-amendment.json"
    )
    approved_amendment.write_text(
        amendment.model_dump_json(indent=2),
        encoding="utf-8",
    )

    with pytest.raises(FoundryInputError, match="already exists"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            _effective(amendment),
            release=_release(amendment),
            composition_amendments=(amendment,),
        )

    assert not paths.effective_current_path(
        tmp_path,
        "payments",
        canonical_digest(_scope()),
    ).exists()


def test_effective_approval_authorizes_only_through_its_pinned_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approval must not reopen a replaceable namespace after its lock is held."""
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path, "payments", bundle, assessment, proposal
    )
    decision = _decision(case, proposal)
    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    amendment = _amendment(proposal, decision)

    def reopened_path(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("approval reopened a canonical path")

    monkeypatch.setattr(query, "load_current_asset", reopened_path)
    monkeypatch.setattr(query, "load_bound_effective_amendments", reopened_path)
    monkeypatch.setattr(query, "load_bound_effective_asset", reopened_path)
    monkeypatch.setattr(store, "load_effective_current", reopened_path)

    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )

    assert asset.effective_asset_id == _effective(amendment).effective_contract_id


def test_effective_publication_failure_leaves_existing_scope_pointer_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    amendment = _amendment(proposal, decision)
    first = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        _effective(amendment),
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    failed_effective = _effective(amendment, at=_LATER + timedelta(minutes=1))

    def fail_pointer(*_args: object, **_kwargs: object) -> None:
        raise OSError("scope pointer write failed")

    monkeypatch.setattr(store, "save_effective_current", fail_pointer)
    with pytest.raises(OSError, match="scope pointer write failed"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            failed_effective,
            release=_release(amendment),
            composition_amendments=(amendment,),
        )

    assert (
        query.load_current_effective_asset(
            tmp_path,
            "payments",
            _scope(),
            now=_LATER + timedelta(minutes=1),
        ).effective_asset_id
        == first.effective_asset_id
    )
    monkeypatch.undo()

    recovered = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        failed_effective,
        release=_release(amendment),
        composition_amendments=(amendment,),
    )

    assert recovered.effective_asset_id == failed_effective.effective_contract_id
    assert (
        query.load_current_effective_asset(
            tmp_path,
            "payments",
            _scope(),
            now=_LATER + timedelta(minutes=1),
        ).effective_asset_id
        == failed_effective.effective_contract_id
    )
