"""Small, dependency-neutral primitives for immutable directory publication."""

from __future__ import annotations

import ctypes
import errno
import os
import platform
import sys
from pathlib import Path


class DirectoryPublicationCollisionError(RuntimeError):
    """The immutable publication destination already exists."""


class DirectoryPublicationError(RuntimeError):
    """The platform cannot atomically publish a directory without replacement."""


def publish_directory_noreplace(
    staged_directory: Path,
    destination: Path,
    *,
    parent_fd: int | None = None,
) -> None:
    """Atomically publish ``staged_directory`` only when ``destination`` is absent.

    POSIX ``rename`` would replace an empty destination directory, so it is not a
    valid fallback for immutable runs. macOS and Linux expose explicit no-replace
    variants; every other platform fails closed.  A caller that has already
    pinned the containing directory may pass its descriptor so publication never
    reopens a replaceable pathname.
    """
    close_parent = parent_fd is None
    if parent_fd is None:
        if staged_directory.parent != destination.parent:
            raise DirectoryPublicationError(
                "directory publication requires one parent directory"
            )
        parent_fd = os.open(destination.parent, _directory_open_flags())
    try:
        rename_directory_noreplace(
            parent_fd,
            os.fsencode(staged_directory.name),
            os.fsencode(destination.name),
        )
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
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def rename_directory_noreplace(
    parent_fd: int, source: bytes, destination: bytes
) -> None:
    """Perform the platform no-replace rename relative to one open parent."""
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
        result = renameatx_np(
            parent_fd,
            source,
            parent_fd,
            destination,
            0x00000004 | 0x00000010 | 0x00000020,  # EXCL | NOFOLLOW_ANY | BENEATH
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
