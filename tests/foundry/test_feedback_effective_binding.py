from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import loop_apidoc.foundry as foundry
from loop_apidoc.foundry import effective_binding, feedback, head_io, paths, query, store
from loop_apidoc.foundry.models import FoundryInputError, FoundryPublicationError
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
    original_read_pointer = effective_binding.read_effective_pointer
    swapped = False

    def read_then_replace(*args: object, **kwargs: object):
        nonlocal swapped
        pointer = original_read_pointer(*args, **kwargs)  # type: ignore[arg-type]
        if not swapped:
            scope_root.rename(moved_root)
            foreign_root.rename(scope_root)
            swapped = True
        return pointer

    monkeypatch.setattr(
        effective_binding,
        "read_effective_pointer",
        read_then_replace,
    )

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
    original_read = effective_binding.read_bound_effective

    def capture_then_replace(*args: object, **kwargs: object):
        snapshot = original_read(*args, **kwargs)  # type: ignore[arg-type]
        artifact_path.write_bytes(b'{"attacker": true}')
        return snapshot

    monkeypatch.setattr(
        effective_binding,
        "read_bound_effective",
        capture_then_replace,
    )

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
    original_write = head_io._atomic_write_model_relative
    moved = False

    def write_then_replace_scope(
        parent_fd: int,
        name: str,
        model: object,
        *,
        prefix: str,
        outcome: head_io.HeadSnapshot | None = None,
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

    monkeypatch.setattr(
        head_io, "_atomic_write_model_relative", write_then_replace_scope
    )
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
