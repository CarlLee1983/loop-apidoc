"""Descriptor-pinned filesystem primitives for Foundry persistence.

This module is the only low-level Foundry boundary that creates, replaces,
moves, or removes entries below a held directory descriptor.  Higher-level
model persistence and transaction policy stay in :mod:`foundry.store`.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import shutil
import stat
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from loop_apidoc.atomic_publish import rename_directory_noreplace
from loop_apidoc.foundry.models import FoundryInputError, FoundryPublicationError

_ModelT = TypeVar("_ModelT", bound=BaseModel)


@dataclass
class ImmutableEntryPublication:
    """Ownership token for a newly linked immutable governed entry."""

    owned_entry: bool = False
    identity: tuple[int, int] | None = None


@dataclass(slots=True)
class HeadSnapshot:
    """One head's original bytes and any transaction-owned replacement inode."""

    content: bytes | None
    original_identity: tuple[int, int] | None
    published_identity: tuple[int, int] | None = None


def _directory_open_flags() -> int:
    """Return the mandatory no-follow flags for every governed directory open."""
    directory = getattr(os, "O_DIRECTORY", None)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if directory is None or no_follow is None:
        raise FoundryInputError(
            "secure descriptor-relative directory operations are unavailable"
        )
    return os.O_RDONLY | directory | no_follow


def _open_directory(path: Path | str, *, parent_fd: int | None = None) -> int:
    flags = _directory_open_flags() | getattr(os, "O_CLOEXEC", 0)
    return os.open(path, flags, dir_fd=parent_fd)


def validate_pinned_directory_chain(
    root_path: Path,
    *,
    expected_root_fd: int | None,
    components: tuple[tuple[str, int | None], ...],
    message: str,
) -> None:
    """Reopen a canonical directory chain without following a substituted link.

    The held descriptors remain authoritative for all I/O.  This check proves
    that the canonical namespace still names those descriptors at the commit
    boundary.  Each pass walks with ``openat``/``O_NOFOLLOW`` and compares the
    opened descriptors directly; it never performs a separate pathname
    ``is_symlink``/``stat`` check that an attacker could interleave.
    """
    if any(
        not component
        or component in {".", ".."}
        or "/" in component
        or "\\" in component
        for component, _ in components
    ):
        raise FoundryInputError("unsafe governed directory component")

    def open_once() -> None:
        descriptors: list[int] = []
        try:
            root_fd = _open_directory(root_path)
            descriptors.append(root_fd)
            if expected_root_fd is not None and not os.path.samestat(
                os.fstat(root_fd), os.fstat(expected_root_fd)
            ):
                raise FoundryPublicationError(message)
            parent_fd = root_fd
            for component, expected_fd in components:
                child_fd = _open_directory(component, parent_fd=parent_fd)
                descriptors.append(child_fd)
                if expected_fd is not None and not os.path.samestat(
                    os.fstat(child_fd), os.fstat(expected_fd)
                ):
                    raise FoundryPublicationError(message)
                parent_fd = child_fd
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    try:
        # A second fresh walk catches a replacement that happened after the
        # first root open but before its descendants were checked.  POSIX does
        # not provide a way to close the final instant of namespace mutation;
        # writes themselves always remain descriptor-relative.
        open_once()
        open_once()
    except FoundryPublicationError:
        raise
    except (OSError, FoundryInputError) as exc:
        raise FoundryPublicationError(message) from exc


