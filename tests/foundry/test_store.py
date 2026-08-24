from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from loop_apidoc.foundry import descriptor_io, paths, store
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


def test_namespace_validation_rejects_a_symlink_swap_between_identity_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A link inserted after the first identity comparison must fail closed."""
    docset = _docset()
    store.save_docset(tmp_path, docset)
    transaction = store.begin_governance_transaction(tmp_path, docset.docset_id)
    foundry_root = tmp_path / ".foundry"
    moved_root = tmp_path / "moved-foundry"
    original_samestat = os.path.samestat
    swapped = False

    def swap_after_first_identity_check(first: os.stat_result, second: os.stat_result) -> bool:
        nonlocal swapped
        result = original_samestat(first, second)
        if not swapped:
            swapped = True
            foundry_root.rename(moved_root)
            foundry_root.symlink_to(moved_root, target_is_directory=True)
        return result

    monkeypatch.setattr(
        descriptor_io.os.path,
        "samestat",
        swap_after_first_identity_check,
    )
    try:
        with pytest.raises(FoundryPublicationError, match="namespace changed"):
            store.validate_governance_namespace(
                tmp_path,
                docset.docset_id,
                api_fd=transaction.api_fd,
                docset_fd=transaction.docset_fd,
                assets_fd=transaction.assets_fd,
            )
        assert swapped
    finally:
        monkeypatch.undo()
        if foundry_root.is_symlink():
            foundry_root.unlink()
        if moved_root.exists():
            moved_root.rename(foundry_root)
        transaction.close()


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
            retired_entries = tuple(tmp_path.iterdir())
            assert len(retired_entries) == 1
            assert "-cleanup-" in retired_entries[0].name

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


def test_write_once_model_relative_rejects_every_existing_output(
    tmp_path: Path,
) -> None:
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        created, identity = store.write_once_model_relative(
            parent_fd, "nested/docset.json", _docset()
        )
        assert not created
        assert identity == store.entry_identity_relative(parent_fd, "nested/docset.json")

        with pytest.raises(FoundryInputError, match="already exists"):
            store.write_once_model_relative(
                parent_fd, "nested/docset.json", _docset()
            )

        with pytest.raises(FoundryInputError, match="already exists"):
            store.write_once_model_relative(
                parent_fd,
                "nested/docset.json",
                _docset().model_copy(update={"title": "Changed"}),
            )
    finally:
        os.close(parent_fd)


def test_write_once_model_relative_rejects_equal_content_file_replacement_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An idempotent collision must remain bound to the file it read."""
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    model = _docset()
    try:
        store.write_once_model_relative(parent_fd, "decision.json", model)
        original_open = descriptor_io.os.open
        replaced = False

        def open_then_replace(*args: object, **kwargs: object) -> int:
            nonlocal replaced
            descriptor = original_open(*args, **kwargs)  # type: ignore[arg-type]
            name = args[0] if args else kwargs.get("path")
            flags = args[1] if len(args) > 1 else kwargs.get("flags", 0)
            directory = kwargs.get("dir_fd")
            if (
                not replaced
                and name == "decision.json"
                and isinstance(flags, int)
                and not flags & os.O_CREAT
                and isinstance(directory, int)
            ):
                replaced = True
                os.rename(
                    "decision.json",
                    "original-decision.json",
                    src_dir_fd=directory,
                    dst_dir_fd=directory,
                )
                replacement = original_open(
                    "decision.json",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory,
                )
                try:
                    os.write(replacement, model.model_dump_json(indent=2).encode())
                finally:
                    os.close(replacement)
            return descriptor

        monkeypatch.setattr(descriptor_io.os, "open", open_then_replace)

        with pytest.raises(FoundryPublicationError, match="identity changed"):
            store.write_once_model_relative(parent_fd, "decision.json", model)
    finally:
        os.close(parent_fd)


