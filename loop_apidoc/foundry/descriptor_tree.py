"""Descriptor-pinned copy of trusted regular-file artifact trees."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path, PurePath

from loop_apidoc.foundry import descriptor_namespace
from loop_apidoc.foundry.models import FoundryInputError, FoundryPublicationError


def copy_tree_to_directory(source: Path, destination_fd: int, name: str) -> None:
    """Copy a regular-file tree into a new pinned destination directory."""
    source_fd = _open_source_directory(source)
    target_fd = -1
    target_identity: tuple[int, int] | None = None
    try:
        os.mkdir(name, 0o700, dir_fd=destination_fd)
        target_fd = descriptor_namespace._open_directory(
            name, parent_fd=destination_fd
        )
        opened = os.fstat(target_fd)
        target_identity = opened.st_dev, opened.st_ino
        _copy_tree_contents(source_fd, target_fd)
        os.fsync(target_fd)
    except BaseException as primary:
        if target_identity is None:
            raise
        try:
            descriptor_namespace.remove_owned_entry_relative(
                destination_fd, name, target_identity
            )
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
        name, target_fd, identity = descriptor_namespace.create_owned_directory_relative(
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
                descriptor_namespace.remove_owned_entry_relative(
                    destination_fd, name, identity
                )
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
        descriptor = descriptor_namespace._open_directory(source)
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
                source_child_fd = descriptor_namespace._open_directory(
                    name, parent_fd=source_fd
                )
                opened = os.fstat(source_child_fd)
                if not stat.S_ISDIR(opened.st_mode) or not os.path.samestat(
                    metadata, opened
                ):
                    raise FoundryInputError(
                        f"candidate artifact is unsafe: {label}"
                    )
                os.mkdir(name, 0o700, dir_fd=destination_fd)
                target_child_fd = descriptor_namespace._open_directory(
                    name, parent_fd=destination_fd
                )
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