def _rename_noreplace(
    staged_root: Path,
    asset_root: Path,
    *,
    parent_fd: int | None = None,
) -> None:
    """Rename sibling directories without replacing an existing destination."""
    if parent_fd is None and staged_root.parent != asset_root.parent:
        raise OSError(errno.EXDEV, "asset publication requires one parent directory")
    close_parent = parent_fd is None
    if parent_fd is None:
        parent_fd = os.open(asset_root.parent, _directory_open_flags())
    source_name = os.fsencode(staged_root.name)
    destination_name = os.fsencode(asset_root.name)
    try:
        rename_directory_noreplace(parent_fd, source_name, destination_name)
    finally:
        if close_parent:
            os.close(parent_fd)


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
        if entry_identity_relative(parent_fd, basename) != identity:
            raise _rollback_recovery_error(
                f"governance head identity changed during publication: {name}"
            )
        snapshot.published_identity = identity
        return

    if entry_identity_relative(parent_fd, basename) != expected:
        raise FoundryPublicationError(
            f"governance head identity changed before publication: {name}"
        )
    quarantine = f".{basename}-replace-{uuid.uuid4().hex}"
    try:
        _rename_noreplace(
            Path(basename), Path(quarantine), parent_fd=parent_fd
        )
    except OSError as exc:
        raise FoundryPublicationError(
            f"governance head move failed during publication: {name}"
        ) from exc

    moved = entry_identity_relative(parent_fd, quarantine)
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

    if entry_identity_relative(parent_fd, basename) != identity:
        raise _rollback_recovery_error(
            f"governance head identity changed during publication: {name}"
        )
    snapshot.published_identity = identity
    try:
        remove_owned_entry_relative(parent_fd, quarantine, expected)
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
    resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
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


def _atomic_write_bytes_relative(
    parent_fd: int,
    name: str,
    content: bytes,
    *,
    prefix: str,
) -> tuple[int, int]:
    resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    temporary_name = f"{prefix}{uuid.uuid4().hex}.tmp"
    descriptor = -1
    identity: tuple[int, int] | None = None
    snapshot: HeadSnapshot | None = None
    try:
        snapshot = _capture_mutable_head_snapshot(
            resolved_parent_fd, basename, name, None
        )
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=resolved_parent_fd,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
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
        if snapshot is not None and snapshot.published_identity is not None:
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


