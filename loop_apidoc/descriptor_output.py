"""Descriptor-bound output paths for an immutable assembly stage.

``pathlib.Path`` resolves each operation through the process cwd or a named
ancestor.  A run stage can be renamed while it is assembled, so output writers
need a small path-shaped adapter that always opens below the held stage
descriptor instead.  This module deliberately exposes only the mutating
operations the assembly writers need; it never exports a pathname for the
descriptor it owns.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePath


class DescriptorOutputError(RuntimeError):
    """A requested output operation cannot remain below its held descriptor."""


def _directory_flags() -> int:
    directory = getattr(os, "O_DIRECTORY", None)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if directory is None or no_follow is None:
        raise DescriptorOutputError(
            "secure descriptor-relative output is unavailable on this platform"
        )
    return os.O_RDONLY | directory | no_follow | getattr(os, "O_CLOEXEC", 0)


def _components(value: str | Path) -> tuple[str, ...]:
    raw = os.fspath(value)
    if "\\" in raw:
        raise DescriptorOutputError(f"unsafe output path: {raw}")
    relative = PurePath(raw)
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise DescriptorOutputError(f"unsafe output path: {raw}")
    return tuple(part for part in relative.parts if part != ".")


def _identity(descriptor: int) -> tuple[int, int]:
    metadata = os.fstat(descriptor)
    return metadata.st_dev, metadata.st_ino


def _open_named_directory(parent_fd: int, name: str) -> int:
    try:
        return os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise DescriptorOutputError("output directory is unavailable") from exc


def _create_owned_directory(
    output: DescriptorOutput,
    parent_fd: int,
    parts: tuple[str, ...],
    mode: int,
) -> int:
    """Create, pin, and require an empty directory below an owned parent."""
    leaf = parts[-1]
    try:
        os.mkdir(leaf, mode, dir_fd=parent_fd)
    except FileExistsError as exc:
        raise DescriptorOutputError("output directory is not owned") from exc
    descriptor = -1
    try:
        created = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(created.st_mode):
            raise DescriptorOutputError("new output entry is not a directory")
        expected = created.st_dev, created.st_ino
        descriptor = _open_named_directory(parent_fd, leaf)
        if _identity(descriptor) != expected:
            raise DescriptorOutputError("new output directory identity changed")
        if os.listdir(descriptor):
            raise DescriptorOutputError("new output directory is not empty")
        output._remember_directory(parts, descriptor)
        os.fsync(parent_fd)
        return descriptor
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        # Do not remove the pathname here.  It can have been replaced after
        # creation, and descriptor-bound cleanup must never remove a foreign
        # entry.
        raise


def _open_directory(
    output: DescriptorOutput,
    parts: tuple[str, ...],
    *,
    create: bool,
) -> int:
    descriptor = os.dup(output._root_fd())
    try:
        for index, part in enumerate(parts, start=1):
            child_parts = parts[:index]
            expected = output._directory_identity(child_parts)
            if expected is None:
                if not create:
                    raise DescriptorOutputError("output directory is not owned")
                child = _create_owned_directory(
                    output, descriptor, child_parts, 0o700
                )
            else:
                child = _open_named_directory(descriptor, part)
                try:
                    if _identity(child) != expected:
                        raise DescriptorOutputError("output directory identity changed")
                except BaseException:
                    os.close(child)
                    raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_known_directory(output: DescriptorOutput, parts: tuple[str, ...]) -> int:
    return _open_directory(output, parts, create=False)


class DescriptorOutput:
    """Own one writable directory descriptor for the duration of a run stage."""

    def __init__(self, directory_fd: int) -> None:
        self._fd = os.dup(directory_fd)
        self._closed = False
        root_metadata = os.fstat(self._fd)
        if not stat.S_ISDIR(root_metadata.st_mode):
            os.close(self._fd)
            raise DescriptorOutputError("output descriptor is not a directory")
        # A new assembly stage is private and starts empty.  Accepting a
        # pre-populated replacement would let an attacker smuggle arbitrary
        # artifacts (including hard links) into an otherwise valid run.
        if os.listdir(self._fd):
            os.close(self._fd)
            raise DescriptorOutputError("new output stage is not empty")
        self._directories: dict[tuple[str, ...], tuple[int, int]] = {
            (): (root_metadata.st_dev, root_metadata.st_ino)
        }
        self._files: dict[tuple[str, ...], tuple[int, int]] = {}

    @property
    def root(self) -> DescriptorOutputPath:
        return DescriptorOutputPath(self, ())

    def close(self) -> None:
        if not self._closed:
            os.close(self._fd)
            self._closed = True

    def _root_fd(self) -> int:
        if self._closed:
            raise DescriptorOutputError("output descriptor is closed")
        return self._fd

    def _directory_identity(self, parts: tuple[str, ...]) -> tuple[int, int] | None:
        return self._directories.get(parts)

    def _remember_directory(self, parts: tuple[str, ...], descriptor: int) -> None:
        identity = _identity(descriptor)
        existing = self._directories.get(parts)
        if existing is not None and existing != identity:
            raise DescriptorOutputError("output directory identity changed")
        self._directories[parts] = identity

    def _remember_file(self, parts: tuple[str, ...], descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise DescriptorOutputError("output leaf is not a regular file")
        identity = metadata.st_dev, metadata.st_ino
        existing = self._files.get(parts)
        if existing is not None and existing != identity:
            raise DescriptorOutputError("output file identity changed")
        self._files[parts] = identity

    def verify_ownership(self) -> None:
        """Require the stage namespace to contain only its owned artifacts."""
        if self._closed:
            raise DescriptorOutputError("output descriptor is closed")
        for parts in sorted(self._directories, key=lambda value: (len(value), value)):
            descriptor = _open_known_directory(self, parts)
            try:
                expected_children = {
                    child[-1]
                    for child in self._directories
                    if len(child) == len(parts) + 1 and child[:-1] == parts
                }
                expected_children.update(
                    child[-1]
                    for child in self._files
                    if len(child) == len(parts) + 1 and child[:-1] == parts
                )
                if set(os.listdir(descriptor)) != expected_children:
                    raise DescriptorOutputError("output stage namespace changed")
            finally:
                os.close(descriptor)
        for parts, expected in self._files.items():
            parent = _open_known_directory(self, parts[:-1])
            descriptor = -1
            try:
                descriptor = os.open(
                    parts[-1],
                    os.O_RDONLY
                    | getattr(os, "O_NONBLOCK", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=parent,
                )
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode) or (
                    metadata.st_dev,
                    metadata.st_ino,
                ) != expected:
                    raise DescriptorOutputError("output file identity changed")
            except OSError as exc:
                raise DescriptorOutputError("output stage namespace changed") from exc
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                os.close(parent)


@dataclass(frozen=True, slots=True)
class DescriptorOutputPath:
    """One relative location below :class:`DescriptorOutput`.

    It intentionally mirrors the narrow mutable ``Path`` interface used by
    assembly writers.  Every call opens parents with ``openat`` and
    ``O_NOFOLLOW`` from the original output descriptor; relative process cwd
    is never consulted.
    """

    _output: DescriptorOutput
    _parts: tuple[str, ...]

    @property
    def name(self) -> str:
        return self._parts[-1] if self._parts else ""

    @property
    def parent(self) -> DescriptorOutputPath:
        if not self._parts:
            return self
        return DescriptorOutputPath(self._output, self._parts[:-1])

    def __truediv__(self, value: str | Path) -> DescriptorOutputPath:
        return DescriptorOutputPath(self._output, self._parts + _components(value))

    def mkdir(
        self,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if not self._parts:
            if exist_ok:
                return
            raise FileExistsError("descriptor output root already exists")
        parent_fd = self._open_directory(self._parts[:-1], create=parents)
        try:
            leaf = self._parts[-1]
            expected = self._output._directory_identity(self._parts)
            if expected is not None:
                if not exist_ok:
                    raise FileExistsError("descriptor output directory already exists")
                descriptor = _open_named_directory(parent_fd, leaf)
                try:
                    if _identity(descriptor) != expected:
                        raise DescriptorOutputError("output directory identity changed")
                finally:
                    os.close(descriptor)
                return
            descriptor = _create_owned_directory(
                self._output, parent_fd, self._parts, mode
            )
            os.close(descriptor)
        finally:
            os.close(parent_fd)

    def write_text(
        self,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        parent_fd, leaf = self._open_leaf_parent()
        descriptor = -1
        try:
            descriptor = os.open(
                leaf,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=parent_fd,
            )
            self._output._remember_file(self._parts, descriptor)
            with os.fdopen(
                descriptor,
                "w",
                encoding=encoding,
                errors=errors,
                newline=newline,
            ) as handle:
                descriptor = -1
                written = handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.fsync(parent_fd)
            return written
        except FileExistsError as exc:
            raise DescriptorOutputError(
                f"output leaf already exists: {self}"
            ) from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            os.close(parent_fd)

    def _open_leaf_parent(self) -> tuple[int, str]:
        if not self._parts:
            raise IsADirectoryError("descriptor output root has no file leaf")
        return self._open_directory(self._parts[:-1], create=False), self._parts[-1]

    def _open_directory(self, parts: tuple[str, ...], *, create: bool) -> int:
        return _open_directory(self._output, parts, create=create)

    def verify_ownership(self) -> None:
        """Verify every generated entry before the outer stage is published."""
        self._output.verify_ownership()

    def __str__(self) -> str:
        return "/".join(self._parts) if self._parts else "."


@contextmanager
def output_path_from_fd(directory_fd: int) -> Iterator[DescriptorOutputPath]:
    """Yield a relative output root whose writes stay bound to ``directory_fd``."""
    output = DescriptorOutput(directory_fd)
    try:
        yield output.root
    finally:
        output.close()


OutputPath = Path | DescriptorOutputPath
