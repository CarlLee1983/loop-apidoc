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
