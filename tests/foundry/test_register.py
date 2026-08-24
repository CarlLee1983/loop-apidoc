from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.foundry import descriptor_namespace, governed, head_io, paths, register, store
from loop_apidoc.foundry.models import (
    Docset,
    FoundryInputError,
    FoundryPublicationError,
    SourceRef,
    SourceRole,
)


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


def test_register_respects_an_active_cross_docset_catalog_transaction(
    tmp_path: Path,
) -> None:
    register.register_docset(tmp_path, _docset())
    transaction = store.begin_governance_transaction(tmp_path, "tappay-backend")
    try:
        with pytest.raises(
            FoundryInputError, match="transaction is already in progress"
        ):
            register.register_docset(
                tmp_path, _docset(docset_id="other-api", title="Other API")
            )
    finally:
        transaction.close()

    assert [
        item.docset_id for item in store.load_catalog(tmp_path).docsets
    ] == ["tappay-backend"]


def test_register_rejects_a_docset_id_that_escapes_the_docsets_root(
    tmp_path: Path,
) -> None:
    with pytest.raises(FoundryInputError, match="unsafe docset id"):
        register.register_docset(
            tmp_path, _docset(docset_id="../escaped", title="Escaped")
        )

    assert not (paths.foundry_api_root(tmp_path) / "escaped").exists()


def test_register_catalog_failure_rolls_back_new_docset_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_save_catalog = store.save_catalog

    def fail_catalog(*_args: object, **_kwargs: object) -> None:
        raise OSError("catalog publication failed")

    monkeypatch.setattr(store, "save_catalog", fail_catalog)
    with pytest.raises(OSError, match="catalog publication failed"):
        register.register_docset(tmp_path, _docset())

    assert not paths.docset_dir(tmp_path, "tappay-backend").exists()
    assert not paths.catalog_path(tmp_path).exists()
    assert not (
        paths.foundry_api_root(tmp_path) / ".catalog-governance.lock"
    ).exists()

    monkeypatch.setattr(store, "save_catalog", original_save_catalog)
    result = register.register_docset(tmp_path, _docset())
    assert result.docset_id == "tappay-backend"


def test_register_preflight_failure_preserves_captured_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register.register_docset(tmp_path, _docset())
    catalog_path = paths.catalog_path(tmp_path)
    docset_path = paths.docset_manifest_path(tmp_path, "tappay-backend")
    catalog_before = catalog_path.read_bytes()
    docset_before = docset_path.read_bytes()
    original_read_head = head_io.read_head_snapshot_relative
    reads = 0

    def fail_second_snapshot(parent_fd: int, name: str) -> head_io.HeadSnapshot:
        nonlocal reads
        reads += 1
        if reads == 2:
            raise OSError("docset snapshot failed")
        return original_read_head(parent_fd, name)

    monkeypatch.setattr(head_io, "read_head_snapshot_relative", fail_second_snapshot)

    with pytest.raises(OSError, match="docset snapshot failed"):
        register.register_docset(
            tmp_path, _docset(title="Updated title"), exist_ok=True
        )

    assert catalog_path.read_bytes() == catalog_before
    assert docset_path.read_bytes() == docset_before
    assert not (
        paths.foundry_api_root(tmp_path) / ".catalog-governance.lock"
    ).exists()


def test_register_namespace_replacement_preserves_foreign_directory_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_save_catalog = store.save_catalog
    docset_root = paths.docset_dir(tmp_path, "tappay-backend")
    displaced_root = docset_root.with_name("owned-docset-displaced")

    def replace_namespace(*args: object, **kwargs: object) -> None:
        original_save_catalog(*args, **kwargs)
        docset_root.rename(displaced_root)
        docset_root.mkdir()
        (docset_root / "foreign.txt").write_text("foreign", encoding="utf-8")

    monkeypatch.setattr(store, "save_catalog", replace_namespace)

    with pytest.raises(
        FoundryPublicationError, match="transaction-owned entry identity changed"
    ):
        register.register_docset(tmp_path, _docset())

    assert (docset_root / "foreign.txt").read_text(encoding="utf-8") == "foreign"
    assert (displaced_root / "docset.json").is_file()
    assert (
        paths.foundry_api_root(tmp_path) / ".catalog-governance.lock"
    ).exists()


def test_register_rejects_existing_docset_replaced_between_stat_and_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register.register_docset(tmp_path, _docset())
    catalog_before = paths.catalog_path(tmp_path).read_bytes()
    docset_root = paths.docset_dir(tmp_path, "tappay-backend")
    displaced_root = docset_root.with_name("original-docset-displaced")
    original_open = descriptor_namespace.open_directory_relative
    replaced = False

    def replace_before_open(parent_fd: int, name: str) -> int:
        nonlocal replaced
        if name == "tappay-backend" and not replaced:
            replaced = True
            docset_root.rename(displaced_root)
            docset_root.mkdir()
            (docset_root / "foreign.txt").write_text("foreign", encoding="utf-8")
        return original_open(parent_fd, name)

    monkeypatch.setattr(descriptor_namespace, "open_directory_relative", replace_before_open)

    with pytest.raises(FoundryPublicationError, match="namespace changed"):
        register.register_docset(
            tmp_path, _docset(title="Updated title"), exist_ok=True
        )

    assert paths.catalog_path(tmp_path).read_bytes() == catalog_before
    assert (docset_root / "foreign.txt").read_text(encoding="utf-8") == "foreign"
    assert (displaced_root / "docset.json").is_file()
    assert not (
        paths.foundry_api_root(tmp_path) / ".catalog-governance.lock"
    ).exists()


