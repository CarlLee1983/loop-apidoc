from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from loop_apidoc.diff.loader import DiffInputError, load_run_artifacts
from loop_apidoc.foundry.strict_artifacts import (
    StrictCoreExecutionError,
    require_eligible_strict_candidate,
)
from . import (
    descriptor_namespace,
    descriptor_tree,
    governed,
    head_io,
    paths,
    store,
)
from loop_apidoc.foundry.models import Docset, FoundryInputError, FoundryPublicationError


@dataclass(frozen=True)
class ImportResult:
    run_id: str
    candidate_dir: Path


@dataclass(frozen=True)
class _BackupQuarantine:
    """A predecessor retained until this overwrite has definitely committed."""

    original_name: str
    quarantine_name: str
    identity: tuple[int, int]


def import_run(
    project_root: Path,
    docset_id: str,
    run_dir: Path,
    *,
    overwrite: bool = False,
) -> ImportResult:
    # Reuse the diff loader as the completeness gate for a run dir.
    try:
        load_run_artifacts(run_dir)
    except DiffInputError as exc:
        raise FoundryInputError(f"run directory is not a valid run: {exc}") from exc
    try:
        require_eligible_strict_candidate(run_dir)
    except StrictCoreExecutionError as exc:
        raise FoundryInputError(str(exc)) from exc

    run_id = run_dir.name
    _require_safe_run_id(run_id)
    transaction = store.begin_governance_transaction(
        project_root, docset_id, create_assets=False
    )
    candidates_fd = stage_fd = -1
    stage_name: str | None = None
    stage_identity: tuple[int, int] | None = None
    prior_identity: tuple[int, int] | None = None
    backup_name: str | None = None
    backup_identity: tuple[int, int] | None = None
    pruned_backups: list[_BackupQuarantine] = []
    docset_snapshot: head_io.HeadSnapshot | None = None
    try:
        docset_snapshot, docset = head_io.read_head_model_snapshot_relative(
            transaction.docset_fd,
            Docset,
            "docset.json",
            "docset.json",
        )
        if docset.docset_id != docset_id:
            raise FoundryInputError("governance docset identity is stale")
        candidates_fd = descriptor_namespace.ensure_directory_relative(
            transaction.docset_fd, "candidates"
        )
        transaction.own_fd(candidates_fd)
        prior_identity = descriptor_namespace.entry_identity_relative(candidates_fd, run_id)
        if prior_identity is not None and not overwrite:
            raise FoundryInputError(f"candidate already exists: {run_id}")
        _finalize_stale_backup_quarantines(candidates_fd, run_id)
        try:
            stage_name, stage_fd, stage_identity = descriptor_tree.copy_tree_to_owned_directory(
                run_dir,
                candidates_fd,
                prefix=f".{run_id}-stage-",
            )
        except (FoundryInputError, OSError) as exc:
            raise FoundryInputError("candidate import staging failed") from exc
        transaction.own_fd(stage_fd)
        stage_path = descriptor_namespace.directory_fd_path(stage_fd)
        try:
            load_run_artifacts(stage_path)
            require_eligible_strict_candidate(stage_path)
        except (DiffInputError, StrictCoreExecutionError) as exc:
            raise FoundryInputError(
                "staged candidate is not a complete eligible run"
            ) from exc

        if prior_identity is not None:
            _quarantine_stale_backups(candidates_fd, run_id, pruned_backups)
            backup_name = _next_backup_name(candidates_fd, run_id)
            backup_identity = descriptor_namespace.move_owned_directory_relative(
                candidates_fd,
                run_id,
                backup_name,
                prior_identity,
            )
        assert docset_snapshot is not None
        head_io.validate_head_snapshot_relative(
            transaction.docset_fd,
            "docset.json",
            docset_snapshot,
        )
        publication = store.publish_asset(
            Path(stage_name),
            Path(run_id),
            parent_fd=candidates_fd,
            expected_identity=stage_identity,
        )
        assert publication.identity == stage_identity
        descriptor_namespace.validate_directory_relative(
            transaction.docset_fd, "candidates", candidates_fd
        )
        head_io.validate_head_snapshot_relative(
            transaction.docset_fd,
            "docset.json",
            docset_snapshot,
        )
        governed.validate_governance_namespace(
            transaction.project_root,
            docset_id,
            root_fd=transaction.root_fd,
            api_fd=transaction.api_fd,
            docset_fd=transaction.docset_fd,
            assets_fd=transaction.assets_fd,
        )
        # Durable publication is complete before retired predecessors receive
        # best-effort, identity-pinned cleanup outside this transaction.
        transaction.close()
    except BaseException as primary:
        try:
            backup_identity = _reconcile_backup_for_rollback(
                candidates_fd,
                run_id,
                prior_identity,
                backup_name,
                backup_identity,
            )
            _rollback_candidate_import(
                candidates_fd,
                run_id,
                prior_identity,
                stage_name,
                stage_identity,
                backup_name,
                backup_identity,
            )
            _restore_quarantined_backups(candidates_fd, pruned_backups)
        except BaseException as cleanup_error:
            transaction.abandon()
            failure = FoundryPublicationError(
                "candidate import failed and recovery is required: "
                f"{cleanup_error}"
            )
            failure.recovery_required = True  # type: ignore[attr-defined]
            raise failure from primary
        try:
            transaction.close()
        except FoundryPublicationError:
            transaction.force_close()
        raise
    _finalize_backup_quarantines(project_root, docset_id, run_id, pruned_backups)
    return ImportResult(
        run_id=run_id,
        candidate_dir=paths.candidate_dir(project_root, docset_id, run_id),
    )


