"""Small, dependency-neutral primitives for immutable directory publication."""

from __future__ import annotations

import ctypes
import errno
import os
import platform
import stat
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

DirectoryIdentity = tuple[int, int]
EntryIdentity = tuple[int, int, int]


class DirectoryPublicationCollisionError(RuntimeError):
    """The immutable publication destination already exists."""


class DirectoryPublicationError(RuntimeError):
    """The platform cannot atomically publish a directory without replacement."""


def publish_directory_noreplace(
    staged_directory: Path,
    destination: Path,
    *,
    parent_fd: int | None = None,
    expected_source_identity: DirectoryIdentity | None = None,
    post_publish_verify: Callable[[], None] | None = None,
) -> None:
    """Atomically publish ``staged_directory`` only when ``destination`` is absent.

    POSIX ``rename`` would replace an empty destination directory, so it is not a
    valid fallback for immutable runs. macOS and Linux expose explicit no-replace
    variants; every other platform fails closed.  A caller that has already
    pinned the containing directory may pass its descriptor so publication never
    reopens a replaceable pathname.  ``expected_source_identity`` binds the
    source name to a directory descriptor captured by the caller; the source
    is checked immediately before rename and the destination immediately after
    it, so a directory-name replacement cannot be reported as a success.
    ``post_publish_verify`` runs through any still-held source capability after
    the move; callers use it to revalidate stage contents in the narrow window
    between their preflight and publication.
    """
    close_parent = parent_fd is None
    if parent_fd is None:
        if staged_directory.parent != destination.parent:
            raise DirectoryPublicationError(
                "directory publication requires one parent directory"
            )
        parent_fd = open_directory(destination.parent, "directory publication parent")
    try:
        if expected_source_identity is not None:
            verify_directory_entry_identity(
                parent_fd,
                staged_directory.name,
                expected_source_identity,
                "directory publication source",
            )
        rename_directory_noreplace(
            parent_fd,
            os.fsencode(staged_directory.name),
            os.fsencode(destination.name),
        )
        try:
            if expected_source_identity is not None:
                verify_directory_entry_identity(
                    parent_fd,
                    destination.name,
                    expected_source_identity,
                    "published directory",
                )
            if post_publish_verify is not None:
                post_publish_verify()
            os.fsync(parent_fd)
        except Exception as primary:
            try:
                quarantine = _quarantine_untrusted_entry(parent_fd, destination.name)
            except Exception as quarantine_error:
                raise DirectoryPublicationError(
                    "published directory failed verification and could not be quarantined"
                ) from quarantine_error
            raise DirectoryPublicationError(
                "published directory failed verification; retained outside "
                f"the canonical run name as {quarantine}"
            ) from primary
    except FileExistsError as exc:
        raise DirectoryPublicationCollisionError(
            f"directory already exists: {destination}"
        ) from exc
    except OSError as exc:
        raise DirectoryPublicationError(
            f"directory publication failed: {destination}"
        ) from exc
    finally:
        if close_parent:
            os.close(parent_fd)


def _directory_open_flags() -> int:
    directory = getattr(os, "O_DIRECTORY", None)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if directory is None or no_follow is None:
        raise DirectoryPublicationError(
            "secure directory publication is unavailable on this platform"
        )
    return os.O_RDONLY | directory | no_follow | getattr(os, "O_CLOEXEC", 0)


def open_directory(path: Path, label: str) -> int:
    """Open one concrete non-symlink directory for an identity-bound operation."""
    try:
        return os.open(path, _directory_open_flags())
    except OSError as exc:
        raise DirectoryPublicationError(
            f"{label} is not a real non-symlink directory: {path}"
        ) from exc


