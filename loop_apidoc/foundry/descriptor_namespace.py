"""Descriptor-pinned namespace operations for Foundry persistence."""

from __future__ import annotations

import errno
import fcntl
import os
import stat
import sys
import uuid
from pathlib import Path, PurePath

from loop_apidoc.atomic_publish import rename_directory_noreplace
from loop_apidoc.foundry.models import FoundryInputError, FoundryPublicationError


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
