from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from loop_apidoc.foundry import (
    descriptor_io,
    effective_approval,
    feedback,
    paths,
)
from loop_apidoc.foundry.models import FoundryPublicationError
from tests.foundry.test_feedback import (
    _amendment,
    _assessment,
    _bundle,
    _decision,
    _effective,
    _proposal,
    _release,
    _setup_base,
)


def test_existing_effective_asset_rejects_directory_swap_during_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A held immutable asset must still be its parent's named entry at commit."""
    _setup_base(tmp_path)
    bundle = _bundle()
    assessment = _assessment(bundle)
    proposal = _proposal(bundle, assessment)
    case = feedback.persist_feedback_case(
        tmp_path,
        "payments",
        bundle,
        assessment,
        proposal,
    )
    decision = _decision(case, proposal)
    feedback.record_feedback_review(tmp_path, "payments", case.case_id, decision)
    amendment = _amendment(proposal, decision)
    effective = _effective(amendment)
    asset = feedback.approve_feedback_case(
        tmp_path,
        "payments",
        case.case_id,
        amendment,
        effective,
        release=_release(amendment),
        composition_amendments=(amendment,),
    )
    provenance = effective_approval._effective_provenance(
        case,
        effective,
        amendment,
    )
    asset_root = paths.effective_asset_dir(
        tmp_path,
        "payments",
        asset.scope_digest,
        asset.effective_asset_id,
    )
    moved_root = tmp_path / "moved-effective-asset"
    original_read = descriptor_io.read_model_relative
    swapped = False

    def read_then_replace(*args: object, **kwargs: object):
        nonlocal swapped
        value = original_read(*args, **kwargs)  # type: ignore[arg-type]
        relative = args[2] if len(args) > 2 else kwargs.get("relative")
        if not swapped and relative == "asset.json":
            asset_root.rename(moved_root)
            shutil.copytree(moved_root, asset_root)
            swapped = True
        return value

    monkeypatch.setattr(descriptor_io, "read_model_relative", read_then_replace)
    assets_root = asset_root.parent
    assets_fd = os.open(assets_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        with pytest.raises(FoundryPublicationError, match="namespace changed"):
            effective_approval._verify_existing_effective_asset(
                assets_fd,
                asset.effective_asset_id,
                asset=asset,
                effective_contract=effective,
                amendment=amendment,
                provenance=provenance,
            )
    finally:
        os.close(assets_fd)

    assert swapped
