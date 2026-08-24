"""Atomic mutable-head snapshots and rollback for Foundry persistence."""

from __future__ import annotations

import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from loop_apidoc.foundry import descriptor_namespace
from loop_apidoc.foundry.models import FoundryInputError, FoundryPublicationError

_ModelT = TypeVar("_ModelT", bound=BaseModel)


@dataclass(slots=True)
class HeadSnapshot:
    """One head's original bytes and any transaction-owned replacement inode."""

    content: bytes | None
    original_identity: tuple[int, int] | None
    published_identity: tuple[int, int] | None = None

@dataclass
class _RollbackEntryPublication:
    """Tracks a temporary rollback file that this transaction linked."""

    owned_entry: bool = False
    identity: tuple[int, int] | None = None


def _capture_mutable_head_snapshot(
    parent_fd: int,
    basename: str,
    name: str,
    outcome: HeadSnapshot | None,
) -> HeadSnapshot:
    """Capture the exact mutable head a replacement is allowed to supersede."""
    observed = read_head_snapshot_relative(parent_fd, basename)
    if outcome is None:
        outcome = observed
    elif (
        observed.original_identity != outcome.original_identity
        or observed.content != outcome.content
    ):
        raise FoundryPublicationError(
            f"governance head identity changed before publication: {name}"
        )
    outcome.published_identity = None
    return outcome