def _require_safe_run_id(run_id: str) -> None:
    if not run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise FoundryInputError("unsafe run id")


def _next_backup_name(candidates_fd: int, run_id: str) -> str:
    for _ in range(100):
        candidate = f".{run_id}-backup-{uuid.uuid4().hex}"
        if descriptor_namespace.entry_identity_relative(candidates_fd, candidate) is None:
            return candidate
    raise FoundryPublicationError("cannot allocate candidate backup directory")


def _quarantine_stale_backups(
    candidates_fd: int,
    run_id: str,
    quarantines: list[_BackupQuarantine],
) -> None:
    """Retire prior backups reversibly until the overwrite has committed."""
    prefix = f".{run_id}-backup-"
    for name in os.listdir(candidates_fd):
        if not name.startswith(prefix) or name == prefix:
            continue
        identity = descriptor_namespace.entry_identity_relative(candidates_fd, name)
        if identity is not None:
            quarantine_name = _next_backup_quarantine_name(candidates_fd, run_id)
            descriptor_namespace.move_owned_directory_relative(
                candidates_fd,
                name,
                quarantine_name,
                identity,
            )
            quarantines.append(
                _BackupQuarantine(name, quarantine_name, identity)
            )


def _next_backup_quarantine_name(candidates_fd: int, run_id: str) -> str:
    for _ in range(100):
        candidate = f".{run_id}-backup-prune-{uuid.uuid4().hex}"
        if descriptor_namespace.entry_identity_relative(candidates_fd, candidate) is None:
            return candidate
    raise FoundryPublicationError("cannot allocate candidate backup quarantine")


def _restore_quarantined_backups(
    candidates_fd: int,
    quarantines: list[_BackupQuarantine],
) -> None:
    """Undo reversible predecessor retirement after an uncommitted overwrite."""
    for quarantine in reversed(quarantines):
        descriptor_namespace.move_owned_directory_relative(
            candidates_fd,
            quarantine.quarantine_name,
            quarantine.original_name,
            quarantine.identity,
        )


def _finalize_stale_backup_quarantines(candidates_fd: int, run_id: str) -> None:
    """Collect leftovers from a previously committed post-close cleanup."""
    prefix = f".{run_id}-backup-prune-"
    for name in os.listdir(candidates_fd):
        if not name.startswith(prefix) or name == prefix:
            continue
        identity = descriptor_namespace.entry_identity_relative(candidates_fd, name)
        if identity is not None:
            descriptor_namespace.remove_owned_entry_relative(candidates_fd, name, identity)


