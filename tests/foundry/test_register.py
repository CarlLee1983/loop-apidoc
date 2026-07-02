from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.foundry import register, store
from loop_apidoc.foundry.models import Docset, FoundryInputError, SourceRef, SourceRole


def _docset(**overrides: object) -> Docset:
    base = dict(
        docset_id="tappay-backend",
        title="TapPay Backend API",
        provider="tappay",
        product="backend-api",
        source_scope="Payment backend API documents",
        sources=[
            SourceRef(kind="file", path="sources/tappay/backend.md", role=SourceRole.PRIMARY),
        ],
    )
    base.update(overrides)
    return Docset(**base)  # type: ignore[arg-type]


def test_register_writes_docset_and_catalog(tmp_path: Path) -> None:
    result = register.register_docset(tmp_path, _docset())
    assert result.docset_id == "tappay-backend"
    assert store.load_docset(tmp_path, "tappay-backend") == _docset()
    catalog = store.load_catalog(tmp_path)
    assert [d.docset_id for d in catalog.docsets] == ["tappay-backend"]
    assert catalog.docsets[0].title == "TapPay Backend API"
    assert catalog.docsets[0].current_asset is None


def test_register_existing_without_exist_ok_raises(tmp_path: Path) -> None:
    register.register_docset(tmp_path, _docset())
    with pytest.raises(FoundryInputError, match="already exists"):
        register.register_docset(tmp_path, _docset(title="Changed"))


def test_register_exist_ok_updates_and_preserves_current_asset(tmp_path: Path) -> None:
    register.register_docset(tmp_path, _docset())
    # simulate a prior approval having set current_asset
    existing = store.load_docset(tmp_path, "tappay-backend")
    store.save_docset(tmp_path, existing.model_copy(update={"current_asset": "tappay-backend-1"}))

    updated = register.register_docset(tmp_path, _docset(title="New Title"), exist_ok=True)
    assert updated.title == "New Title"
    assert updated.current_asset == "tappay-backend-1"
    assert store.load_catalog(tmp_path).docsets[0].current_asset == "tappay-backend-1"
