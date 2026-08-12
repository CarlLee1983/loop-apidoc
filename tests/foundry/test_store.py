from __future__ import annotations

import os
from pathlib import Path

import pytest

from loop_apidoc.foundry import paths, store
from loop_apidoc.foundry.models import (
    Asset,
    AssetArtifactDigests,
    AssetArtifactKinds,
    AssetArtifacts,
    AssetStatus,
    AssetValidation,
    Catalog,
    CatalogDocsetEntry,
    CurrentPointer,
    Docset,
    FoundryInputError,
    FoundryPublicationError,
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
        schema_version="normative-asset/v1",
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
        artifact_digests=AssetArtifactDigests(
            openapi="0" * 64,
            provenance="1" * 64,
            validation="2" * 64,
        ),
        artifact_kinds=AssetArtifactKinds(
            openapi="file",
            provenance="file",
            validation="file",
        ),
        approved_by="fixture",
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
        schema_version="normative-current/v1",
        docset_id="tappay-backend",
        current_asset="tappay-backend-20260702-120000",
        asset_digest="3" * 64,
        status=AssetStatus.APPROVED,
        validation=AssetValidation(ok=True, score=92),
        generated_at="2026-07-02T12:00:00+00:00",
        artifacts=_asset().artifacts,
        artifact_digests=_asset().artifact_digests,
        artifact_kinds=_asset().artifact_kinds,
    )
    store.save_current(tmp_path, "tappay-backend", pointer)
    assert store.load_current(tmp_path, "tappay-backend") == pointer


def test_save_current_failure_preserves_previous_pointer_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pointer = CurrentPointer(
        schema_version="normative-current/v1",
        docset_id="tappay-backend",
        current_asset="tappay-backend-20260702-120000",
        asset_digest="3" * 64,
        status=AssetStatus.APPROVED,
        validation=AssetValidation(ok=True, score=92),
        generated_at="2026-07-02T12:00:00+00:00",
        artifacts=_asset().artifacts,
        artifact_digests=_asset().artifact_digests,
        artifact_kinds=_asset().artifact_kinds,
    )
    store.save_current(tmp_path, "tappay-backend", pointer)
    path = paths.current_path(tmp_path, "tappay-backend")
    previous = path.read_bytes()

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("pointer publication failed")

    monkeypatch.setattr(store.os, "replace", fail_replace)
    with pytest.raises(OSError, match="pointer publication failed"):
        store.save_current(
            tmp_path,
            "tappay-backend",
            pointer.model_copy(update={"current_asset": "new"}),
        )

    assert path.read_bytes() == previous
    assert not list(path.parent.glob(".current-*"))


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


def test_upsert_catalog_entry_collapses_existing_duplicates() -> None:
    entry = CatalogDocsetEntry(
        docset_id="a", title="A", provider="p", product="x", current_asset=None
    )
    catalog = Catalog(docsets=[entry, entry.model_copy()])

    updated = store.upsert_catalog_entry(
        catalog, entry.model_copy(update={"title": "A2"})
    )

    assert [item.docset_id for item in updated.docsets] == ["a"]
    assert updated.docsets[0].title == "A2"


def test_governance_transaction_serializes_catalog_updates_across_docsets(
    tmp_path: Path,
) -> None:
    first = _docset()
    second = first.model_copy(
        update={"docset_id": "other-api", "title": "Other API"}
    )
    store.save_docset(tmp_path, first)
    store.save_docset(tmp_path, second)

    transaction = store.begin_governance_transaction(tmp_path, first.docset_id)
    try:
        with pytest.raises(
            FoundryInputError, match="transaction is already in progress"
        ):
            store.begin_governance_transaction(tmp_path, second.docset_id)
        assert (
            paths.foundry_api_root(tmp_path) / ".catalog-governance.lock"
        ).is_dir()
    finally:
        transaction.close()

    retry = store.begin_governance_transaction(tmp_path, second.docset_id)
    retry.close()


