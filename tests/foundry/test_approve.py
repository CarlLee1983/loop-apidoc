from __future__ import annotations

import hashlib
import json
import shutil
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loop_apidoc.foundry import approve, importer, paths, query, register, store
from loop_apidoc.foundry.models import (
    AssetStatus,
    Docset,
    FoundryApprovalError,
    FoundryInputError,
    FoundryPublicationError,
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


def test_approve_rejects_preexisting_asset_root_without_overwrite(tmp_path: Path) -> None:
    _setup(tmp_path)
    asset_root = paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    )
    asset_root.mkdir(parents=True)
    sentinel = asset_root / "asset.json"
    sentinel.write_text("sentinel", encoding="utf-8")

    with pytest.raises(FoundryApprovalError, match="asset already exists"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )

    assert sentinel.read_text(encoding="utf-8") == "sentinel"


def test_approve_rejects_preexisting_asset_root_file_without_overwrite(
    tmp_path: Path,
) -> None:
    _setup(tmp_path)
    asset_root = paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    )
    asset_root.parent.mkdir(parents=True, exist_ok=True)
    asset_root.write_text("sentinel", encoding="utf-8")

    with pytest.raises(FoundryApprovalError, match="asset already exists"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )

    assert asset_root.read_text(encoding="utf-8") == "sentinel"


def test_approve_rejects_asset_root_symlink_without_writing_outside(
    tmp_path: Path,
) -> None:
    _setup(tmp_path)
    asset_root = paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    )
    outside = tmp_path / "outside-asset-root"
    outside.mkdir()
    asset_root.parent.mkdir(parents=True, exist_ok=True)
    asset_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(FoundryApprovalError, match="asset already exists"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )

    assert not (outside / "asset.json").exists()
    assert not (outside / "artifacts").exists()


def test_rename_collision_does_not_delete_foreign_asset_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    original_rename = store._rename_noreplace

    def foreign_root_then_fail(source: Path, destination: Path, **kwargs: object) -> None:
        foreign_root = destination
        foreign_root.mkdir()
        (foreign_root / "sentinel").write_text("owned elsewhere", encoding="utf-8")
        raise FileExistsError("foreign asset root won the rename race")

    monkeypatch.setattr(store, "_rename_noreplace", foreign_root_then_fail)
    asset_root = paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    )

    with pytest.raises(FoundryInputError, match="asset root publication failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
        )

    assert (asset_root / "sentinel").read_text(encoding="utf-8") == "owned elsewhere"
    monkeypatch.setattr(store, "_rename_noreplace", original_rename)


