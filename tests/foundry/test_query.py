from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.foundry import approve, importer, query, register
from loop_apidoc.foundry.models import Docset, FoundryInputError
from tests.foundry._fixtures import write_run_dir

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
_RUN_ID = "20260702T120000.000000Z"


def _approve(tmp_path: Path) -> str:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )
    importer.import_run(
        tmp_path, "tappay-backend", write_run_dir(tmp_path / "output" / _RUN_ID)
    )
    return approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    ).asset_id


def test_load_current_asset_returns_approved(tmp_path: Path) -> None:
    asset_id = _approve(tmp_path)
    asset = query.load_current_asset(tmp_path, "tappay-backend")
    assert asset.asset_id == asset_id
    assert asset.validation.score == 92


def test_load_current_asset_without_pointer_raises(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )
    with pytest.raises(FoundryInputError, match="no current asset"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_resolve_current_artifact_returns_existing_path(tmp_path: Path) -> None:
    asset_id = _approve(tmp_path)
    openapi = query.resolve_current_artifact(tmp_path, "tappay-backend", "openapi")
    assert openapi.is_file()
    assert openapi.name == "openapi.yaml"
    assert asset_id in str(openapi)

    handoff = query.resolve_current_artifact(tmp_path, "tappay-backend", "handoff")
    assert handoff.is_dir()


def test_resolve_current_artifact_unknown_name_raises(tmp_path: Path) -> None:
    _approve(tmp_path)
    with pytest.raises(FoundryInputError, match="unknown artifact"):
        query.resolve_current_artifact(tmp_path, "tappay-backend", "bogus")


def test_list_docsets_returns_catalog(tmp_path: Path) -> None:
    _approve(tmp_path)
    catalog = query.list_docsets(tmp_path)
    assert [d.docset_id for d in catalog.docsets] == ["tappay-backend"]
    assert catalog.docsets[0].current_asset is not None