def test_restore_head_snapshot_preserves_a_same_content_substitute(
    tmp_path: Path,
) -> None:
    """Rollback must not overwrite a substituted mutable governance head."""
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    original = _docset()
    updated = original.model_copy(update={"title": "Updated title"})
    try:
        store.write_model_relative(parent_fd, "docset.json", original)
        snapshot = store.read_head_snapshot_relative(parent_fd, "docset.json")
        store._atomic_write_model_relative(
            parent_fd,
            "docset.json",
            updated,
            prefix=".docset-",
            outcome=snapshot,
        )
        assert snapshot.published_identity is not None
        os.rename(
            "docset.json",
            "owned-updated-docset.json",
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        replacement = os.open(
            "docset.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=parent_fd,
        )
        try:
            os.write(replacement, updated.model_dump_json(indent=2).encode())
        finally:
            os.close(replacement)
        substitute_identity = store.entry_identity_relative(parent_fd, "docset.json")

        with pytest.raises(FoundryPublicationError, match="identity changed") as caught:
            store.restore_head_relative(parent_fd, "docset.json", snapshot)

        assert getattr(caught.value, "recovery_required", False)
        assert store.entry_identity_relative(parent_fd, "docset.json") == substitute_identity
        assert (tmp_path / "docset.json").read_text(encoding="utf-8") == updated.model_dump_json(
            indent=2
        )
    finally:
        os.close(parent_fd)


def test_mutable_head_publication_does_not_overwrite_a_substitute_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compare-and-swap handoff must preserve a same-content replacement."""
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    original = _docset()
    updated = original.model_copy(update={"title": "Updated title"})
    try:
        store.write_model_relative(parent_fd, "docset.json", original)
        snapshot = store.read_head_snapshot_relative(parent_fd, "docset.json")
        original_rename = descriptor_io._rename_noreplace
        substituted = False

        def substitute_before_cas(
            source: Path,
            destination: Path,
            *,
            parent_fd: int | None = None,
        ) -> None:
            nonlocal substituted
            if (
                not substituted
                and parent_fd is not None
                and source == Path("docset.json")
            ):
                substituted = True
                os.rename(
                    "docset.json",
                    "original-docset.json",
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
                descriptor = os.open(
                    "docset.json",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=parent_fd,
                )
                try:
                    os.write(descriptor, original.model_dump_json(indent=2).encode())
                finally:
                    os.close(descriptor)
            original_rename(source, destination, parent_fd=parent_fd)

        monkeypatch.setattr(descriptor_io, "_rename_noreplace", substitute_before_cas)

        with pytest.raises(FoundryPublicationError, match="identity changed"):
            store._atomic_write_model_relative(
                parent_fd,
                "docset.json",
                updated,
                prefix=".docset-",
                outcome=snapshot,
            )

        assert substituted
        assert snapshot.published_identity is None
        assert (tmp_path / "docset.json").read_text(encoding="utf-8") == (
            original.model_dump_json(indent=2)
        )
    finally:
        os.close(parent_fd)


def test_write_once_receipt_records_owned_entry_before_parent_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    publication = store.ImmutableEntryPublication()
    original_fsync = descriptor_io.os.fsync

    def fail_parent_fsync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("injected parent fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(descriptor_io.os, "fsync", fail_parent_fsync)
    try:
        with pytest.raises(OSError, match="parent fsync failure"):
            store.write_once_model_relative(
                parent_fd,
                "decision.json",
                _docset(),
                outcome=publication,
            )
        assert publication.owned_entry
        assert publication.identity == store.entry_identity_relative(
            parent_fd, "decision.json"
        )

        monkeypatch.setattr(descriptor_io.os, "fsync", original_fsync)
        assert publication.identity is not None
        store.remove_owned_entry_relative(
            parent_fd, "decision.json", publication.identity
        )
        assert not (tmp_path / "decision.json").exists()
    finally:
        os.close(parent_fd)


def test_remove_owned_entry_preserves_a_substitute_created_during_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "old.txt").write_text("old", encoding="utf-8")
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        identity = store.entry_identity_relative(parent_fd, "owned")
        assert identity is not None
        original_remove = descriptor_io.remove_entry_relative

        def replace_before_cleanup(
            descriptor: int,
            name: str,
            *,
            expected_identity: tuple[int, int] | None = None,
        ) -> None:
            if name == "owned":
                os.rename(
                    "owned",
                    ".original-owned",
                    src_dir_fd=descriptor,
                    dst_dir_fd=descriptor,
                )
            os.mkdir("owned", dir_fd=descriptor)
            replacement_fd = os.open(
                "owned",
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                dir_fd=descriptor,
            )
            try:
                substitute_fd = os.open(
                    "substitute.txt",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=replacement_fd,
                )
                with os.fdopen(substitute_fd, "w", encoding="utf-8") as handle:
                    handle.write("must survive")
            finally:
                os.close(replacement_fd)
            original_remove(
                descriptor,
                name,
                expected_identity=expected_identity,
            )

        monkeypatch.setattr(descriptor_io, "remove_entry_relative", replace_before_cleanup)

        store.remove_owned_entry_relative(parent_fd, "owned", identity)

        assert (owned / "substitute.txt").read_text(encoding="utf-8") == "must survive"
    finally:
        os.close(parent_fd)


def test_remove_owned_entry_rejects_a_substitute_for_its_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "old.txt").write_text("old", encoding="utf-8")
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        identity = store.entry_identity_relative(parent_fd, "owned")
        assert identity is not None
        original_remove = descriptor_io.remove_entry_relative
        foreign_quarantine: Path | None = None

        def replace_quarantine_before_cleanup(
            descriptor: int,
            name: str,
            *,
            expected_identity: tuple[int, int] | None = None,
        ) -> None:
            nonlocal foreign_quarantine
            assert name.startswith(".owned-cleanup-")
            os.rename(
                name,
                ".owned-original",
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
            )
            os.mkdir(name, dir_fd=descriptor)
            foreign_quarantine = tmp_path / name
            (foreign_quarantine / "foreign.txt").write_text(
                "must survive", encoding="utf-8"
            )
            original_remove(
                descriptor,
                name,
                expected_identity=expected_identity,
            )

        monkeypatch.setattr(
            descriptor_io,
            "remove_entry_relative",
            replace_quarantine_before_cleanup,
        )

        with pytest.raises(FoundryPublicationError, match="identity changed") as error:
            store.remove_owned_entry_relative(parent_fd, "owned", identity)

        assert getattr(error.value, "recovery_required", False)
        assert foreign_quarantine is not None
        assert (foreign_quarantine / "foreign.txt").read_text(encoding="utf-8") == (
            "must survive"
        )
        assert (tmp_path / ".owned-original" / "old.txt").is_file()
    finally:
        os.close(parent_fd)


def test_remove_owned_directory_rejects_swap_after_quarantine_fd_is_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "old.txt").write_text("old", encoding="utf-8")
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        identity = store.entry_identity_relative(parent_fd, "owned")
        assert identity is not None
        original_validate = descriptor_io._validate_directory_name_matches_descriptor
        foreign_quarantine: Path | None = None

        def replace_before_final_validation(
            descriptor: int,
            name: str,
            owned_descriptor: int,
        ) -> None:
            nonlocal foreign_quarantine
            assert name.startswith(".owned-cleanup-")
            os.rename(
                name,
                ".owned-original",
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
            )
            os.mkdir(name, dir_fd=descriptor)
            foreign_quarantine = tmp_path / name
            (foreign_quarantine / "foreign.txt").write_text(
                "must survive", encoding="utf-8"
            )
            original_validate(descriptor, name, owned_descriptor)

        monkeypatch.setattr(
            descriptor_io,
            "_validate_directory_name_matches_descriptor",
            replace_before_final_validation,
        )

        with pytest.raises(FoundryPublicationError, match="identity changed") as error:
            store.remove_owned_entry_relative(parent_fd, "owned", identity)

        assert getattr(error.value, "recovery_required", False)
        assert foreign_quarantine is not None
        assert (foreign_quarantine / "foreign.txt").read_text(encoding="utf-8") == (
            "must survive"
        )
    finally:
        os.close(parent_fd)


def test_remove_owned_file_rejects_a_substitute_for_its_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = tmp_path / "owned.json"
    owned.write_text("owned", encoding="utf-8")
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        identity = store.entry_identity_relative(parent_fd, "owned.json")
        assert identity is not None
        original_remove = descriptor_io.remove_entry_relative
        foreign_quarantine: Path | None = None

        def replace_quarantine_before_cleanup(
            descriptor: int,
            name: str,
            *,
            expected_identity: tuple[int, int] | None = None,
        ) -> None:
            nonlocal foreign_quarantine
            assert name.startswith(".owned.json-cleanup-")
            os.rename(
                name,
                ".owned-original.json",
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
            )
            with open(
                name,
                "w",
                encoding="utf-8",
                opener=lambda path, flags: os.open(path, flags, dir_fd=descriptor),
            ) as handle:
                handle.write("must survive")
            foreign_quarantine = tmp_path / name
            original_remove(
                descriptor,
                name,
                expected_identity=expected_identity,
            )

        monkeypatch.setattr(
            descriptor_io,
            "remove_entry_relative",
            replace_quarantine_before_cleanup,
        )

        with pytest.raises(FoundryPublicationError, match="identity changed") as error:
            store.remove_owned_entry_relative(parent_fd, "owned.json", identity)

        assert getattr(error.value, "recovery_required", False)
        assert foreign_quarantine is not None
        assert foreign_quarantine.read_text(encoding="utf-8") == "must survive"
    finally:
        os.close(parent_fd)


def test_remove_owned_entry_retains_its_verified_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = tmp_path / "owned.json"
    owned.write_text("owned", encoding="utf-8")
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))

    def unexpected_delete(*args: object, **kwargs: object) -> None:
        raise AssertionError("owned cleanup must retain its tombstone")

    monkeypatch.setattr(descriptor_io.os, "unlink", unexpected_delete)
    monkeypatch.setattr(descriptor_io.os, "rmdir", unexpected_delete)
    try:
        identity = store.entry_identity_relative(parent_fd, "owned.json")
        assert identity is not None

        store.remove_owned_entry_relative(parent_fd, "owned.json", identity)

        quarantines = tuple(tmp_path.glob(".owned.json-cleanup-*"))
        assert not owned.exists()
        assert len(quarantines) == 1
        assert quarantines[0].read_text(encoding="utf-8") == "owned"
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


def test_copy_tree_rejects_source_file_replaced_by_symlink_after_metadata_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "candidate"
    source.mkdir()
    payload = source / "payload.txt"
    payload.write_text("trusted", encoding="utf-8")
    external = tmp_path / "external.txt"
    external.write_text("attacker", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    destination_fd = os.open(
        destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    original_stat = descriptor_io.os.stat
    replaced = False

    def stat_then_replace(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal replaced
        result = original_stat(path, *args, **kwargs)  # type: ignore[arg-type]
        is_payload = path == payload or (
            path == "payload.txt" and kwargs.get("dir_fd") is not None
        )
        if is_payload and not replaced:
            replaced = True
            payload.unlink()
            payload.symlink_to(external)
        return result

    monkeypatch.setattr(descriptor_io.os, "stat", stat_then_replace)
    try:
        with pytest.raises(FoundryInputError, match="unsafe"):
            store.copy_tree_to_directory(source, destination_fd, "copied")
        assert replaced
        assert not (destination / "copied").exists()
    finally:
        os.close(destination_fd)


def test_copy_tree_rejects_source_directory_replaced_by_symlink_after_metadata_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "candidate"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (nested / "payload.txt").write_text("trusted", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    (external / "payload.txt").write_text("attacker", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    destination_fd = os.open(
        destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    original_stat = descriptor_io.os.stat
    replaced = False

    def stat_then_replace(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal replaced
        result = original_stat(path, *args, **kwargs)  # type: ignore[arg-type]
        is_nested = path == nested or (
            path == "nested" and kwargs.get("dir_fd") is not None
        )
        if is_nested and not replaced:
            replaced = True
            nested.rename(source / "moved-nested")
            nested.symlink_to(external, target_is_directory=True)
        return result

    monkeypatch.setattr(descriptor_io.os, "stat", stat_then_replace)
    try:
        with pytest.raises(FoundryInputError, match="unsafe"):
            store.copy_tree_to_directory(source, destination_fd, "copied")
        assert replaced
        assert not (destination / "copied").exists()
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