def _publish_temporary_head_relative(
    parent_fd: int,
    basename: str,
    temporary_name: str,
    identity: tuple[int, int],
    snapshot: HeadSnapshot,
    *,
    name: str,
) -> None:
    """CAS-publish a temporary regular file without clobbering a substitute.

    POSIX has no ``rename(expected_inode=...)`` primitive.  Move the expected
    head to a unique quarantine first, verify that the moved inode is the one
    captured by the snapshot, and only then link the new inode into the now
    absent canonical name.  Any replacement in either gap remains visible and
    the old head is restored only when that name is still absent.
    """
    expected = snapshot.original_identity
    if expected is None:
        try:
            os.link(
                temporary_name,
                basename,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise FoundryPublicationError(
                f"governance head identity changed during publication: {name}"
            ) from exc
        if descriptor_namespace.entry_identity_relative(parent_fd, basename) != identity:
            raise _rollback_recovery_error(
                f"governance head identity changed during publication: {name}"
            )
        snapshot.published_identity = identity
        return

    if descriptor_namespace.entry_identity_relative(parent_fd, basename) != expected:
        raise FoundryPublicationError(
            f"governance head identity changed before publication: {name}"
        )
    quarantine = f".{basename}-replace-{uuid.uuid4().hex}"
    try:
        descriptor_namespace._rename_noreplace(
            Path(basename), Path(quarantine), parent_fd=parent_fd
        )
    except OSError as exc:
        raise FoundryPublicationError(
            f"governance head move failed during publication: {name}"
        ) from exc

    moved = descriptor_namespace.entry_identity_relative(parent_fd, quarantine)
    if moved != expected:
        try:
            _return_quarantined_head(parent_fd, quarantine, basename)
        except BaseException as recovery_error:
            raise _rollback_recovery_error(
                f"governance head identity changed during publication: {name}",
                recovery_error,
            ) from recovery_error
        raise FoundryPublicationError(
            f"governance head identity changed during publication: {name}"
        )

    try:
        os.link(
            temporary_name,
            basename,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except BaseException as primary:
        try:
            _return_quarantined_head(parent_fd, quarantine, basename)
        except BaseException as recovery_error:
            raise _rollback_recovery_error(
                f"governance head rollback recovery is required: {name}",
                recovery_error,
            ) from primary
        if isinstance(primary, FileExistsError):
            raise FoundryPublicationError(
                f"governance head identity changed during publication: {name}"
            ) from primary
        raise

    if descriptor_namespace.entry_identity_relative(parent_fd, basename) != identity:
        raise _rollback_recovery_error(
            f"governance head identity changed during publication: {name}"
        )
    snapshot.published_identity = identity
    try:
        descriptor_namespace.remove_owned_entry_relative(parent_fd, quarantine, expected)
    except BaseException as exc:
        raise _rollback_recovery_error(
            f"governance head replacement cleanup failed: {name}", exc
        ) from exc


def _atomic_write_model_relative(
    parent_fd: int,
    name: str,
    model: BaseModel,
    *,
    prefix: str,
    outcome: HeadSnapshot | None = None,
) -> tuple[int, int]:
    """Atomically replace one governed JSON head relative to a held directory fd."""
    resolved_parent_fd, basename = descriptor_namespace._open_relative_parent(
        parent_fd, name
    )
    temporary_name = f"{prefix}{uuid.uuid4().hex}.tmp"
    descriptor = -1
    identity: tuple[int, int] | None = None
    snapshot: HeadSnapshot | None = None
    try:
        snapshot = _capture_mutable_head_snapshot(
            resolved_parent_fd, basename, name, outcome
        )
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=resolved_parent_fd,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(model.model_dump_json(indent=2))
            handle.flush()
            metadata = os.fstat(handle.fileno())
            identity = metadata.st_dev, metadata.st_ino
            os.fsync(handle.fileno())
        assert identity is not None
        _publish_temporary_head_relative(
            resolved_parent_fd,
            basename,
            temporary_name,
            identity,
            snapshot,
            name=name,
        )
        os.fsync(resolved_parent_fd)
        return identity
    except BaseException as primary:
        if (
            outcome is None
            and snapshot is not None
            and snapshot.published_identity is not None
        ):
            try:
                _restore_head_snapshot_relative(
                    resolved_parent_fd, basename, snapshot
                )
            except BaseException as recovery_error:
                raise _rollback_recovery_error(
                    f"governance head rollback recovery is required: {name}",
                    recovery_error,
                ) from primary
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(temporary_name, dir_fd=resolved_parent_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(resolved_parent_fd)

def read_head_snapshot_relative(parent_fd: int, name: str) -> HeadSnapshot:
    """Capture one regular governance head and keep its inode binding."""
    try:
        resolved_parent_fd, basename = descriptor_namespace._open_relative_parent(
            parent_fd, name
        )
    except FileNotFoundError:
        return HeadSnapshot(content=None, original_identity=None)
    except OSError as exc:
        raise FoundryInputError(f"unsafe governance path: {name}") from exc
    descriptor = -1
    try:
        try:
            metadata = os.stat(
                basename, dir_fd=resolved_parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            try:
                os.stat(basename, dir_fd=resolved_parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return HeadSnapshot(content=None, original_identity=None)
            raise FoundryPublicationError(
                f"governance head identity changed during snapshot: {name}"
            ) from None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise FoundryInputError(f"governance head path is unsafe: {name}")
        descriptor = os.open(
            basename,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=resolved_parent_fd,
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(metadata, opened):
            raise FoundryPublicationError(
                f"governance head identity changed during snapshot: {name}"
            )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            content = handle.read()
        try:
            current = os.stat(
                basename, dir_fd=resolved_parent_fd, follow_symlinks=False
            )
        except FileNotFoundError as exc:
            raise FoundryPublicationError(
                f"governance head identity changed during snapshot: {name}"
            ) from exc
        if not stat.S_ISREG(current.st_mode) or not os.path.samestat(metadata, current):
            raise FoundryPublicationError(
                f"governance head identity changed during snapshot: {name}"
            )
        return HeadSnapshot(
            content=content,
            original_identity=(opened.st_dev, opened.st_ino),
        )
    except FoundryPublicationError:
        raise
    except OSError as exc:
        raise FoundryInputError(f"cannot read governance head: {name}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(resolved_parent_fd)


def read_head_relative(parent_fd: int, name: str) -> bytes | None:
    """Capture one regular governance head relative to a pinned directory."""
    return read_head_snapshot_relative(parent_fd, name).content


def read_head_model_snapshot_relative(
    parent_fd: int,
    model: type[_ModelT],
    name: str,
    label: str,
) -> tuple[HeadSnapshot, _ModelT]:
    """Parse one immutable-in-operation model together with its head receipt."""
    snapshot = read_head_snapshot_relative(parent_fd, name)
    if snapshot.content is None:
        raise FoundryInputError(f"required file missing: {label}")
    try:
        return snapshot, model.model_validate_json(snapshot.content)
    except ValidationError as exc:
        raise FoundryInputError(f"{label} is invalid: {str(exc)[:200]}") from exc
    except ValueError as exc:
        raise FoundryInputError(f"{label} is not valid JSON: {str(exc)[:200]}") from exc


def validate_head_snapshot_relative(
    parent_fd: int,
    name: str,
    snapshot: HeadSnapshot,
) -> None:
    """Require a mutable head to still be the exact snapshot the caller read."""
    observed = read_head_snapshot_relative(parent_fd, name)
    if (
        observed.original_identity != snapshot.original_identity
        or observed.content != snapshot.content
    ):
        raise FoundryPublicationError(
            f"governance head identity changed during operation: {name}"
        )

def _rollback_recovery_error(
    message: str,
    cause: BaseException | None = None,
) -> FoundryPublicationError:
    error = FoundryPublicationError(message)
    error.recovery_required = True  # type: ignore[attr-defined]
    if cause is not None:
        return error.with_traceback(cause.__traceback__)
    return error


def _return_quarantined_head(
    parent_fd: int,
    quarantine: str,
    basename: str,
) -> None:
    """Put an untrusted quarantine entry back without replacing a new name."""
    if descriptor_namespace.entry_identity_relative(parent_fd, basename) is not None:
        raise _rollback_recovery_error(
            "governance head identity changed during rollback"
        )
    try:
        descriptor_namespace._rename_noreplace(
            Path(quarantine), Path(basename), parent_fd=parent_fd
        )
    except OSError as exc:
        raise _rollback_recovery_error(
            "governance head rollback recovery is required", exc
        ) from exc
    os.fsync(parent_fd)


def _link_bytes_noreplace_relative(
    parent_fd: int,
    basename: str,
    content: bytes,
    *,
    prefix: str,
    outcome: _RollbackEntryPublication,
) -> tuple[int, int]:
    """Publish raw rollback bytes only into an absent, pinned name."""
    temporary_name = f"{prefix}{uuid.uuid4().hex}.tmp"
    descriptor = -1
    outcome.owned_entry = False
    outcome.identity = None
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            metadata = os.fstat(handle.fileno())
            identity = metadata.st_dev, metadata.st_ino
            os.fsync(handle.fileno())
        try:
            os.link(
                temporary_name,
                basename,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise FoundryPublicationError(
                "governance head identity changed during rollback"
            ) from exc
        outcome.owned_entry = True
        outcome.identity = identity
        if descriptor_namespace.entry_identity_relative(parent_fd, basename) != identity:
            raise FoundryPublicationError(
                "governance head identity changed during rollback"
            )
        os.fsync(parent_fd)
        return identity
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except OSError:
            pass


def _restore_head_snapshot_relative(
    parent_fd: int,
    name: str,
    snapshot: HeadSnapshot,
) -> None:
    """Restore a mutation only when its published inode still owns the name."""
    expected_identity = snapshot.published_identity
    if expected_identity is None:
        return
    try:
        resolved_parent_fd, basename = descriptor_namespace._open_relative_parent(
            parent_fd, name
        )
    except (FoundryInputError, OSError) as exc:
        raise _rollback_recovery_error(
            "governance head rollback path is unsafe", exc
        ) from exc
    quarantine = f".{basename}-rollback-{uuid.uuid4().hex}"
    try:
        if (
            descriptor_namespace.entry_identity_relative(resolved_parent_fd, basename)
            != expected_identity
        ):
            raise _rollback_recovery_error(
                f"governance head identity changed during rollback: {name}"
            )
        try:
            descriptor_namespace._rename_noreplace(
                Path(basename), Path(quarantine), parent_fd=resolved_parent_fd
            )
        except OSError as exc:
            raise _rollback_recovery_error(
                f"governance head rollback move failed: {name}", exc
            ) from exc
        moved_identity = descriptor_namespace.entry_identity_relative(
            resolved_parent_fd, quarantine
        )
        if moved_identity != expected_identity:
            try:
                _return_quarantined_head(
                    resolved_parent_fd, quarantine, basename
                )
            except BaseException as recovery_error:
                raise _rollback_recovery_error(
                    f"governance head identity changed during rollback: {name}",
                    recovery_error,
                ) from recovery_error
            raise _rollback_recovery_error(
                f"governance head identity changed during rollback: {name}"
            )
        if snapshot.content is None:
            try:
                descriptor_namespace.remove_owned_entry_relative(
                    resolved_parent_fd, quarantine, expected_identity
                )
            except BaseException as exc:
                raise _rollback_recovery_error(
                    f"governance head rollback cleanup failed: {name}", exc
                ) from exc
            return

        restored = _RollbackEntryPublication()
        try:
            _link_bytes_noreplace_relative(
                resolved_parent_fd,
                basename,
                snapshot.content,
                prefix=f".{Path(name).stem}-rollback-",
                outcome=restored,
            )
        except BaseException as primary:
            failures: list[BaseException] = []
            if restored.owned_entry and restored.identity is not None:
                try:
                    descriptor_namespace.remove_owned_entry_relative(
                        resolved_parent_fd, basename, restored.identity
                    )
                except BaseException as cleanup_error:
                    failures.append(cleanup_error)
            try:
                _return_quarantined_head(resolved_parent_fd, quarantine, basename)
            except BaseException as recovery_error:
                failures.append(recovery_error)
            if failures:
                raise _rollback_recovery_error(
                    f"governance head rollback recovery is required: {name}",
                    failures[0],
                ) from primary
            raise
        try:
            descriptor_namespace.remove_owned_entry_relative(
                resolved_parent_fd, quarantine, expected_identity
            )
        except BaseException as exc:
            raise _rollback_recovery_error(
                f"governance head rollback cleanup failed: {name}", exc
            ) from exc
    finally:
        os.close(resolved_parent_fd)

def restore_head_relative(
    parent_fd: int,
    name: str,
    snapshot: HeadSnapshot,
) -> None:
    """Restore only the inode a transaction recorded as its replacement."""
    if not isinstance(snapshot, HeadSnapshot):
        raise FoundryInputError("governance head rollback requires a head snapshot")
    _restore_head_snapshot_relative(parent_fd, name, snapshot)
