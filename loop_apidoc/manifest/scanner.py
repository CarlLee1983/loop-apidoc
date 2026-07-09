from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from loop_apidoc.manifest.formats import detect_format, guess_mime_type, is_supported
from loop_apidoc.manifest.models import LocalSource, ProcessingStatus

_CHUNK_SIZE = 1 << 20  # 1 MiB

# Repository furniture that happens to be readable but is never an API spec.
# Left in the manifest as `ignored` rather than dropped, so an operator can see
# what the scan decided. A stray README that says something endpoint-shaped must
# not become source evidence.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    "README*",
    "LICENSE*",
    "LICENCE*",
    "CHANGELOG*",
    "CONTRIBUTING*",
    ".DS_Store",
    ".git/*",
)


def is_excluded(relative_path: str, patterns: Sequence[str]) -> bool:
    """A pattern matches either the whole POSIX relative path or the basename."""
    name = PurePosixPath(relative_path).name
    return any(fnmatch(relative_path, p) or fnmatch(name, p) for p in patterns)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_regular_file(path: Path) -> bool:
    try:
        if path.is_file():
            return True
        # Broken symlink: exists as an entry but target is gone.
        return path.is_symlink()
    except OSError:
        return False


def _within_root(path: Path, root_resolved: Path) -> bool:
    """True when `path` resolves to a location inside `root_resolved`.

    Broken symlinks resolve (strict=False) to a still-inside-root target and
    stay readable-then-unreadable as before; symlinks pointing outside the
    source root resolve elsewhere and are rejected here so we never hash
    content the operator did not place under --sources."""
    try:
        return path.resolve().is_relative_to(root_resolved)
    except OSError:
        return False


def scan_sources(
    root: Path,
    scanned_at: datetime,
    excludes: Sequence[str] = (),
) -> list[LocalSource]:
    """Scan `root` for sources. `excludes` adds to DEFAULT_EXCLUDES; matches are
    recorded with status `ignored` and are never hashed or read."""
    sources: list[LocalSource] = []
    seen_hashes: dict[str, str] = {}  # sha256 -> first relative_path
    root_resolved = root.resolve()
    patterns = (*DEFAULT_EXCLUDES, *excludes)

    files = sorted(
        (p for p in root.rglob("*") if _is_regular_file(p)),
        key=lambda p: p.relative_to(root).as_posix(),
    )

    for path in files:
        relative_path = path.relative_to(root).as_posix()
        source_format = detect_format(path)
        supported = is_supported(source_format)

        if is_excluded(relative_path, patterns):
            sources.append(
                LocalSource(
                    relative_path=relative_path,
                    mime_type=guess_mime_type(path),
                    source_format=source_format,
                    size_bytes=0,
                    sha256="",
                    scanned_at=scanned_at,
                    supported=False,
                    status=ProcessingStatus.IGNORED,
                    duplicate_of=None,
                )
            )
            continue

        if not _within_root(path, root_resolved):
            sources.append(
                LocalSource(
                    relative_path=relative_path,
                    mime_type=guess_mime_type(path),
                    source_format=source_format,
                    size_bytes=0,
                    sha256="",
                    scanned_at=scanned_at,
                    supported=False,
                    status=ProcessingStatus.UNREADABLE,
                    duplicate_of=None,
                )
            )
            continue

        try:
            sha256 = hash_file(path)
            size_bytes = path.stat().st_size
        except OSError:
            sources.append(
                LocalSource(
                    relative_path=relative_path,
                    mime_type=guess_mime_type(path),
                    source_format=source_format,
                    size_bytes=0,
                    sha256="",
                    scanned_at=scanned_at,
                    supported=False,
                    status=ProcessingStatus.UNREADABLE,
                    duplicate_of=None,
                )
            )
            continue

        if not supported:
            status = ProcessingStatus.UNSUPPORTED
            duplicate_of = None
        elif sha256 in seen_hashes:
            status = ProcessingStatus.DUPLICATE
            duplicate_of = seen_hashes[sha256]
        else:
            status = ProcessingStatus.PENDING
            duplicate_of = None
            seen_hashes[sha256] = relative_path

        sources.append(
            LocalSource(
                relative_path=relative_path,
                mime_type=guess_mime_type(path),
                source_format=source_format,
                size_bytes=size_bytes,
                sha256=sha256,
                scanned_at=scanned_at,
                supported=supported,
                status=status,
                duplicate_of=duplicate_of,
            )
        )

    return sources