def test_owned_directory_creation_cleans_up_after_parent_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    original_fsync = os.fsync
    calls = 0

    def fail_first_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("staging fsync failed")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_first_fsync)
    try:
        with pytest.raises(OSError, match="staging fsync failed"):
            store.create_owned_directory_relative(parent_fd, prefix=".stage-")
        assert list(tmp_path.iterdir()) == []

        name, descriptor, _identity = store.create_owned_directory_relative(
            parent_fd, prefix=".retry-"
        )
        os.close(descriptor)
        assert (tmp_path / name).is_dir()
    finally:
        os.close(parent_fd)


def test_catalog_transaction_creates_namespace_serializes_and_releases_lock(
    tmp_path: Path,
) -> None:
    transaction = store.begin_catalog_transaction(tmp_path)
    try:
        assert paths.docsets_root(tmp_path).is_dir()
        with pytest.raises(
            FoundryInputError, match="transaction is already in progress"
        ):
            store.begin_catalog_transaction(tmp_path)
    finally:
        transaction.close()

    retry = store.begin_catalog_transaction(tmp_path)
    retry.close()


def test_catalog_transaction_fails_closed_when_namespace_is_replaced(
    tmp_path: Path,
) -> None:
    transaction = store.begin_catalog_transaction(tmp_path)
    api_root = paths.foundry_api_root(tmp_path)
    moved_root = tmp_path / "api-before-replacement"
    api_root.rename(moved_root)
    api_root.mkdir()

    with pytest.raises(FoundryPublicationError, match="namespace changed"):
        transaction.close()

    transaction.abandon()


def test_write_once_model_relative_is_idempotent_and_rejects_conflicts(
    tmp_path: Path,
) -> None:
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        created, identity = store.write_once_model_relative(
            parent_fd, "nested/docset.json", _docset()
        )
        assert not created
        assert identity == store.entry_identity_relative(parent_fd, "nested/docset.json")

        existing, existing_identity = store.write_once_model_relative(
            parent_fd, "nested/docset.json", _docset()
        )
        assert existing
        assert existing_identity == identity

        with pytest.raises(FoundryInputError, match="already exists"):
            store.write_once_model_relative(
                parent_fd,
                "nested/docset.json",
                _docset().model_copy(update={"title": "Changed"}),
            )
    finally:
        os.close(parent_fd)


def test_copy_tree_to_directory_copies_nested_regular_files_and_rolls_back_unsafe_input(
    tmp_path: Path,
) -> None:
    source = tmp_path / "candidate"
    (source / "nested").mkdir(parents=True)
    (source / "asset.json").write_text("{}", encoding="utf-8")
    (source / "nested" / "artifact.txt").write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    destination_fd = os.open(
        destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        store.copy_tree_to_directory(source, destination_fd, "published")
        assert (destination / "published" / "nested" / "artifact.txt").read_text(
            encoding="utf-8"
        ) == "payload"

        unsafe_source = tmp_path / "unsafe-candidate"
        unsafe_source.mkdir()
        (unsafe_source / "link").symlink_to(source / "asset.json")
        with pytest.raises(FoundryInputError, match="unsafe"):
            store.copy_tree_to_directory(unsafe_source, destination_fd, "unsafe")
        assert not (destination / "unsafe").exists()
    finally:
        os.close(destination_fd)


def test_publish_asset_publishes_once_without_replacing_existing_root(
    tmp_path: Path,
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    staged = assets / ".stage"
    staged.mkdir()
    (staged / "asset.json").write_text("{}", encoding="utf-8")
    published = assets / "asset-1"

    outcome = store.publish_asset(staged, published)

    assert outcome.owned_root
    assert outcome.identity is not None
    assert (published / "asset.json").is_file()

    retry_stage = assets / ".retry-stage"
    retry_stage.mkdir()
    with pytest.raises(FoundryInputError, match="already exists"):
        store.publish_asset(retry_stage, published)