def open_directory_relative(parent_fd: int, name: str, label: str) -> int:
    """Open a concrete direct child beneath a pinned parent descriptor."""
    try:
        return os.open(name, _directory_open_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise DirectoryPublicationError(
            f"{label} is not a real non-symlink directory: {name}"
        ) from exc


def directory_identity(directory_fd: int) -> DirectoryIdentity:
    """Return the stable device/inode identity held by a directory descriptor."""
    metadata = os.fstat(directory_fd)
    return metadata.st_dev, metadata.st_ino


def create_owned_directory_relative(
    parent_fd: int,
    *,
    prefix: str,
    label: str,
) -> tuple[str, int, DirectoryIdentity]:
    """Create and open a private child directly beneath ``parent_fd``.

    ``mkdir`` has no descriptor-returning variant.  Record the no-follow inode
    immediately after creation and require the subsequently opened descriptor
    to match it, so a name replaced in that interval cannot become the stage
    we write into.  A failed creation is deliberately retained: pathname-based
    cleanup could remove a replacement owned by someone else.
    """
    if not prefix or "/" in prefix or "\\" in prefix:
        raise DirectoryPublicationError("unsafe private directory prefix")
    for _ in range(100):
        name = f"{prefix}{uuid.uuid4().hex}"
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        descriptor = -1
        try:
            created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(created.st_mode):
                raise DirectoryPublicationError(
                    f"new {label} is not a real directory"
                )
            expected = created.st_dev, created.st_ino
            descriptor = open_directory_relative(parent_fd, name, label)
            if directory_identity(descriptor) != expected:
                raise DirectoryPublicationError(f"new {label} identity changed")
            os.fsync(parent_fd)
            return name, descriptor, expected
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            raise
    raise DirectoryPublicationError(f"cannot allocate private {label}")


def verify_directory_entry_identity(
    parent_fd: int,
    name: str,
    expected: DirectoryIdentity,
    label: str,
) -> None:
    """Require a named child of ``parent_fd`` to retain ``expected`` identity."""
    descriptor = open_directory_relative(parent_fd, name, label)
    try:
        if directory_identity(descriptor) != expected:
            raise DirectoryPublicationError(f"{label} identity changed")
    finally:
        os.close(descriptor)


def verify_directory_path_identity(
    path: Path,
    expected: DirectoryIdentity,
    label: str,
) -> None:
    """Require a returned directory pathname to still bind its pinned directory."""
    descriptor = open_directory(path, label)
    try:
        if directory_identity(descriptor) != expected:
            raise DirectoryPublicationError(f"{label} identity changed")
    finally:
        os.close(descriptor)


def _quarantine_untrusted_entry(parent_fd: int, name: str) -> str:
    """Move an identity-mismatched final entry out of its public name.

    We never recursively delete an entry after an identity failure: a final
    name can already have been swapped to a foreign directory.  Moving it to
    a random sibling through the held parent descriptor preserves evidence for
    controlled inspection while ensuring a failed run cannot occupy ``name``.
    """
    for _ in range(100):
        quarantine = f".{name}-rejected-{uuid.uuid4().hex}"
        expected = _entry_identity_nofollow(
            parent_fd, name, "identity-mismatched published entry"
        )
        try:
            _rename_entry_noreplace(
                parent_fd, os.fsencode(name), os.fsencode(quarantine)
            )
        except FileExistsError:
            continue
        except OSError as exc:
            raise DirectoryPublicationError(
                "identity-mismatched published entry could not be quarantined"
            ) from exc
        if _entry_identity_nofollow(
            parent_fd,
            quarantine,
            "quarantined published entry",
        ) != expected:
            raise DirectoryPublicationError("quarantined published entry identity changed")
        os.fsync(parent_fd)
        return quarantine
    raise DirectoryPublicationError(
        "identity-mismatched published entry cannot be assigned a quarantine"
    )


def _entry_identity_nofollow(
    parent_fd: int, name: str, label: str
) -> EntryIdentity:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise DirectoryPublicationError(f"{label} is unavailable: {name}") from exc
    return metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode)


def rename_directory_noreplace(
    parent_fd: int, source: bytes, destination: bytes
) -> None:
    """Perform the platform no-replace rename relative to one open parent."""
    _rename_noreplace(parent_fd, source, destination, nofollow_any=True)


def _rename_entry_noreplace(parent_fd: int, source: bytes, destination: bytes) -> None:
    """Move one direct entry without following its leaf symlink on Darwin."""
    _rename_noreplace(parent_fd, source, destination, nofollow_any=False)


def _rename_noreplace(
    parent_fd: int,
    source: bytes,
    destination: bytes,
    *,
    nofollow_any: bool,
) -> None:
    """Perform a no-replace rename with the caller's direct-entry policy."""
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renameatx_np = libc.renameatx_np
        renameatx_np.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameatx_np.restype = ctypes.c_int
        flags = 0x00000004 | 0x00000020  # EXCL | BENEATH
        if nofollow_any:
            flags |= 0x00000010  # NOFOLLOW_ANY
        result = renameatx_np(
            parent_fd,
            source,
            parent_fd,
            destination,
            flags,
        )
    elif sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is not None:
            renameat2.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            renameat2.restype = ctypes.c_int
            result = renameat2(
                parent_fd, source, parent_fd, destination, 0x00000001
            )  # RENAME_NOREPLACE
        else:
            syscall_numbers = {
                "x86_64": 316,
                "aarch64": 276,
                "armv7l": 382,
                "ppc64le": 357,
            }
            syscall_number = syscall_numbers.get(platform.machine())
            syscall = getattr(libc, "syscall", None)
            if syscall is None or syscall_number is None:
                raise OSError(errno.ENOTSUP, "renameat2 is unavailable")
            syscall.restype = ctypes.c_long
            result = syscall(
                syscall_number, parent_fd, source, parent_fd, destination, 0x00000001
            )  # RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOTSUP, "no-replace directory rename is unavailable")
    if result != 0:
        error_number = ctypes.get_errno() or errno.EIO
        raise OSError(error_number, os.strerror(error_number))
