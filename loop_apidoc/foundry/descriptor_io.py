"""Descriptor-pinned JSON and immutable-entry I/O for Foundry persistence."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from loop_apidoc.foundry import descriptor_namespace, head_io
from loop_apidoc.foundry.models import FoundryInputError, FoundryPublicationError

_ModelT = TypeVar("_ModelT", bound=BaseModel)


@dataclass
class ImmutableEntryPublication:
    """Ownership token for a newly linked immutable governed entry."""

    owned_entry: bool = False
    identity: tuple[int, int] | None = None


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
        resolved_parent_fd, basename = descriptor_namespace._open_relative_parent(
            parent_fd, name
        )
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
        descriptor = descriptor_namespace.open_directory_relative(parent_fd, name)
    except FoundryInputError:
        raise
    except OSError as exc:
        raise FoundryInputError(f"artifact is missing or unsafe: {label}") from exc
    try:
        entries: list[tuple[str, str]] = []
        _digest_tree_entries(descriptor, entries, label=label)
        descriptor_namespace.validate_directory_relative(parent_fd, name, descriptor)
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
                child_fd = descriptor_namespace._open_directory(
                    name, parent_fd=directory_fd
                )
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
                descriptor_namespace.validate_directory_relative(
                    directory_fd, name, child_fd
                )
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

def write_model_relative(parent_fd: int, name: str, model: BaseModel) -> None:
    """Write a new/replaceable model beneath a pinned directory tree."""
    resolved_parent_fd, basename = descriptor_namespace._open_relative_parent(
        parent_fd, name
    )
    try:
        head_io._atomic_write_model_relative(
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
        directory_fd = descriptor_namespace.ensure_directory_relative(
            parent_fd, parent_name
        )
        os.close(directory_fd)
    resolved_parent_fd, basename = descriptor_namespace._open_relative_parent(
        parent_fd, name
    )
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
            snapshot = head_io.read_head_snapshot_relative(
                resolved_parent_fd, basename
            )
            if snapshot.content is None or snapshot.original_identity is None:
                raise FoundryPublicationError(
                    f"governed immutable output disappeared: {name}"
                )
            if (
                descriptor_namespace.entry_identity_relative(resolved_parent_fd, basename)
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
        if (
            descriptor_namespace.entry_identity_relative(resolved_parent_fd, basename)
            != identity
        ):
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
