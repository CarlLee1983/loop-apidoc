from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path

import pytest

from loop_apidoc.foundry import importer, paths, register, store
from loop_apidoc.foundry.models import (
    Docset,
    FoundryInputError,
    FoundryPublicationError,
)
from tests.foundry._fixtures import write_run_dir

_RUN_ID = "20260702T120000.000000Z"


def _register(tmp_path: Path) -> None:
    register.register_docset(
        tmp_path,
        Docset(docset_id="tappay-backend", title="T", provider="tappay", product="backend-api"),
    )


def test_import_copies_run_into_candidate(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)

    result = importer.import_run(tmp_path, "tappay-backend", run_dir)

    assert result.run_id == _RUN_ID
    dest = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    assert result.candidate_dir == dest
    assert (dest / "openapi.yaml").is_file()
    assert (dest / "validation" / "report.json").is_file()
    assert (dest / "handoff" / "sdk-hints.json").is_file()


def test_import_missing_docset_raises(tmp_path: Path) -> None:
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    with pytest.raises(FoundryInputError, match="docset.json"):
        importer.import_run(tmp_path, "nope", run_dir)


def test_import_revalidates_docset_inside_the_pinned_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-lock docset check cannot authorize a substituted destination."""
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    docset_dir = paths.docset_dir(tmp_path, "tappay-backend")
    foreign_docset = tmp_path / "foreign-docset"
    moved_docset = tmp_path / "moved-docset"
    shutil.copytree(docset_dir, foreign_docset)
    (foreign_docset / "docset.json").unlink()
    original_begin = store.begin_governance_transaction
    swapped = False

    def substitute_then_begin(*args: object, **kwargs: object) -> store.GovernanceTransaction:
        nonlocal swapped
        if not swapped:
            docset_dir.rename(moved_docset)
            foreign_docset.rename(docset_dir)
            swapped = True
        return original_begin(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(store, "begin_governance_transaction", substitute_then_begin)

    with pytest.raises(FoundryInputError, match="docset.json"):
        importer.import_run(tmp_path, "tappay-backend", run_dir)

    assert swapped
    assert not (docset_dir / "candidates" / _RUN_ID).exists()


def test_import_incomplete_run_raises(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    (run_dir / "openapi.yaml").unlink()
    with pytest.raises(FoundryInputError, match="openapi.yaml"):
        importer.import_run(tmp_path, "tappay-backend", run_dir)


def test_import_rejects_ineligible_strict_core_execution(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    core_dir = run_dir / "core"
    core_dir.mkdir()
    (core_dir / "execution.json").write_text(
        json.dumps(
            {
                "mode": "strict",
                "blocking": True,
                "legacy_status": "passed",
                "core_verdict": "accept",
                "exact_supported_claims": 0,
                "candidate_eligible": False,
                "approval_requests": 0,
                "artifact_publications": 0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(FoundryInputError, match="strict Core execution"):
        importer.import_run(tmp_path, "tappay-backend", run_dir)


def test_import_duplicate_candidate_raises_without_overwrite(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    with pytest.raises(FoundryInputError, match="candidate already exists"):
        importer.import_run(tmp_path, "tappay-backend", run_dir)


def test_import_overwrite_replaces_candidate(tmp_path: Path) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    result = importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)
    assert result.candidate_dir.is_dir()


def test_import_overwrite_keeps_old_candidate_when_staged_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    destination = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    destination_openapi = destination / "openapi.yaml"
    destination_openapi.write_text("old candidate", encoding="utf-8")

    def fail_copy(*args: object, **kwargs: object) -> object:
        raise OSError("injected candidate copy failure")

    monkeypatch.setattr(
        store, "copy_tree_to_owned_directory", fail_copy, raising=False
    )

    with pytest.raises(FoundryInputError, match="candidate import"):
        importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)

    assert destination_openapi.read_text(encoding="utf-8") == "old candidate"
    entry_names = {entry.name for entry in destination.parent.iterdir()}
    assert _RUN_ID in entry_names
    assert all(name == _RUN_ID or "-cleanup-" in name for name in entry_names)


def test_import_overwrite_restores_old_candidate_when_publication_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    destination = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    destination_openapi = destination / "openapi.yaml"
    destination_openapi.write_text("old candidate", encoding="utf-8")

    def fail_publication(*args: object, **kwargs: object) -> object:
        raise FoundryPublicationError("injected candidate publication failure")

    monkeypatch.setattr(store, "publish_asset", fail_publication)

    with pytest.raises(FoundryPublicationError, match="injected candidate publication"):
        importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)

    assert destination_openapi.read_text(encoding="utf-8") == "old candidate"
    entry_names = {entry.name for entry in destination.parent.iterdir()}
    assert _RUN_ID in entry_names
    assert all(name == _RUN_ID or "-cleanup-" in name for name in entry_names)


def test_overwrite_failure_restores_the_previously_retained_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed overwrite must put both generations back exactly as it found them."""
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    destination = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    (destination / "openapi.yaml").write_text("first current", encoding="utf-8")
    importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)
    retained_backup = next(destination.parent.glob(f".{_RUN_ID}-backup-*"))
    retained_name = retained_backup.name
    retained_bytes = (retained_backup / "openapi.yaml").read_bytes()
    (destination / "openapi.yaml").write_text("second current", encoding="utf-8")

    def fail_publication(*args: object, **kwargs: object) -> object:
        raise FoundryPublicationError("injected post-retirement publication failure")

    monkeypatch.setattr(store, "publish_asset", fail_publication)

    with pytest.raises(FoundryPublicationError, match="post-retirement publication"):
        importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)

    assert (destination / "openapi.yaml").read_text(encoding="utf-8") == "second current"
    restored_backup = destination.parent / retained_name
    assert restored_backup.is_dir()
    assert (restored_backup / "openapi.yaml").read_bytes() == retained_bytes