def test_real_no_replace_collision_preserves_foreign_empty_asset_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A destination appearing between the check and rename is never replaced."""
    _setup(tmp_path)
    original_exclusive_rename = store._rename_noreplace

    def foreign_root_then_exclusive_rename(
        staged_root: Path, asset_root: Path, **kwargs: object
    ) -> None:
        asset_root.mkdir()
        original_exclusive_rename(staged_root, asset_root, **kwargs)

    monkeypatch.setattr(
        store, "_rename_noreplace", foreign_root_then_exclusive_rename
    )

    with pytest.raises(FoundryInputError, match="asset root publication failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
        )

    foreign_root = paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    )
    (foreign_root / "sentinel").write_text("owned elsewhere", encoding="utf-8")
    assert (foreign_root / "sentinel").read_text(encoding="utf-8") == "owned elsewhere"


def test_approve_rejects_duplicate_catalog_baseline_before_asset_publication(
    tmp_path: Path,
) -> None:
    _setup(tmp_path)
    catalog = store.load_catalog(tmp_path)
    entry = catalog.docsets[0]
    store.save_catalog(
        tmp_path,
        catalog.model_copy(update={"docsets": [entry, entry.model_copy()]}),
    )

    with pytest.raises(FoundryInputError, match="catalog entry is not unique"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )

    assert not paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    ).exists()


def test_concurrent_approval_is_serialized_per_docset(tmp_path: Path, monkeypatch) -> None:
    _setup(tmp_path)
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)
    entered = threading.Event()
    release = threading.Event()
    first_call = True
    original_save_current = store.save_current

    def pause_first_save(*args: object, **kwargs: object) -> None:
        nonlocal first_call
        if first_call:
            first_call = False
            entered.set()
            assert release.wait(timeout=5)
        original_save_current(*args, **kwargs)

    monkeypatch.setattr(store, "save_current", pause_first_save)
    outcomes: dict[str, object] = {}

    def approve_first() -> None:
        try:
            outcomes["first"] = approve.approve_candidate(
                tmp_path, "tappay-backend", _RUN_ID, approved_by="one", now=_NOW
            )
        except BaseException as exc:  # pragma: no cover - assertion below reports it
            outcomes["first"] = exc

    thread = threading.Thread(target=approve_first)
    thread.start()
    assert entered.wait(timeout=5)
    with pytest.raises(FoundryInputError, match="transaction is already in progress"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID_2, approved_by="two", now=_LATER
        )
    release.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert not isinstance(outcomes.get("first"), BaseException)
    first = outcomes["first"]
    assert isinstance(first, object)
    assert store.load_current(tmp_path, "tappay-backend").current_asset == first.asset_id
    assert not paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260703-090000"
    ).exists()


def test_concurrent_retry_cannot_rollback_or_fork_after_first_transaction_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)
    entered = threading.Event()
    release = threading.Event()
    first_call = True
    original_save_current = store.save_current

    def fail_first_save(*_args: object, **_kwargs: object) -> None:
        nonlocal first_call
        if first_call:
            first_call = False
            entered.set()
            assert release.wait(timeout=5)
            raise OSError("first transaction pointer failure")
        original_save_current(*_args, **_kwargs)

    monkeypatch.setattr(store, "save_current", fail_first_save)
    outcome: dict[str, BaseException | None] = {}

    def approve_first() -> None:
        try:
            approve.approve_candidate(
                tmp_path, "tappay-backend", _RUN_ID, approved_by="one", now=_NOW
            )
        except BaseException as exc:  # pragma: no cover - assertion below reports it
            outcome["error"] = exc

    thread = threading.Thread(target=approve_first)
    thread.start()
    assert entered.wait(timeout=5)
    with pytest.raises(FoundryInputError, match="transaction is already in progress"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID_2, approved_by="two", now=_LATER
        )
    release.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert isinstance(outcome.get("error"), OSError)
    assert not paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    ).exists()
    assert store.load_docset(tmp_path, "tappay-backend").current_asset is None

    monkeypatch.setattr(store, "save_current", original_save_current)
    retried = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID_2, approved_by="two", now=_LATER
    )
    assert retried.supersedes is None
    assert store.load_current(tmp_path, "tappay-backend").current_asset == retried.asset_id


def test_approval_rejects_symlinked_docset_ancestor_before_writing_outside(
    tmp_path: Path,
) -> None:
    _setup(tmp_path)
    docsets_root = paths.docsets_root(tmp_path)
    outside_root = tmp_path / "outside-foundry"
    outside_root.mkdir()
    shutil.move(str(docsets_root), str(outside_root / "docsets"))
    docsets_root.symlink_to(outside_root / "docsets", target_is_directory=True)

    with pytest.raises(FoundryInputError, match="governance ancestor is unsafe"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
        )

    assert not paths.asset_dir(tmp_path, "tappay-backend", "tappay-backend-20260702-120000").exists()
    assert not (outside_root / "docsets" / "tappay-backend" / "assets").exists()


def test_approval_rejects_docset_ancestor_replaced_after_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    docset_dir = paths.docset_dir(tmp_path, "tappay-backend")
    outside_root = tmp_path / "outside-foundry"
    outside_root.mkdir()
    moved_docset = outside_root / "tappay-backend"
    original_validate = store._validate_governance_ancestors

    def validate_then_replace(project_root: Path, docset_id: str) -> None:
        original_validate(project_root, docset_id)
        docset_dir.rename(moved_docset)
        docset_dir.symlink_to(moved_docset, target_is_directory=True)

    monkeypatch.setattr(store, "_validate_governance_ancestors", validate_then_replace)

    with pytest.raises(FoundryInputError, match="cannot acquire governance transaction"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
        )

    assert not (moved_docset / ".governance.lock").exists()
    assert not paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    ).exists()


def test_approval_rejects_unsafe_docset_id_before_lock_path_construction(
    tmp_path: Path,
) -> None:
    _setup(tmp_path)
    (tmp_path / "escape").mkdir()

    with pytest.raises(FoundryInputError, match="unsafe docset id"):
        approve.approve_candidate(
            tmp_path, "../escape", _RUN_ID, approved_by="operator", now=_NOW
        )

    assert not (tmp_path / "escape" / ".governance.lock").exists()


@pytest.mark.skipif(not Path("/var").is_symlink(), reason="requires macOS /var alias")
def test_approval_normalizes_macos_var_alias_for_project_root(tmp_path: Path) -> None:
    _setup(tmp_path)
    private_var = Path("/private/var")
    if not tmp_path.is_relative_to(private_var):
        pytest.skip("pytest temporary directory is not under /private/var")
    aliased_root = Path("/var") / tmp_path.relative_to(private_var)

    asset = approve.approve_candidate(
        aliased_root,
        "tappay-backend",
        _RUN_ID,
        approved_by="operator",
        now=_NOW,
    )

    assert asset.asset_id == "tappay-backend-20260702-120000"
    assert query.load_current_asset(tmp_path, "tappay-backend").asset_id == asset.asset_id


def test_approval_rejects_a_predecessor_changed_after_review_snapshot(
    tmp_path: Path,
) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="one", now=_NOW
    )
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)

    with pytest.raises(FoundryInputError, match="reviewed predecessor"):
        approve.approve_candidate(
            tmp_path,
            "tappay-backend",
            _RUN_ID_2,
            approved_by="two",
            now=_LATER,
            expected_base_asset_id=first.asset_id,
            expected_base_asset_digest="0" * 64,
            enforce_expected_base=True,
        )

    assert store.load_current(tmp_path, "tappay-backend").current_asset == first.asset_id


def test_approve_records_supersession_without_mutating_previous_asset(tmp_path: Path) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    first_dir = (
        tmp_path / ".foundry/api/docsets/tappay-backend/assets" / first.asset_id
    )
    prior_bytes = {
        path.relative_to(first_dir): path.read_bytes()
        for path in first_dir.rglob("*")
        if path.is_file()
    }
    # import + approve a second run
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)
    second = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID_2, approved_by="a", now=_LATER
    )

    assert second.supersedes == first.asset_id
    reloaded_first = store.load_asset(tmp_path, "tappay-backend", first.asset_id)
    assert reloaded_first.status is AssetStatus.APPROVED
    assert {
        path.relative_to(first_dir): path.read_bytes()
        for path in first_dir.rglob("*")
        if path.is_file()
    } == prior_bytes
    assert store.load_current(tmp_path, "tappay-backend").current_asset == second.asset_id


def test_approval_failure_before_current_write_keeps_current_pointer(tmp_path: Path, monkeypatch) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)

    def fail_current(*_args: object, **_kwargs: object) -> None:
        raise OSError("current pointer write failed")

    monkeypatch.setattr(store, "save_current", fail_current)
    with pytest.raises(OSError, match="current pointer write failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID_2, approved_by="a", now=_LATER
        )

    current = store.load_current(tmp_path, "tappay-backend")
    assert current is not None
    assert current.current_asset == first.asset_id


def test_pointer_failure_rolls_back_catalog_and_docset_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    paths_to_preserve = (
        paths.current_path(tmp_path, "tappay-backend"),
        paths.docset_manifest_path(tmp_path, "tappay-backend"),
        paths.catalog_path(tmp_path),
    )
    previous_bytes = {path: path.read_bytes() for path in paths_to_preserve}
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)
    original_save_current = store.save_current
    calls = 0

    def fail_once(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("current pointer write failed")
        original_save_current(*args, **kwargs)

    monkeypatch.setattr(store, "save_current", fail_once)
    with pytest.raises(OSError, match="current pointer write failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID_2, approved_by="a", now=_LATER
        )

    assert {path: path.read_bytes() for path in paths_to_preserve} == previous_bytes
    monkeypatch.setattr(store, "save_current", original_save_current)
    retried = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID_2, approved_by="a", now=_LATER
    )

    assert retried.supersedes == first.asset_id
    assert store.load_current(tmp_path, "tappay-backend").current_asset == retried.asset_id
    assert store.load_docset(tmp_path, "tappay-backend").current_asset == retried.asset_id
    assert store.load_catalog(tmp_path).docsets[0].current_asset == retried.asset_id


def test_namespace_replacement_after_lock_does_not_touch_foreign_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    docset_dir = paths.docset_dir(tmp_path, "tappay-backend")
    moved_docset = tmp_path / "locked-docset"
    original_save_current = store.save_current

    def replace_namespace_then_fail(*_args: object, **_kwargs: object) -> None:
        docset_dir.rename(moved_docset)
        (docset_dir / "assets").mkdir(parents=True)
        (docset_dir / "sentinel.txt").write_text("foreign", encoding="utf-8")
        raise OSError("current pointer write failed")

    monkeypatch.setattr(store, "save_current", replace_namespace_then_fail)

    with pytest.raises(OSError, match="current pointer write failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )

    assert sorted(
        path.relative_to(docset_dir).as_posix()
        for path in docset_dir.rglob("*")
    ) == ["assets", "sentinel.txt"]
    assert (docset_dir / "sentinel.txt").read_text(encoding="utf-8") == "foreign"
    assert not (
        moved_docset / "assets" / "tappay-backend-20260702-120000"
    ).exists()
    assert json.loads((moved_docset / "docset.json").read_text(encoding="utf-8"))[
        "current_asset"
    ] is None

    monkeypatch.setattr(store, "save_current", original_save_current)


def test_staging_after_namespace_replacement_remains_in_the_pinned_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    docset_dir = paths.docset_dir(tmp_path, "tappay-backend")
    moved_docset = tmp_path / "locked-docset"
    original_validate = store.validate_governance_namespace
    calls = 0

    def replace_after_validation(*args: object, **kwargs: object) -> None:
        nonlocal calls
        original_validate(*args, **kwargs)
        calls += 1
        if calls == 1:
            docset_dir.rename(moved_docset)
            (docset_dir / "assets").mkdir(parents=True)
            (docset_dir / "sentinel.txt").write_text("foreign", encoding="utf-8")

    monkeypatch.setattr(
        store, "validate_governance_namespace", replace_after_validation
    )

    with pytest.raises(FoundryPublicationError, match="namespace changed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )

    assert sorted(
        path.relative_to(docset_dir).as_posix()
        for path in docset_dir.rglob("*")
    ) == ["assets", "sentinel.txt"]
    assert not list((moved_docset / "assets").iterdir())
    assert json.loads((moved_docset / "docset.json").read_text(encoding="utf-8"))[
        "current_asset"
    ] is None


def test_first_approval_pointer_failure_restores_unpublished_heads_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    original_save_current = store.save_current

    def fail_current(*_args: object, **_kwargs: object) -> None:
        raise OSError("current pointer write failed")

    monkeypatch.setattr(store, "save_current", fail_current)
    with pytest.raises(OSError, match="current pointer write failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )

    assert not paths.current_path(tmp_path, "tappay-backend").exists()
    assert store.load_docset(tmp_path, "tappay-backend").current_asset is None
    assert store.load_catalog(tmp_path).docsets[0].current_asset is None
    assert not paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    ).exists()

    monkeypatch.setattr(store, "save_current", original_save_current)
    retried = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    assert retried.asset_id == "tappay-backend-20260702-120000"


def test_rollback_failures_attempt_all_heads_and_surface_original_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)
    attempted: list[str] = []
    original_restore = store.restore_head_relative

    def fail_current(*_args: object, **_kwargs: object) -> None:
        raise OSError("current pointer write failed")

    def restore_head(parent_fd: int, name: str, content: bytes | None) -> None:
        attempted.append(name)
        if name in {"docset.json", "catalog.json"}:
            raise OSError(f"rollback {name} failed")
        original_restore(parent_fd, name, content)

    monkeypatch.setattr(store, "save_current", fail_current)
    monkeypatch.setattr(store, "restore_head_relative", restore_head)

    with pytest.raises(FoundryPublicationError) as caught:
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID_2, approved_by="a", now=_LATER
        )

    assert isinstance(caught.value.__cause__, OSError)
    assert "current pointer write failed" in str(caught.value)
    assert "docset.json" in str(caught.value)
    assert "catalog.json" in str(caught.value)
    assert attempted == ["current.json", "docset.json", "catalog.json"]
    assert (
        paths.docset_dir(tmp_path, "tappay-backend") / ".governance.lock"
    ).is_dir()
    assert (
        paths.foundry_api_root(tmp_path) / ".catalog-governance.lock"
    ).is_dir()
    assert paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260703-093000"
    ).is_dir()
    with pytest.raises(FoundryInputError, match="transaction is already in progress"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID_2, approved_by="a", now=_LATER
        )
    with pytest.raises(FoundryInputError):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_candidate_copy_failure_cleans_asset_for_deterministic_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    asset_root = paths.asset_dir(tmp_path, "tappay-backend", "tappay-backend-20260702-120000")
    original_copytree = store.copy_tree_to_directory

    def fail_copy(_source: Path, destination_fd: int, name: str) -> None:
        store.os.mkdir(name, dir_fd=destination_fd)
        raise OSError("candidate copy failed")

    monkeypatch.setattr(store, "copy_tree_to_directory", fail_copy)
    with pytest.raises(OSError, match="candidate copy failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )
    assert not asset_root.exists()

    monkeypatch.setattr(store, "copy_tree_to_directory", original_copytree)
    retried = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    assert retried.asset_id == "tappay-backend-20260702-120000"


def test_digest_failure_cleans_asset_for_deterministic_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    original_digest = approve.digest_artifact

    def fail_digest(*_args: object, **_kwargs: object) -> str:
        raise FoundryInputError("artifact digest failed")

    monkeypatch.setattr(approve, "digest_artifact", fail_digest)
    with pytest.raises(FoundryInputError, match="artifact digest failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )
    assert not paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    ).exists()

    monkeypatch.setattr(approve, "digest_artifact", original_digest)
    retried = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    assert retried.asset_id == "tappay-backend-20260702-120000"


def test_current_rejects_tampered_governed_strict_companion_artifact(
    tmp_path: Path,
) -> None:
    _setup(tmp_path)
    candidate = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    core_dir = candidate / "core"
    core_dir.mkdir()
    (core_dir / "claims.json").write_text("[]", encoding="utf-8")

    asset = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    governed_claims = (
        paths.asset_artifacts_dir(tmp_path, "tappay-backend", asset.asset_id)
        / "core"
        / "claims.json"
    )
    governed_claims.write_text('[{"tampered": true}]', encoding="utf-8")

    with pytest.raises(FoundryInputError, match="artifact digest is stale: core_claims"):
        query.load_current_asset(tmp_path, "tappay-backend")


def test_strict_release_write_failure_cleans_asset_for_deterministic_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    candidate = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    (candidate / "core").mkdir()

    class _CandidateRelease:
        def model_dump_json(self, **_kwargs: object) -> str:
            return "{}"

    monkeypatch.setattr(
        approve,
        "require_eligible_strict_candidate",
        lambda _candidate: _CandidateRelease(),
    )
    monkeypatch.setattr(
        approve, "approve_release", lambda release, _decision: release
    )
    original_write_model = store.write_model_relative

    def fail_release_write(parent_fd: int, name: str, model: object) -> None:
        if name.endswith("/release.json"):
            raise OSError("strict release write failed")
        original_write_model(parent_fd, name, model)

    monkeypatch.setattr(store, "write_model_relative", fail_release_write)
    with pytest.raises(OSError, match="strict release write failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )
    asset_root = paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    )
    assert not asset_root.exists()
    assert not list(paths.assets_dir(tmp_path, "tappay-backend").glob(".tappay-backend-*"))

    monkeypatch.undo()
    retried = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    assert retried.asset_id == "tappay-backend-20260702-120000"


def test_asset_publication_failure_cleans_stage_for_deterministic_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    original_publish = store.publish_asset

    def fail_publish(*_args: object, **_kwargs: object) -> None:
        raise OSError("asset publication failed")

    monkeypatch.setattr(store, "publish_asset", fail_publish)
    with pytest.raises(OSError, match="asset publication failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
        )
    assets_root = paths.assets_dir(tmp_path, "tappay-backend")
    assert not paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    ).exists()
    assert not list(assets_root.glob(".tappay-backend-20260702-120000-*"))

    monkeypatch.setattr(store, "publish_asset", original_publish)
    retried = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    assert retried.asset_id == "tappay-backend-20260702-120000"


def test_publication_failure_after_rename_cleans_published_root_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    original_publish = store.publish_asset

    def rename_then_fail(
        staged_root: Path, asset_root: Path, **kwargs: object
    ) -> None:
        original_publish(staged_root, asset_root, **kwargs)
        raise OSError("publication durability callback failed")

    monkeypatch.setattr(store, "publish_asset", rename_then_fail)
    with pytest.raises(OSError, match="durability callback failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
        )

    assert not paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    ).exists()
    monkeypatch.setattr(store, "publish_asset", original_publish)
    retried = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
    )
    assert retried.asset_id == "tappay-backend-20260702-120000"


def test_rollback_does_not_delete_a_same_name_foreign_asset_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    asset_root = paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    )
    moved_owned_root = tmp_path / "owned-asset"

    def replace_asset_then_fail(*_args: object, **_kwargs: object) -> None:
        asset_root.rename(moved_owned_root)
        asset_root.mkdir()
        (asset_root / "sentinel.txt").write_text("foreign", encoding="utf-8")
        raise OSError("current pointer write failed")

    monkeypatch.setattr(store, "save_current", replace_asset_then_fail)

    with pytest.raises(
        FoundryPublicationError, match="transaction-owned entry identity changed"
    ):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
        )

    assert (asset_root / "sentinel.txt").read_text(encoding="utf-8") == "foreign"
    assert moved_owned_root.is_dir()
    assert (
        paths.docset_dir(tmp_path, "tappay-backend") / ".governance.lock"
    ).is_dir()
    assert (
        paths.foundry_api_root(tmp_path) / ".catalog-governance.lock"
    ).is_dir()


def test_asset_directory_sync_failure_after_rename_is_reported_and_cleaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    original_fsync = store.os.fsync
    fail_once = True

    def fail_directory_sync(fd: int) -> None:
        nonlocal fail_once
        if fail_once and stat.S_ISDIR(store.os.fstat(fd).st_mode):
            fail_once = False
            raise OSError("asset directory sync failed")
        original_fsync(fd)

    monkeypatch.setattr(store.os, "fsync", fail_directory_sync)
    with pytest.raises(OSError, match="asset directory sync failed"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
        )

    assert not paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    ).exists()


def test_asset_publication_uses_the_pinned_parent_after_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    original_open = store.os.open
    assets_parent = paths.assets_dir(tmp_path, "tappay-backend")
    fail_once = True

    def fail_asset_parent_open(
        path: object, flags: int, *args: object, **kwargs: object
    ) -> int:
        nonlocal fail_once
        if fail_once and Path(path) == assets_parent:
            fail_once = False
            raise OSError("asset parent open failed")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(store.os, "open", fail_asset_parent_open)
    asset = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
    )

    assert asset.asset_id == "tappay-backend-20260702-120000"


def test_lock_cleanup_failure_rolls_back_published_root_and_allows_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    original_rmdir = Path.rmdir

    def fail_governance_lock(path: Path) -> None:
        if path.name == ".governance.lock":
            raise OSError("injected lock cleanup failure")
        original_rmdir(path)

    monkeypatch.setattr(Path, "rmdir", fail_governance_lock)
    with pytest.raises(FoundryPublicationError, match="lock cleanup"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
        )

    assert not paths.asset_dir(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    ).exists()
    assert store.load_docset(tmp_path, "tappay-backend").current_asset is None
    assert store.load_catalog(tmp_path).docsets[0].current_asset is None
    assert not paths.current_path(tmp_path, "tappay-backend").exists()

    monkeypatch.setattr(Path, "rmdir", original_rmdir)
    retried = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="operator", now=_NOW
    )
    assert retried.asset_id == "tappay-backend-20260702-120000"


def test_approve_rejects_tampered_previous_current_before_advancing(
    tmp_path: Path,
) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    current = store.load_current(tmp_path, "tappay-backend")
    assert current is not None
    store.save_current(
        tmp_path,
        "tappay-backend",
        current.model_copy(update={"status": AssetStatus.CANDIDATE}),
    )
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)

    with pytest.raises(FoundryInputError, match="current asset is not approved"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID_2, approved_by="a", now=_LATER
        )

    assert store.load_current(tmp_path, "tappay-backend").current_asset == first.asset_id


def test_legacy_reapproval_requires_explicit_intent_and_preserves_legacy_bytes(
    tmp_path: Path,
) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    legacy_asset_dir = paths.asset_dir(tmp_path, "tappay-backend", first.asset_id)
    asset_payload = json.loads(
        (legacy_asset_dir / "asset.json").read_text(encoding="utf-8")
    )
    for field in ("schema_version", "artifact_digests", "artifact_kinds"):
        asset_payload.pop(field)
    (legacy_asset_dir / "asset.json").write_text(
        json.dumps(asset_payload), encoding="utf-8"
    )
    current_path = paths.current_path(tmp_path, "tappay-backend")
    pointer_payload = json.loads(current_path.read_text(encoding="utf-8"))
    for field in (
        "schema_version",
        "docset_id",
        "asset_digest",
        "artifact_digests",
        "artifact_kinds",
    ):
        pointer_payload.pop(field)
    current_path.write_text(json.dumps(pointer_payload), encoding="utf-8")
    legacy_bytes = {
        path.relative_to(legacy_asset_dir): path.read_bytes()
        for path in legacy_asset_dir.rglob("*")
        if path.is_file()
    }
    legacy_current_sha256 = hashlib.sha256(current_path.read_bytes()).hexdigest()
    legacy_asset_sha256 = hashlib.sha256(
        (legacy_asset_dir / "asset.json").read_bytes()
    ).hexdigest()

    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)
    with pytest.raises(FoundryInputError, match="current.json is invalid"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID_2, approved_by="a", now=_LATER
        )

    with pytest.raises(FoundryInputError, match="trusted digest"):
        approve.approve_candidate(
            tmp_path,
            "tappay-backend",
            _RUN_ID_2,
            approved_by="migration-operator",
            now=_LATER,
            reapprove_legacy=True,
        )

    migrated = approve.approve_candidate(
        tmp_path,
        "tappay-backend",
        _RUN_ID_2,
        approved_by="migration-operator",
        now=_LATER,
        reapprove_legacy=True,
        legacy_current_sha256=legacy_current_sha256,
        legacy_asset_sha256=legacy_asset_sha256,
    )

    assert migrated.schema_version == "normative-asset/v1"
    assert migrated.supersedes == first.asset_id
    assert query.load_current_asset(tmp_path, "tappay-backend").asset_id == migrated.asset_id
    assert {
        path.relative_to(legacy_asset_dir): path.read_bytes()
        for path in legacy_asset_dir.rglob("*")
        if path.is_file()
    } == legacy_bytes


def test_legacy_reapproval_flag_rejects_an_already_v1_current(tmp_path: Path) -> None:
    _setup(tmp_path)
    approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)
    current_path = paths.current_path(tmp_path, "tappay-backend")
    asset_path = paths.asset_manifest_path(
        tmp_path, "tappay-backend", "tappay-backend-20260702-120000"
    )

    with pytest.raises(FoundryInputError, match="unversioned"):
        approve.approve_candidate(
            tmp_path,
            "tappay-backend",
            _RUN_ID_2,
            approved_by="migration-operator",
            now=_LATER,
            reapprove_legacy=True,
            legacy_current_sha256=hashlib.sha256(current_path.read_bytes()).hexdigest(),
            legacy_asset_sha256=hashlib.sha256(asset_path.read_bytes()).hexdigest(),
        )


def test_legacy_reapproval_checks_trusted_bytes_before_legacy_parsing(tmp_path: Path) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    asset_path = paths.asset_manifest_path(tmp_path, "tappay-backend", first.asset_id)
    current_path = paths.current_path(tmp_path, "tappay-backend")
    asset_path.write_text("not-json", encoding="utf-8")
    current_path.write_text("not-json", encoding="utf-8")
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)

    with pytest.raises(FoundryInputError, match="trusted digest mismatch"):
        approve.approve_candidate(
            tmp_path,
            "tappay-backend",
            _RUN_ID_2,
            approved_by="migration-operator",
            now=_LATER,
            reapprove_legacy=True,
            legacy_current_sha256="0" * 64,
            legacy_asset_sha256="0" * 64,
        )


def test_legacy_reapproval_parses_single_captured_record_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    asset_path = paths.asset_manifest_path(tmp_path, "tappay-backend", first.asset_id)
    current_path = paths.current_path(tmp_path, "tappay-backend")
    asset_payload = json.loads(asset_path.read_text(encoding="utf-8"))
    for field in ("schema_version", "artifact_digests", "artifact_kinds"):
        asset_payload.pop(field)
    asset_path.write_text(json.dumps(asset_payload), encoding="utf-8")
    pointer_payload = json.loads(current_path.read_text(encoding="utf-8"))
    for field in (
        "schema_version",
        "docset_id",
        "asset_digest",
        "artifact_digests",
        "artifact_kinds",
    ):
        pointer_payload.pop(field)
    current_path.write_text(json.dumps(pointer_payload), encoding="utf-8")
    original_current = current_path.read_bytes()
    original_asset = asset_path.read_bytes()
    current_digest = hashlib.sha256(original_current).hexdigest()
    asset_digest = hashlib.sha256(original_asset).hexdigest()
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)

    original_read_bytes = Path.read_bytes
    reads: dict[Path, int] = {current_path: 0, asset_path: 0}

    def read_once(path: Path) -> bytes:
        if path not in reads:
            return original_read_bytes(path)
        reads[path] += 1
        raw = original_read_bytes(path)
        if path == asset_path:
            # A later filesystem read would observe corruption; the approval
            # must continue using the already captured buffers.
            current_path.write_bytes(b"not-json")
            asset_path.write_bytes(b"not-json")
        return raw

    monkeypatch.setattr(Path, "read_bytes", read_once)
    try:
        migrated = approve.approve_candidate(
            tmp_path,
            "tappay-backend",
            _RUN_ID_2,
            approved_by="migration-operator",
            now=_LATER,
            reapprove_legacy=True,
            legacy_current_sha256=current_digest,
            legacy_asset_sha256=asset_digest,
        )
    finally:
        current_path.write_bytes(original_current)
        asset_path.write_bytes(original_asset)

    assert migrated.supersedes == first.asset_id
    assert reads == {current_path: 1, asset_path: 1}


def test_legacy_reapproval_rejects_pointer_asset_summary_drift(tmp_path: Path) -> None:
    _setup(tmp_path)
    first = approve.approve_candidate(
        tmp_path, "tappay-backend", _RUN_ID, approved_by="a", now=_NOW
    )
    asset_path = paths.asset_manifest_path(tmp_path, "tappay-backend", first.asset_id)
    asset_payload = json.loads(asset_path.read_text(encoding="utf-8"))
    for field in ("schema_version", "artifact_digests", "artifact_kinds"):
        asset_payload.pop(field)
    asset_path.write_text(json.dumps(asset_payload), encoding="utf-8")
    current_path = paths.current_path(tmp_path, "tappay-backend")
    pointer_payload = json.loads(current_path.read_text(encoding="utf-8"))
    for field in (
        "schema_version",
        "docset_id",
        "asset_digest",
        "artifact_digests",
        "artifact_kinds",
    ):
        pointer_payload.pop(field)
    pointer_payload["validation"]["score"] = 0
    current_path.write_text(json.dumps(pointer_payload), encoding="utf-8")
    legacy_current_sha256 = hashlib.sha256(current_path.read_bytes()).hexdigest()
    legacy_asset_sha256 = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    run_dir2 = write_run_dir(tmp_path / "output" / _RUN_ID_2)
    importer.import_run(tmp_path, "tappay-backend", run_dir2)

    with pytest.raises(FoundryInputError, match="summary is stale"):
        approve.approve_candidate(
            tmp_path,
            "tappay-backend",
            _RUN_ID_2,
            approved_by="migration-operator",
            now=_LATER,
            reapprove_legacy=True,
            legacy_current_sha256=legacy_current_sha256,
            legacy_asset_sha256=legacy_asset_sha256,
        )


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


def test_approve_never_overrides_ineligible_strict_execution(tmp_path: Path) -> None:
    _setup(tmp_path, validation_ok=False)
    candidate = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    core_dir = candidate / "core"
    core_dir.mkdir()
    (core_dir / "execution.json").write_text(
        json.dumps(
            {
                "mode": "strict",
                "blocking": True,
                "legacy_status": "passed",
                "core_verdict": "reject",
                "exact_supported_claims": 0,
                "candidate_eligible": False,
                "approval_requests": 0,
                "artifact_publications": 0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(FoundryApprovalError, match="strict Core execution"):
        approve.approve_candidate(
            tmp_path,
            "tappay-backend",
            _RUN_ID,
            approved_by="a",
            now=_NOW,
            allow_failing=True,
        )


def test_approve_refuses_below_min_score(tmp_path: Path) -> None:
    _setup(tmp_path, score=70)
    with pytest.raises(FoundryApprovalError, match="score"):
        approve.approve_candidate(
            tmp_path, "tappay-backend", _RUN_ID, approved_by="ci-score-90", now=_NOW, min_score=90
        )
