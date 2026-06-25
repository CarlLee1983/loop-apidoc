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


def scan_sources(root: Path, scanned_at: datetime) -> list[LocalSource]:
    sources: list[LocalSource] = []
    seen_hashes: dict[str, str] = {}  # sha256 -> first relative_path

    files = sorted(
        (p for p in root.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(root).as_posix(),
    )

    for path in files:
        relative_path = path.relative_to(root).as_posix()
        source_format = detect_format(path)
        supported = is_supported(source_format)
        sha256 = hash_file(path)

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
                size_bytes=path.stat().st_size,
                sha256=sha256,
                scanned_at=scanned_at,
                supported=supported,
                status=status,
                duplicate_of=duplicate_of,
            )
        )

    return sources