def _open_relative_parent(parent_fd: int, name: str) -> tuple[int, str]:
    relative = PurePath(name)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in name
    ):
        raise FoundryInputError(f"unsafe governance relative path: {name}")
    descriptor = os.dup(parent_fd)
    try:
        for part in relative.parts[:-1]:
            child = _open_directory(part, parent_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, relative.parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def read_bytes_relative(
    parent_fd: int,
    name: str,
    label: str,
    *,
    optional: bool = False,
    max_bytes: int | None = None,
) -> bytes | None:
    """Read one regular file below a pinned descriptor without following links."""
    try:
        resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    except FileNotFoundError:
        if optional:
            return None
        raise FoundryInputError(f"required file missing: {label}") from None
    except OSError as exc:
        raise FoundryInputError(f"{label} path is unsafe") from exc
    descriptor = -1
    try:
        try:
            metadata = os.stat(
                basename, dir_fd=resolved_parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            if optional:
                return None
            raise FoundryInputError(f"required file missing: {label}") from None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise FoundryInputError(f"{label} path is unsafe")
        if max_bytes is not None and metadata.st_size > max_bytes:
            raise FoundryInputError(f"{label} exceeds size limit")
        descriptor = os.open(
            basename,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=resolved_parent_fd,
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(metadata, opened):
            raise FoundryInputError(f"{label} path is unsafe")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            content = handle.read() if max_bytes is None else handle.read(max_bytes + 1)
        if max_bytes is not None and len(content) > max_bytes:
            raise FoundryInputError(f"{label} exceeds size limit")
        return content
    except FoundryInputError:
        raise
    except OSError as exc:
        raise FoundryInputError(f"cannot read {label}: {str(exc)[:200]}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(resolved_parent_fd)


def read_model_relative(
    parent_fd: int,
    model: type[_ModelT],
    name: str,
    label: str,
    *,
    optional: bool = False,
    max_bytes: int | None = None,
) -> _ModelT | None:
    """Load one strict JSON model through the pinned read seam."""
    content = read_bytes_relative(
        parent_fd,
        name,
        label,
        optional=optional,
        max_bytes=max_bytes,
    )
    if content is None:
        return None
    try:
        return model.model_validate_json(content)
    except ValidationError as exc:
        raise FoundryInputError(f"{label} is invalid: {str(exc)[:200]}") from exc
    except ValueError as exc:
        raise FoundryInputError(f"{label} is not valid JSON: {str(exc)[:200]}") from exc


def digest_artifact_relative(
    parent_fd: int,
    name: str,
    kind: str,
    label: str = "artifact",
) -> str:
    """Digest one regular file or tree below a held directory descriptor.

    This mirrors :func:`foundry.integrity.digest_artifact` without reopening an
    untrusted pathname.  A tree is traversed through held descriptors and its
    root is revalidated before returning the digest.
    """
    if kind == "file":
        content = read_bytes_relative(parent_fd, name, label)
        assert content is not None
        return hashlib.sha256(content).hexdigest()
    if kind != "tree":
        raise FoundryInputError(f"unknown artifact kind: {label}")
    try:
        descriptor = open_directory_relative(parent_fd, name)
    except FoundryInputError:
        raise
    except OSError as exc:
        raise FoundryInputError(f"artifact is missing or unsafe: {label}") from exc
    try:
        entries: list[tuple[str, str]] = []
        _digest_tree_entries(descriptor, entries, label=label)
        validate_directory_relative(parent_fd, name, descriptor)
    finally:
        os.close(descriptor)
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _digest_tree_entries(
    directory_fd: int,
    entries: list[tuple[str, str]],
    *,
    label: str,
    relative: PurePath = PurePath(),
) -> None:
    """Collect the deterministic digest entries for one pinned artifact tree."""
    try:
        names = sorted(os.listdir(directory_fd))
    except OSError as exc:
        raise FoundryInputError(f"cannot read artifact: {label}") from exc
    for name in names:
        child_relative = relative / name
        try:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise FoundryInputError(f"cannot read artifact: {label}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise FoundryInputError(f"unsafe artifact path: {label}")
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = -1
            try:
                child_fd = _open_directory(name, parent_fd=directory_fd)
                opened = os.fstat(child_fd)
                if not stat.S_ISDIR(opened.st_mode) or not os.path.samestat(
                    metadata, opened
                ):
                    raise FoundryInputError(f"unsafe artifact path: {label}")
                _digest_tree_entries(
                    child_fd,
                    entries,
                    label=label,
                    relative=child_relative,
                )
                validate_directory_relative(directory_fd, name, child_fd)
            except FoundryInputError:
                raise
            except OSError as exc:
                raise FoundryInputError(f"cannot read artifact: {label}") from exc
            finally:
                if child_fd >= 0:
                    os.close(child_fd)
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise FoundryInputError(f"artifact contains a non-file: {label}")
        content = read_bytes_relative(directory_fd, name, label)
        assert content is not None
        entries.append((child_relative.as_posix(), hashlib.sha256(content).hexdigest()))


def open_directory_relative(parent_fd: int, name: str) -> int:
    """Open one existing directory beneath a pinned root without following links."""
    resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    try:
        return _open_directory(basename, parent_fd=resolved_parent_fd)
    finally:
        os.close(resolved_parent_fd)


def validate_directory_relative(
    parent_fd: int, name: str, expected_fd: int
) -> None:
    """Reject replacement of a nested directory pinned by a transaction."""
    try:
        current_fd = open_directory_relative(parent_fd, name)
    except OSError as exc:
        raise FoundryPublicationError(
            f"governance namespace changed during publication: {name}"
        ) from exc
    try:
        if not os.path.samestat(os.fstat(current_fd), os.fstat(expected_fd)):
            raise FoundryPublicationError(
                f"governance namespace changed during publication: {name}"
            )
    finally:
        os.close(current_fd)


def ensure_directory_relative(parent_fd: int, name: str) -> int:
    """Create/open a directory chain beneath a pinned root and return its fd."""
    relative = PurePath(name)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in name
    ):
        raise FoundryInputError(f"unsafe governance relative path: {name}")
    descriptor = os.dup(parent_fd)
    try:
        for part in relative.parts:
            try:
                child = _open_directory(part, parent_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, dir_fd=descriptor)
                os.fsync(descriptor)
                child = _open_directory(part, parent_fd=descriptor)
            except OSError as exc:
                raise FoundryInputError(f"unsafe governance path: {name}") from exc
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def create_owned_directory_relative(
    parent_fd: int, *, prefix: str
) -> tuple[str, int, tuple[int, int]]:
    """Create an unguessable transaction-owned directory under a pinned parent."""
    for _ in range(100):
        name = f"{prefix}{uuid.uuid4().hex}"
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        descriptor = -1
        identity: tuple[int, int] | None = None
        try:
            metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode):
                raise FoundryPublicationError(
                    "new governed staging entry is not a directory"
                )
            identity = metadata.st_dev, metadata.st_ino
            descriptor = _open_directory(name, parent_fd=parent_fd)
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != identity:
                raise FoundryPublicationError(
                    "new governed staging directory identity changed"
                )
            os.fsync(parent_fd)
            return name, descriptor, identity
        except BaseException as primary:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                if identity is None:
                    raise FoundryPublicationError(
                        "new governed staging directory ownership is unknown"
                    )
                remove_owned_entry_relative(parent_fd, name, identity)
            except BaseException as cleanup_error:
                failure = FoundryPublicationError(
                    "governed staging directory creation failed and recovery "
                    f"is required: {cleanup_error}"
                )
                failure.recovery_required = True  # type: ignore[attr-defined]
                raise failure from primary
            raise
    raise FoundryPublicationError("cannot allocate governed staging directory")


def write_model_relative(parent_fd: int, name: str, model: BaseModel) -> None:
    """Write a new/replaceable model beneath a pinned directory tree."""
    resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    try:
        _atomic_write_model_relative(
            resolved_parent_fd, basename, model, prefix=f".{Path(name).stem}-"
        )
    finally:
        os.close(resolved_parent_fd)


def write_once_model_relative(
    parent_fd: int,
    name: str,
    model: BaseModel,
    *,
    outcome: ImmutableEntryPublication | None = None,
) -> tuple[bool, tuple[int, int]]:
    """Publish one immutable model without replacing an existing leaf."""
    publication = outcome or ImmutableEntryPublication()
    publication.owned_entry = False
    publication.identity = None
    relative = PurePath(name)
    parent_name = str(relative.parent)
    if parent_name != ".":
        directory_fd = ensure_directory_relative(parent_fd, parent_name)
        os.close(directory_fd)
    resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    temporary_name = f".{basename}-{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=resolved_parent_fd,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(model.model_dump_json(indent=2).encode("utf-8"))
            handle.flush()
            identity_metadata = os.fstat(handle.fileno())
            identity = (identity_metadata.st_dev, identity_metadata.st_ino)
            os.fsync(handle.fileno())
        try:
            os.link(
                temporary_name,
                basename,
                src_dir_fd=resolved_parent_fd,
                dst_dir_fd=resolved_parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            snapshot = read_head_snapshot_relative(resolved_parent_fd, basename)
            if snapshot.content is None or snapshot.original_identity is None:
                raise FoundryPublicationError(
                    f"governed immutable output disappeared: {name}"
                )
            if (
                entry_identity_relative(resolved_parent_fd, basename)
                != snapshot.original_identity
            ):
                raise FoundryPublicationError(
                    f"governed immutable output identity changed: {name}"
                )
            raise FoundryInputError(
                f"governed immutable output already exists: {name}"
            )
        # The temporary inode becomes the immutable output atomically at the
        # link.  Record the identity before any post-mutation verification or
        # parent fsync so a caller can roll it back if either step fails.
        publication.owned_entry = True
        publication.identity = identity
        if entry_identity_relative(resolved_parent_fd, basename) != identity:
            raise FoundryPublicationError(
                f"governed immutable output identity changed: {name}"
            )
        os.fsync(resolved_parent_fd)
        return False, identity
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=resolved_parent_fd)
        except OSError:
            pass
        os.close(resolved_parent_fd)


def copy_tree_to_directory(source: Path, destination_fd: int, name: str) -> None:
    """Copy a regular-file tree into a new pinned destination directory."""
    source_fd = _open_source_directory(source)
    target_fd = -1
    target_identity: tuple[int, int] | None = None
    try:
        os.mkdir(name, 0o700, dir_fd=destination_fd)
        target_fd = _open_directory(name, parent_fd=destination_fd)
        opened = os.fstat(target_fd)
        target_identity = opened.st_dev, opened.st_ino
        _copy_tree_contents(source_fd, target_fd)
        os.fsync(target_fd)
    except BaseException as primary:
        if target_identity is None:
            raise
        try:
            remove_owned_entry_relative(destination_fd, name, target_identity)
        except BaseException as cleanup_error:
            failure = FoundryPublicationError(
                "candidate copy failed and recovery is required: "
                f"{cleanup_error}"
            )
            failure.recovery_required = True  # type: ignore[attr-defined]
            raise failure from primary
        raise
    finally:
        if target_fd >= 0:
            os.close(target_fd)
        os.close(source_fd)


def copy_tree_to_owned_directory(
    source: Path, destination_fd: int, *, prefix: str
) -> tuple[str, int, tuple[int, int]]:
    """Copy a complete regular-file tree into a transaction-owned directory."""
    source_fd = _open_source_directory(source)
    try:
        name, target_fd, identity = create_owned_directory_relative(
            destination_fd, prefix=prefix
        )
        try:
            _copy_tree_contents(source_fd, target_fd)
            os.fsync(target_fd)
            return name, target_fd, identity
        except BaseException as primary:
            try:
                os.close(target_fd)
            except OSError:
                pass
            try:
                remove_owned_entry_relative(destination_fd, name, identity)
            except BaseException as cleanup_error:
                failure = FoundryPublicationError(
                    "candidate staging copy failed and recovery is required: "
                    f"{cleanup_error}"
                )
                failure.recovery_required = True  # type: ignore[attr-defined]
                raise failure from primary
            raise
    finally:
        os.close(source_fd)


def _open_source_directory(source: Path) -> int:
    try:
        descriptor = _open_directory(source)
    except OSError as exc:
        raise FoundryInputError("candidate artifact tree is unsafe") from exc
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise FoundryInputError("candidate artifact tree is unsafe")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _copy_tree_contents(
    source_fd: int,
    destination_fd: int,
    *,
    relative: PurePath = PurePath(),
) -> None:
    try:
        names = sorted(os.listdir(source_fd))
    except OSError as exc:
        raise FoundryInputError("candidate artifact tree is unsafe") from exc
    for name in names:
        child_relative = relative / name
        label = str(child_relative)
        try:
            metadata = os.stat(
                name, dir_fd=source_fd, follow_symlinks=False
            )
        except OSError as exc:
            raise FoundryInputError(f"candidate artifact is unsafe: {label}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise FoundryInputError(f"candidate artifact is unsafe: {label}")
        if stat.S_ISDIR(metadata.st_mode):
            source_child_fd = target_child_fd = -1
            try:
                source_child_fd = _open_directory(name, parent_fd=source_fd)
                opened = os.fstat(source_child_fd)
                if not stat.S_ISDIR(opened.st_mode) or not os.path.samestat(
                    metadata, opened
                ):
                    raise FoundryInputError(
                        f"candidate artifact is unsafe: {label}"
                    )
                os.mkdir(name, 0o700, dir_fd=destination_fd)
                target_child_fd = _open_directory(name, parent_fd=destination_fd)
                _copy_tree_contents(
                    source_child_fd,
                    target_child_fd,
                    relative=child_relative,
                )
                os.fsync(target_child_fd)
            except FoundryInputError:
                raise
            except OSError as exc:
                raise FoundryInputError(
                    f"candidate artifact is unsafe: {label}"
                ) from exc
            finally:
                if target_child_fd >= 0:
                    os.close(target_child_fd)
                if source_child_fd >= 0:
                    os.close(source_child_fd)
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise FoundryInputError("candidate artifact contains a non-file")
        source_file_fd = target_file_fd = -1
        try:
            source_file_fd = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=source_fd,
            )
            opened = os.fstat(source_file_fd)
            if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(
                metadata, opened
            ):
                raise FoundryInputError(f"candidate artifact is unsafe: {label}")
            target_file_fd = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=destination_fd,
            )
            with os.fdopen(source_file_fd, "rb") as source_stream, os.fdopen(
                target_file_fd, "wb"
            ) as target_stream:
                source_file_fd = target_file_fd = -1
                shutil.copyfileobj(source_stream, target_stream)
                target_stream.flush()
                os.fsync(target_stream.fileno())
        except FoundryInputError:
            raise
        except OSError as exc:
            raise FoundryInputError(f"candidate artifact is unsafe: {label}") from exc
        finally:
            if target_file_fd >= 0:
                os.close(target_file_fd)
            if source_file_fd >= 0:
                os.close(source_file_fd)


def read_head_snapshot_relative(parent_fd: int, name: str) -> HeadSnapshot:
    """Capture one regular governance head and keep its inode binding."""
    try:
        resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
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
    if entry_identity_relative(parent_fd, basename) is not None:
        raise _rollback_recovery_error(
            "governance head identity changed during rollback"
        )
    try:
        _rename_noreplace(Path(quarantine), Path(basename), parent_fd=parent_fd)
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
    outcome: ImmutableEntryPublication,
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
        if entry_identity_relative(parent_fd, basename) != identity:
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
        resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    except (FoundryInputError, OSError) as exc:
        raise _rollback_recovery_error(
            "governance head rollback path is unsafe", exc
        ) from exc
    quarantine = f".{basename}-rollback-{uuid.uuid4().hex}"
    try:
        if entry_identity_relative(resolved_parent_fd, basename) != expected_identity:
            raise _rollback_recovery_error(
                f"governance head identity changed during rollback: {name}"
            )
        try:
            _rename_noreplace(
                Path(basename), Path(quarantine), parent_fd=resolved_parent_fd
            )
        except OSError as exc:
            raise _rollback_recovery_error(
                f"governance head rollback move failed: {name}", exc
            ) from exc
        moved_identity = entry_identity_relative(resolved_parent_fd, quarantine)
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
                remove_owned_entry_relative(
                    resolved_parent_fd, quarantine, expected_identity
                )
            except BaseException as exc:
                raise _rollback_recovery_error(
                    f"governance head rollback cleanup failed: {name}", exc
                ) from exc
            return

        restored = ImmutableEntryPublication()
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
                    remove_owned_entry_relative(
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
            remove_owned_entry_relative(
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
    content: bytes | None | HeadSnapshot,
) -> None:
    """Restore a captured governance head without retargeting pinned state.

    ``bytes`` remains a compatibility input for legacy callers.  Transaction
    code passes :class:`HeadSnapshot`, which permits rollback only when the
    replacement inode is still the one this transaction published.
    """
    if isinstance(content, HeadSnapshot):
        _restore_head_snapshot_relative(parent_fd, name, content)
        return
    if content is None:
        try:
            resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
        except FileNotFoundError:
            return
        try:
            try:
                os.unlink(basename, dir_fd=resolved_parent_fd)
            except FileNotFoundError:
                return
            os.fsync(resolved_parent_fd)
        finally:
            os.close(resolved_parent_fd)
        return
    _atomic_write_bytes_relative(
        parent_fd, name, content, prefix=f".{Path(name).stem}-rollback-"
    )


def _cleanup_recovery_error(name: str) -> FoundryPublicationError:
    error = FoundryPublicationError(
        f"transaction-owned entry identity changed during cleanup: {name}"
    )
    error.recovery_required = True  # type: ignore[attr-defined]
    return error


def _validate_directory_name_matches_descriptor(
    parent_fd: int,
    name: str,
    descriptor: int,
) -> None:
    try:
        current_fd = _open_directory(name, parent_fd=parent_fd)
    except OSError as exc:
        raise _cleanup_recovery_error(name) from exc
    try:
        if not os.path.samestat(os.fstat(current_fd), os.fstat(descriptor)):
            raise _cleanup_recovery_error(name)
    finally:
        os.close(current_fd)


def remove_entry_relative(
    parent_fd: int,
    name: str,
    *,
    expected_identity: tuple[int, int],
) -> None:
    """Verify a retained owned quarantine without unlinking its pathname."""
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise _cleanup_recovery_error(name) from exc
    if (metadata.st_dev, metadata.st_ino) != expected_identity:
        raise _cleanup_recovery_error(name)
    if stat.S_ISDIR(metadata.st_mode):
        try:
            descriptor = _open_directory(name, parent_fd=parent_fd)
        except OSError as exc:
            raise _cleanup_recovery_error(name) from exc
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != expected_identity:
                raise _cleanup_recovery_error(name)
            _validate_directory_name_matches_descriptor(parent_fd, name, descriptor)
        finally:
            os.close(descriptor)
        return
    if not stat.S_ISREG(metadata.st_mode):
        raise _cleanup_recovery_error(name)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise FoundryInputError(
            "secure descriptor-relative file operations are unavailable"
        )
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | os.O_NONBLOCK
            | no_follow
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise _cleanup_recovery_error(name) from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (
            opened.st_dev,
            opened.st_ino,
        ) != expected_identity:
            raise _cleanup_recovery_error(name)
    finally:
        os.close(descriptor)


def entry_identity_relative(parent_fd: int, name: str) -> tuple[int, int] | None:
    try:
        resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    except FileNotFoundError:
        return None
    try:
        try:
            metadata = os.stat(
                basename, dir_fd=resolved_parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            return None
        return metadata.st_dev, metadata.st_ino
    finally:
        os.close(resolved_parent_fd)


def remove_owned_entry_relative(
    parent_fd: int, name: str, identity: tuple[int, int]
) -> None:
    """Retire an identity-pinned entry into a hidden, durable quarantine.

    Portable POSIX has no ``unlink``/``rmdir`` operation constrained by an
    expected inode. A final namespace swap could otherwise make automatic
    cleanup delete a foreign entry. This primitive therefore only removes the
    canonical name: it moves the exact owned entry to an unguessable sibling
    and retains that tombstone for trusted maintenance.
    """
    try:
        resolved_parent_fd, basename = _open_relative_parent(parent_fd, name)
    except FileNotFoundError:
        return
    try:
        current_identity = entry_identity_relative(resolved_parent_fd, basename)
        if current_identity is None:
            return
        if current_identity != identity:
            raise _cleanup_recovery_error(name)
        quarantine = f".{basename}-cleanup-{uuid.uuid4().hex}"
        try:
            _rename_noreplace(
                Path(basename), Path(quarantine), parent_fd=resolved_parent_fd
            )
        except FileNotFoundError:
            return
        except OSError as exc:
            raise FoundryPublicationError(
                f"transaction-owned entry cleanup move failed: {name}"
            ) from exc

        moved_identity = entry_identity_relative(resolved_parent_fd, quarantine)
        if moved_identity != identity:
            try:
                if entry_identity_relative(resolved_parent_fd, basename) is not None:
                    raise _cleanup_recovery_error(name)
                _rename_noreplace(
                    Path(quarantine),
                    Path(basename),
                    parent_fd=resolved_parent_fd,
                )
                os.fsync(resolved_parent_fd)
            except BaseException as recovery_error:
                raise _cleanup_recovery_error(name) from recovery_error
            raise _cleanup_recovery_error(name)
        remove_entry_relative(
            resolved_parent_fd,
            quarantine,
            expected_identity=identity,
        )
        os.fsync(resolved_parent_fd)
    finally:
        os.close(resolved_parent_fd)


def move_owned_directory_relative(
    parent_fd: int,
    source: str,
    destination: str,
    identity: tuple[int, int],
) -> tuple[int, int]:
    """Atomically move one identity-pinned directory only into an absent name."""
    for value in (source, destination):
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            raise FoundryInputError("unsafe governed directory name")
    if source == destination:
        raise FoundryInputError("governed directory move requires distinct names")
    if entry_identity_relative(parent_fd, source) != identity:
        raise FoundryPublicationError("governed directory identity changed")
    if entry_identity_relative(parent_fd, destination) is not None:
        raise FoundryInputError("governed directory destination already exists")
    try:
        _rename_noreplace(Path(source), Path(destination), parent_fd=parent_fd)
    except OSError as exc:
        raise FoundryPublicationError("governed directory move failed") from exc
    moved_identity = entry_identity_relative(parent_fd, destination)
    if moved_identity != identity:
        raise FoundryPublicationError("governed directory identity changed")
    os.fsync(parent_fd)
    return moved_identity


def directory_fd_path(descriptor: int) -> Path:
    """Resolve a pinned directory descriptor for libraries requiring a pathname."""
    if sys.platform == "darwin":
        # Python's fcntl wrapper caps mutable buffers at 1 KiB, which is also
        # Darwin's path buffer size for F_GETPATH.
        buffer = fcntl.fcntl(descriptor, 50, b"\0" * 1024)  # F_GETPATH
        raw = buffer.split(b"\0", 1)[0]
        if not raw:
            raise FoundryPublicationError("cannot resolve pinned directory")
        return Path(os.fsdecode(raw))
    path = Path("/proc/self/fd") / str(descriptor)
    if path.exists():
        return path
    raise FoundryPublicationError("cannot resolve pinned directory")