def _finalize_backup_quarantines(
    project_root: Path,
    docset_id: str,
    run_id: str,
    quarantines: list[_BackupQuarantine],
) -> None:
    """Best-effort post-commit cleanup that can never roll back a publication."""
    if not quarantines:
        return
    try:
        with governed.open_governed_docset(project_root, docset_id) as governed_docset:
            with governed_docset.open_directory("candidates") as candidates:
                for quarantine in quarantines:
                    descriptor_namespace.remove_owned_entry_relative(
                        candidates.descriptor,
                        quarantine.quarantine_name,
                        quarantine.identity,
                    )
                candidates.validate()
            governed_docset.validate()
    except (FoundryInputError, FoundryPublicationError, OSError):
        # The import has already committed. Leave an identity-pinned hidden
        # quarantine for the next transaction rather than reporting a false
        # failure or attempting a second unprotected candidate mutation.
        return


def _next_recovery_name(candidates_fd: int, run_id: str) -> str:
    for _ in range(100):
        candidate = f".{run_id}-recovery-{uuid.uuid4().hex}"
        if descriptor_namespace.entry_identity_relative(candidates_fd, candidate) is None:
            return candidate
    raise FoundryPublicationError("cannot allocate candidate recovery directory")


def _reconcile_backup_for_rollback(
    candidates_fd: int,
    run_id: str,
    prior_identity: tuple[int, int] | None,
    backup_name: str | None,
    backup_identity: tuple[int, int] | None,
) -> tuple[int, int] | None:
    """Recover an old-candidate identity if its move failed after rename."""
    if (
        candidates_fd < 0
        or prior_identity is None
        or backup_name is None
        or backup_identity is not None
    ):
        return backup_identity
    observed_backup = descriptor_namespace.entry_identity_relative(candidates_fd, backup_name)
    if observed_backup == prior_identity:
        return observed_backup
    observed_current = descriptor_namespace.entry_identity_relative(candidates_fd, run_id)
    if observed_backup is None and observed_current == prior_identity:
        return None
    raise FoundryPublicationError(
        "candidate backup state changed before failed import could be rolled back"
    )


def _rollback_candidate_import(
    candidates_fd: int,
    run_id: str,
    prior_identity: tuple[int, int] | None,
    stage_name: str | None,
    stage_identity: tuple[int, int] | None,
    backup_name: str | None,
    backup_identity: tuple[int, int] | None,
) -> None:
    if candidates_fd < 0:
        return
    if stage_identity is not None:
        current_identity = descriptor_namespace.entry_identity_relative(candidates_fd, run_id)
        if current_identity == stage_identity:
            descriptor_namespace.remove_owned_entry_relative(candidates_fd, run_id, stage_identity)
        elif current_identity is not None and current_identity != prior_identity:
            recovery_name = _next_recovery_name(candidates_fd, run_id)
            descriptor_namespace.move_owned_directory_relative(
                candidates_fd,
                run_id,
                recovery_name,
                current_identity,
            )
            if backup_name is not None and backup_identity is not None:
                descriptor_namespace.move_owned_directory_relative(
                    candidates_fd,
                    backup_name,
                    run_id,
                    backup_identity,
                )
                backup_name = None
                backup_identity = None
            failure = FoundryPublicationError(
                "candidate destination changed; quarantined output requires "
                "recovery"
            )
            failure.recovery_required = True  # type: ignore[attr-defined]
            raise failure
        if stage_name is not None:
            descriptor_namespace.remove_owned_entry_relative(candidates_fd, stage_name, stage_identity)
    if backup_name is not None and backup_identity is not None:
        descriptor_namespace.move_owned_directory_relative(
            candidates_fd,
            backup_name,
            run_id,
            backup_identity,
        )