def test_import_overwrite_restores_old_candidate_after_backup_move_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    destination = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    destination_openapi = destination / "openapi.yaml"
    destination_openapi.write_text("old candidate", encoding="utf-8")
    original_move = store.move_owned_directory_relative

    def move_then_fail(
        parent_fd: int,
        source: str,
        destination_name: str,
        identity: tuple[int, int],
    ) -> tuple[int, int]:
        result = original_move(parent_fd, source, destination_name, identity)
        if source == _RUN_ID:
            raise FoundryPublicationError("injected post-rename backup failure")
        return result

    monkeypatch.setattr(store, "move_owned_directory_relative", move_then_fail)

    with pytest.raises(FoundryPublicationError, match="post-rename backup failure"):
        importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)

    assert destination_openapi.read_text(encoding="utf-8") == "old candidate"
    entry_names = {entry.name for entry in destination.parent.iterdir()}
    assert _RUN_ID in entry_names
    assert all(name == _RUN_ID or "-cleanup-" in name for name in entry_names)


def test_import_retains_governance_lock_when_staged_candidate_is_swapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    candidates = paths.docset_dir(tmp_path, "tappay-backend") / "candidates"
    original_rename = store._rename_noreplace
    swapped = False

    def replace_stage_before_publish(
        staged: Path, destination: Path, *, parent_fd: int | None = None
    ) -> None:
        nonlocal swapped
        if parent_fd is not None and staged.name.startswith(f".{_RUN_ID}-stage-"):
            swapped = True
            os.rename(
                staged.name,
                ".attacker-staging",
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.mkdir(staged.name, dir_fd=parent_fd)
            stage_fd = os.open(
                staged.name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                dir_fd=parent_fd,
            )
            try:
                marker_fd = os.open(
                    "attacker.txt",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=stage_fd,
                )
                os.close(marker_fd)
            finally:
                os.close(stage_fd)
        original_rename(staged, destination, parent_fd=parent_fd)

    monkeypatch.setattr(store, "_rename_noreplace", replace_stage_before_publish)

    with pytest.raises(FoundryPublicationError, match="recovery is required"):
        importer.import_run(tmp_path, "tappay-backend", run_dir)

    assert swapped
    assert not (candidates / _RUN_ID).exists()
    recoveries = sorted(candidates.glob(f".{_RUN_ID}-recovery-*"))
    assert len(recoveries) == 1
    assert (recoveries[0] / "attacker.txt").is_file()
    assert (paths.docset_dir(tmp_path, "tappay-backend") / ".governance.lock").is_dir()
    assert (tmp_path / ".foundry/api/.catalog-governance.lock").is_dir()


def test_import_overwrite_restores_old_candidate_when_lock_close_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    destination = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    destination_openapi = destination / "openapi.yaml"
    destination_openapi.write_text("old candidate", encoding="utf-8")
    original_close = store.GovernanceTransaction.close
    attempts = 0

    def fail_once_close(transaction: store.GovernanceTransaction) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise FoundryPublicationError("injected governance close failure")
        original_close(transaction)

    monkeypatch.setattr(store.GovernanceTransaction, "close", fail_once_close)

    with pytest.raises(FoundryPublicationError, match="injected governance close"):
        importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)

    assert destination_openapi.read_text(encoding="utf-8") == "old candidate"
    entry_names = {entry.name for entry in destination.parent.iterdir()}
    assert _RUN_ID in entry_names
    assert all(name == _RUN_ID or "-cleanup-" in name for name in entry_names)