def test_register_api_namespace_replacement_rolls_back_and_retains_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_save_catalog = store.save_catalog
    api_root = paths.foundry_api_root(tmp_path)
    displaced_api = tmp_path / "displaced-api"

    def replace_api_namespace(*args: object, **kwargs: object) -> None:
        original_save_catalog(*args, **kwargs)
        api_root.rename(displaced_api)
        paths.docsets_root(tmp_path).mkdir(parents=True)

    monkeypatch.setattr(store, "save_catalog", replace_api_namespace)

    with pytest.raises(FoundryPublicationError, match="namespace changed"):
        register.register_docset(tmp_path, _docset())

    assert not paths.catalog_path(tmp_path).exists()
    assert not paths.docset_dir(tmp_path, "tappay-backend").exists()
    assert not (displaced_api / "catalog.json").exists()
    assert not (displaced_api / "docsets" / "tappay-backend").exists()
    assert (displaced_api / ".catalog-governance.lock").is_dir()


def test_register_rejects_symlinked_foundry_before_creating_external_state(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    (tmp_path / ".foundry").symlink_to(external, target_is_directory=True)

    with pytest.raises(FoundryInputError, match="governance"):
        register.register_docset(tmp_path, _docset())

    assert list(external.iterdir()) == []


def test_reregistration_rejects_a_corrupt_docset_manifest(tmp_path: Path) -> None:
    register.register_docset(tmp_path, _docset())
    paths.docset_manifest_path(tmp_path, "tappay-backend").write_text(
        "{ not json", encoding="utf-8"
    )

    with pytest.raises(FoundryInputError, match="invalid docset.json"):
        register.register_docset(tmp_path, _docset(title="Renamed"), exist_ok=True)


def test_registration_rejects_a_corrupt_catalog(tmp_path: Path) -> None:
    register.register_docset(tmp_path, _docset())
    paths.catalog_path(tmp_path).write_text("{ not json", encoding="utf-8")

    with pytest.raises(FoundryInputError, match="invalid catalog.json"):
        register.register_docset(tmp_path, _docset(docset_id="other-backend"))


def test_reregistration_failure_restores_the_previous_docset_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An update that fails after rewriting docset.json must leave the old one."""
    register.register_docset(tmp_path, _docset())
    before = paths.docset_manifest_path(tmp_path, "tappay-backend").read_text(encoding="utf-8")

    def fail_save_catalog(*_args: object, **_kwargs: object) -> None:
        raise OSError("catalog write failed")

    monkeypatch.setattr(store, "save_catalog", fail_save_catalog)
    with pytest.raises(OSError, match="catalog write failed"):
        register.register_docset(
            tmp_path, _docset(title="Renamed Backend API"), exist_ok=True
        )

    assert paths.docset_manifest_path(tmp_path, "tappay-backend").read_text(
        encoding="utf-8"
    ) == before
    assert store.load_docset(tmp_path, "tappay-backend").title == "TapPay Backend API"
    catalog = store.load_catalog(tmp_path)
    assert [entry.title for entry in catalog.docsets] == ["TapPay Backend API"]


def test_catalog_head_substitute_is_not_overwritten_during_registration_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register.register_docset(tmp_path, _docset())
    catalog_path = paths.catalog_path(tmp_path)
    displaced = catalog_path.with_name("transaction-owned-catalog.json")
    original_save_catalog = store.save_catalog
    published: bytes | None = None

    def publish_then_substitute(*args: object, **kwargs: object) -> None:
        nonlocal published
        original_save_catalog(*args, **kwargs)
        published = catalog_path.read_bytes()
        catalog_path.rename(displaced)
        catalog_path.write_bytes(published)
        raise OSError("injected post-publication catalog failure")

    monkeypatch.setattr(store, "save_catalog", publish_then_substitute)

    with pytest.raises(FoundryPublicationError, match="rollback failures"):
        register.register_docset(
            tmp_path,
            _docset(title="Updated Backend API"),
            exist_ok=True,
        )

    assert published is not None
    assert catalog_path.read_bytes() == published
    assert catalog_path.stat().st_ino != displaced.stat().st_ino
    assert (tmp_path / ".foundry/api/.catalog-governance.lock").is_dir()


def test_registration_reports_a_lock_release_failure_after_a_clean_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Releasing the lock validates the namespace; a change there is not silent."""
    register.register_docset(tmp_path, _docset())
    original_validate = governed.validate_catalog_namespace
    calls: list[int] = []

    def fail_on_lock_release(*args: object, **kwargs: object) -> None:
        calls.append(1)
        # The register body validates first; the lock release validates last.
        if len(calls) > 1:
            raise FoundryPublicationError("governance namespace changed")
        original_validate(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(governed, "validate_catalog_namespace", fail_on_lock_release)
    with pytest.raises(FoundryPublicationError, match="lock cleanup failed"):
        register.register_docset(tmp_path, _docset(docset_id="other-backend"))
