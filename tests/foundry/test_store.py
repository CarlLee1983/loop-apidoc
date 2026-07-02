from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifacts,
    AssetStatus,
    AssetValidation,
    Catalog,
    CatalogDocsetEntry,
    CurrentPointer,
    Docset,
    FoundryInputError,
)


def _docset() -> Docset:
    return Docset(
        docset_id="tappay-backend",
        title="TapPay Backend API",
        provider="tappay",
        product="backend-api",
    )


def _asset() -> Asset:
    return Asset(
        asset_id="tappay-backend-20260702-120000",
        docset_id="tappay-backend",
        status=AssetStatus.APPROVED,
        run_id="20260702T120000.000000Z",
        generated_at="2026-07-02T12:00:00+00:00",
        validation=AssetValidation(ok=True, score=92),
        artifacts=AssetArtifacts(
            openapi="artifacts/openapi.yaml",
            provenance="artifacts/provenance.json",
            validation="artifacts/validation/report.json",
        ),
    )


def test_catalog_missing_returns_empty(tmp_path: Path) -> None:
    assert store.load_catalog(tmp_path) == Catalog()


def test_catalog_round_trip(tmp_path: Path) -> None:
    catalog = Catalog(docsets=[CatalogDocsetEntry(
        docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"
    )])
    store.save_catalog(tmp_path, catalog)
    assert paths.catalog_path(tmp_path).is_file()
    assert store.load_catalog(tmp_path) == catalog


def test_docset_round_trip(tmp_path: Path) -> None:
    store.save_docset(tmp_path, _docset())
    assert store.load_docset(tmp_path, "tappay-backend") == _docset()


def test_missing_docset_raises_input_error(tmp_path: Path) -> None:
    with pytest.raises(FoundryInputError, match="docset.json"):
        store.load_docset(tmp_path, "nope")


def test_asset_round_trip(tmp_path: Path) -> None:
    store.save_asset(tmp_path, _asset())
    loaded = store.load_asset(tmp_path, "tappay-backend", "tappay-backend-20260702-120000")
    assert loaded == _asset()


def test_current_absent_returns_none(tmp_path: Path) -> None:
    assert store.load_current(tmp_path, "tappay-backend") is None


def test_current_round_trip(tmp_path: Path) -> None:
    pointer = CurrentPointer(
        current_asset="tappay-backend-20260702-120000",
        status=AssetStatus.APPROVED,
        validation=AssetValidation(ok=True, score=92),
        generated_at="2026-07-02T12:00:00+00:00",
        artifacts=_asset().artifacts,
    )
    store.save_current(tmp_path, "tappay-backend", pointer)
    assert store.load_current(tmp_path, "tappay-backend") == pointer


def test_invalid_json_raises_input_error(tmp_path: Path) -> None:
    path = paths.docset_manifest_path(tmp_path, "tappay-backend")
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(FoundryInputError, match="docset.json"):
        store.load_docset(tmp_path, "tappay-backend")


def test_upsert_catalog_entry_replaces_and_appends() -> None:
    base = Catalog(docsets=[
        CatalogDocsetEntry(docset_id="a", title="A", provider="p", product="x"),
        CatalogDocsetEntry(docset_id="b", title="B", provider="p", product="y"),
    ])
    replaced = store.upsert_catalog_entry(
        base, CatalogDocsetEntry(docset_id="a", title="A2", provider="p", product="x", current_asset="a-1")
    )
    assert [d.docset_id for d in replaced.docsets] == ["a", "b"]
    assert replaced.docsets[0].title == "A2"
    assert replaced.docsets[0].current_asset == "a-1"
    # original is untouched (immutability)
    assert base.docsets[0].title == "A"

    appended = store.upsert_catalog_entry(
        base, CatalogDocsetEntry(docset_id="c", title="C", provider="p", product="z")
    )
    assert [d.docset_id for d in appended.docsets] == ["a", "b", "c"]
