from __future__ import annotations

import os
from pathlib import Path

import pytest

from loop_apidoc.core.conformance import ContractConformance, canonical_digest
from loop_apidoc.core.governance import contract_digest
from loop_apidoc.domain.conformance import MaterialClaimReference, NormativeBaseBinding
from loop_apidoc.foundry import descriptor_namespace, feedback, governed, paths, store
from loop_apidoc.foundry.models import FoundryInputError, FoundryPublicationError
from tests.foundry.test_feedback import (
    _LATER,
    _amendment,
    _assessment,
    _bundle,
    _contract,
    _decision,
    _proposal,
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
    original_validate = descriptor_namespace.validate_directory_relative
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

    monkeypatch.setattr(
        descriptor_namespace, "validate_directory_relative", swap_before_validate
    )

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
    original_validate = governed.validate_governance_namespace
    swapped = False

    def swap_before_namespace_validation(*args: object, **kwargs: object) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            foundry_root.rename(moved_root)
            foundry_root.symlink_to(moved_root, target_is_directory=True)
        original_validate(*args, **kwargs)

    monkeypatch.setattr(
        governed, "validate_governance_namespace", swap_before_namespace_validation
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
    original_validate = governed.validate_governance_namespace
    swapped = False

    def swap_before_namespace_validation(*args: object, **kwargs: object) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            foundry_root.rename(moved_root)
            foundry_root.symlink_to(moved_root, target_is_directory=True)
        original_validate(*args, **kwargs)

    monkeypatch.setattr(
        governed, "validate_governance_namespace", swap_before_namespace_validation
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