def test_import_overwrite_retains_old_candidate_backup_after_commit(
    tmp_path: Path,
) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    destination = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    destination_openapi = destination / "openapi.yaml"
    destination_openapi.write_text("old candidate", encoding="utf-8")
    assert importer.import_run(
        tmp_path, "tappay-backend", run_dir, overwrite=True
    ).run_id == _RUN_ID

    assert destination_openapi.read_text(encoding="utf-8") != "old candidate"
    backups = sorted(destination.parent.glob(f".{_RUN_ID}-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "openapi.yaml").read_text(encoding="utf-8") == "old candidate"
    assert not (paths.docset_dir(tmp_path, "tappay-backend") / ".governance.lock").exists()
    assert not (tmp_path / ".foundry/api/.catalog-governance.lock").exists()


def test_repeated_overwrites_retain_only_the_immediate_predecessor(
    tmp_path: Path,
) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    destination = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)

    (destination / "openapi.yaml").write_text("first predecessor", encoding="utf-8")
    importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)
    (destination / "openapi.yaml").write_text("immediate predecessor", encoding="utf-8")
    importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)

    backups = sorted(destination.parent.glob(f".{_RUN_ID}-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "openapi.yaml").read_text(encoding="utf-8") == (
        "immediate predecessor"
    )


def test_overwrite_prunes_only_exact_stale_backups_without_following_symlink(
    tmp_path: Path,
) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    destination = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    candidates = destination.parent
    stale_backup = candidates / f".{_RUN_ID}-backup-stale"
    stale_backup.mkdir()
    retained_sentinel = tmp_path / "retained-sentinel"
    retained_sentinel.mkdir()
    (retained_sentinel / "must-survive").write_text("sentinel", encoding="utf-8")
    symlink_backup = candidates / f".{_RUN_ID}-backup-linked"
    symlink_backup.symlink_to(retained_sentinel, target_is_directory=True)
    unrelated = candidates / f".{_RUN_ID}-backupish"
    unrelated.mkdir()

    importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)

    backups = sorted(candidates.glob(f".{_RUN_ID}-backup-*"))
    assert len(backups) == 1
    assert stale_backup not in backups
    assert symlink_backup not in backups
    assert (retained_sentinel / "must-survive").read_text(encoding="utf-8") == "sentinel"
    assert unrelated.is_dir()


def test_overwrite_preserves_current_candidate_when_backup_retirement_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    importer.import_run(tmp_path, "tappay-backend", run_dir)
    destination = paths.candidate_dir(tmp_path, "tappay-backend", _RUN_ID)
    (destination / "openapi.yaml").write_text("current candidate", encoding="utf-8")
    stale_backup = destination.parent / f".{_RUN_ID}-backup-stale"
    stale_backup.mkdir()
    original_move = store.move_owned_directory_relative

    def fail_stale_retirement(
        parent_fd: int,
        source: str,
        destination: str,
        identity: tuple[int, int],
    ) -> tuple[int, int]:
        if source == stale_backup.name:
            raise FoundryPublicationError("injected stale backup retirement failure")
        return original_move(parent_fd, source, destination, identity)

    monkeypatch.setattr(store, "move_owned_directory_relative", fail_stale_retirement)

    with pytest.raises(FoundryPublicationError, match="stale backup retirement"):
        importer.import_run(tmp_path, "tappay-backend", run_dir, overwrite=True)

    assert (destination / "openapi.yaml").read_text(encoding="utf-8") == (
        "current candidate"
    )
    assert stale_backup.is_dir()


def test_import_rejects_a_concurrent_same_docset_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(tmp_path)
    run_dir = write_run_dir(tmp_path / "output" / _RUN_ID)
    entered = threading.Event()
    release = threading.Event()
    original_copy = store.copy_tree_to_owned_directory
    outcome: dict[str, object] = {}

    def pause_copy(*args: object, **kwargs: object) -> object:
        entered.set()
        assert release.wait(timeout=5)
        return original_copy(*args, **kwargs)

    monkeypatch.setattr(store, "copy_tree_to_owned_directory", pause_copy)

    def first_import() -> None:
        try:
            outcome["result"] = importer.import_run(
                tmp_path, "tappay-backend", run_dir
            )
        except BaseException as exc:  # surfaced below so the thread cannot mask it
            outcome["error"] = exc

    thread = threading.Thread(target=first_import)
    thread.start()
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(FoundryInputError, match="already in progress"):
            importer.import_run(tmp_path, "tappay-backend", run_dir)
    finally:
        release.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert "error" not in outcome
    assert isinstance(outcome.get("result"), importer.ImportResult)
