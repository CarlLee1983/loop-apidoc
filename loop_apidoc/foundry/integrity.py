from __future__ import annotations

import hashlib
import json
from pathlib import Path

from loop_apidoc.foundry.models import FoundryInputError


def read_verified_file(
    path: Path,
    expected_digest: str,
    label: str = "artifact",
    *,
    max_bytes: int | None = None,
) -> bytes:
    """Capture one regular file and verify the bytes that the caller consumes."""
    if path.is_symlink() or not path.is_file():
        raise FoundryInputError(f"artifact is missing or unsafe: {label}")
    try:
        with path.open("rb") as stream:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if max_bytes is not None and total > max_bytes:
                    raise FoundryInputError(f"artifact exceeds size limit: {label}")
                chunks.append(chunk)
    except FoundryInputError:
        raise
    except OSError as exc:
        raise FoundryInputError(f"cannot read artifact: {label}") from exc
    content = b"".join(chunks)
    if hashlib.sha256(content).hexdigest() != expected_digest:
        raise FoundryInputError(f"artifact digest is stale: {label}")
    return content


def digest_artifact(path: Path, kind: str, label: str = "artifact") -> str:
    """Digest one governed file or deterministic regular-file tree."""
    if kind == "file":
        if path.is_symlink() or not path.is_file():
            raise FoundryInputError(f"artifact is missing or unsafe: {label}")
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise FoundryInputError(f"cannot read artifact: {label}") from exc
    if kind != "tree":
        raise FoundryInputError(f"unknown artifact kind: {label}")
    if path.is_symlink() or not path.is_dir():
        raise FoundryInputError(f"artifact is missing or unsafe: {label}")
    entries: list[tuple[str, str]] = []
    try:
        for child in sorted(path.rglob("*")):
            if child.is_symlink():
                raise FoundryInputError(f"unsafe artifact path: {label}")
            if child.is_dir():
                continue
            if not child.is_file():
                raise FoundryInputError(f"artifact contains a non-file: {label}")
            entries.append(
                (
                    child.relative_to(path).as_posix(),
                    hashlib.sha256(child.read_bytes()).hexdigest(),
                )
            )
    except OSError as exc:
        raise FoundryInputError(f"cannot read artifact: {label}") from exc
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
