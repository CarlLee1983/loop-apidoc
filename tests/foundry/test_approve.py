from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.foundry import approve, importer, register, store
from loop_apidoc.foundry.models import (
    AssetStatus,
    Docset,
    FoundryApprovalError,
    FoundryInputError,
)
from tests.foundry._fixtures import write_run_dir

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 7, 3, 9, 30, 0, tzinfo=timezone.utc)
_RUN_ID = "20260702T120000.000000Z"
_RUN_ID_2 = "20260703T090000.000000Z"


def _setup(tmp_path: Path, run_id: str = _RUN_ID, **run_kwargs: object) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )
    run_dir = write_run_dir(tmp_path / "output" / run_id, **run_kwargs)  # type: ignore[arg-type]
    importer.import_run(tmp_path, "tappay-backend", run_dir)


def test_approve_creates_asset_and_current(tmp_path: Path) -> None:
    _setup(tmp_path)

    asset = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="human-review", now=_NOW
    )

    assert asset.asset_id == "tappay-backend-20260702-120000"
    assert asset.status is AssetStatus.APPROVED
    assert asset.approved_by == "human-review"
    assert asset.approved_at == _NOW.isoformat()
    assert asset.validation.ok is True
    assert asset.validation.score == 92
    assert asset.source_hashes == ["hash-manual"]
    assert asset.supersedes is None

    # artifacts copied and self-contained
    art_dir = tmp_path / ".foundry" / "api" / "docsets" / "tappay-backend" / "assets" / asset.asset_id / "artifacts"
    assert (art_dir / "openapi.yaml").is_file()
    assert (art_dir / "handoff" / "sdk-hints.json").is_file()
    assert asset.artifacts.integration_contract == "artifacts/integration-contract.json"
    assert asset.artifacts.handoff == "artifacts/handoff/"
    assert asset.artifacts.score == "artifacts/score/score.json"

    # persisted + pointers updated
    assert store.load_asset(tmp_path, "tappay-backend", asset.asset_id) == asset
    current = store.load_current(tmp_path, "tappay-backend")
    assert current is not None
    assert current.current_asset == asset.asset_id
    assert current.validation.score == 92
    assert store.load_docset(tmp_path, "tappay-backend").current_asset == asset.asset_id
    assert store.load_catalog(tmp_path).docsets[0].current_asset == asset.asset_id


def test_approve_supersedes_previous_asset(tmp_path: Path) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    # import + approve a second run
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)
    second = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID_2, approved_by="a", now=_LATER
    )

    assert second.supersedes == first.asset_id
    reloaded_first = store.load_asset(tmp_path, "tappay-backend", first.asset_id)
    assert reloaded_first.status is AssetStatus.SUPERSEDED
    assert store.load_current(tmp_path, "tappay-backend").current_asset == second.asset_id


def test_approve_missing_candidate_raises_input_error(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )
    with pytest.raises(FoundryInputError, match="candidate"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )


def test_approve_refuses_failing_validation(tmp_path: Path) -> None:
    _setup(tmp_path, validation_ok=False)
    with pytest.raises(FoundryApprovalError, match="validation"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )


def test_approve_refuses_min_score_when_score_absent(tmp_path: Path) -> None:
    _setup(tmp_path, score=None)
    with pytest.raises(FoundryApprovalError, match="score"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="ci-score-90", now=_NOW, min_score=90
        )


def test_approve_allow_failing_overrides_gate(tmp_path: Path) -> None:
    _setup(tmp_path, validation_ok=False)
    asset = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW, allow_failing=True
    )
    assert asset.validation.ok is False
    assert asset.status is AssetStatus.APPROVED


def test_approve_refuses_below_min_score(tmp_path: Path) -> None:
    _setup(tmp_path, score=70)
    with pytest.raises(FoundryApprovalError, match="score"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="ci-score-90", now=_NOW, min_score=90
        )
