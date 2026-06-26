from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from loop_apidoc.manifest.formats import detect_format, guess_mime_type, is_supported
from loop_apidoc.manifest.models import LocalSource, ProcessingStatus

_CHUNK_SIZE = 1 << 20  # 1 MiB


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


def scan_sources(root: Path, scanned_at: datetime) -> list[LocalSource]:
    sources: list[LocalSource] = []
    seen_hashes: dict[str, str] = {}  # sha256 -> first relative_path
    root_resolved = root.resolve()

    files = sorted(
        (p for p in root.rglob("*") if _is_regular_file(p)),
        key=lambda p: p.relative_to(root).as_posix(),
    )

    for path in files:
        relative_path = path.relative_to(root).as_posix()
        source_format = detect_format(path)
        supported = is_supported(source_format)

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
