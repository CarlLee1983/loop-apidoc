from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from loop_apidoc.core.conformance import canonical_digest
from loop_apidoc.foundry import feedback, paths, query, store
from loop_apidoc.foundry.models import FoundryInputError
from tests.foundry.test_feedback import (
    _LATER,
    _amendment,
    _assessment,
    _bundle,
    _decision,
    _effective,
    _proposal,
    _release,
    _scope,
    _setup_base,
)


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


def test_effective_approval_rejects_an_invalid_scoped_current_pointer(
    tmp_path: Path,
) -> None:
    """A corrupted scope head must not be treated as an absent predecessor."""
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
    current_path = paths.effective_current_path(
        tmp_path,
        "payments",
        canonical_digest(_scope()),
    )
    current_path.parent.mkdir(parents=True)
    current_path.write_text("not an effective pointer", encoding="utf-8")

    with pytest.raises(FoundryInputError, match="effective current pointer is invalid"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            _effective(amendment),
            release=_release(amendment),
            composition_amendments=(amendment,),
        )

    assert current_path.read_text(encoding="utf-8") == "not an effective pointer"


def test_effective_approval_rejects_a_stale_scope_pointer_without_replacing_it(
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
    effective = _effective(amendment)
    feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        effective,
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    pointer = store.load_effective_current(
        tmp_path, "payments", canonical_digest(_scope())
    )
    assert pointer is not None
    stale_pointer = pointer.model_copy(
        update={"target": _scope().model_copy(update={"environment": "production"})}
    )
    store.save_effective_current(
        tmp_path,
        "payments",
        canonical_digest(_scope()),
        stale_pointer,
    )

    with pytest.raises(FoundryInputError, match="pointer target scope is stale"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            effective,
            release=_release(amendment),
            composition_amendments=(amendment,),
        )

    assert store.load_effective_current(
        tmp_path, "payments", canonical_digest(_scope())
    ) == stale_pointer


def test_effective_approval_rejects_a_tampered_case_amendment_after_lineage_exists(
    tmp_path: Path,
) -> None:
    """Lineage may reuse an amendment only when the case's immutable leaf agrees."""
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
    effective = _effective(amendment)
    feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        effective,
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    amendment_path = (
        paths.feedback_case_dir(tmp_path, "payments", case.case_id)
        / "approved-amendment.json"
    )
    amendment_path.write_text(
        _amendment(proposal, decision, amendment_id="other-amendment").model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(FoundryInputError, match="approved amendment does not match"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            effective,
            release=_release(amendment),
            composition_amendments=(amendment,),
        )

    assert amendment_path.is_file()


def test_effective_approval_normalizes_a_stale_normative_head_to_input_failure(
    tmp_path: Path,
) -> None:
    """Approval exposes stale normative state as a safe user-correctable failure."""
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
    normative_current = store.load_current(tmp_path, "payments")
    assert normative_current is not None
    store.save_current(
        tmp_path,
        "payments",
        normative_current.model_copy(update={"asset_digest": "0" * 64}),
    )

    with pytest.raises(FoundryInputError, match="base is no longer the normative"):
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
        tmp_path, "payments", canonical_digest(_scope())
    ).exists()


def test_effective_asset_post_publish_failure_rolls_back_all_owned_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed immutable asset publication leaves no approval-visible residue."""
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
    effective = _effective(amendment)
    original_publish = store.publish_asset

    def publish_then_fail(*args: object, **kwargs: object) -> object:
        original_publish(*args, **kwargs)
        raise OSError("asset published but confirmation failed")

    monkeypatch.setattr(store, "publish_asset", publish_then_fail)
    with pytest.raises(OSError, match="asset published but confirmation failed"):
        feedback.approve_feedback_case(
            tmp_path,
            "payments",
            case.case_id,
            amendment,
            effective,
            release=_release(amendment),
            composition_amendments=(amendment,),
        )

    scope_digest = canonical_digest(_scope())
    assert not paths.effective_asset_dir(
        tmp_path, "payments", scope_digest, effective.effective_contract_id
    ).exists()
    assert not paths.effective_current_path(tmp_path, "payments", scope_digest).exists()
    assert not (
        paths.feedback_case_dir(tmp_path, "payments", case.case_id)
        / "approved-amendment.json"
    ).exists()

    monkeypatch.setattr(store, "publish_asset", original_publish)
    recovered = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        effective,
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    assert recovered.effective_asset_id == effective.effective_contract_id
