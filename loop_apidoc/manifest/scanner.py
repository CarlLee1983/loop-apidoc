from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from loop_apidoc.manifest.formats import detect_format, guess_mime_type, is_supported
from loop_apidoc.manifest.models import (
    LocalSource,
    ProcessingStatus,
    SourceAuthority,
)
from loop_apidoc.supplementary_note import SupplementaryProvenance


class ManifestScanError(ValueError):
    """A source's authority cannot be determined, so scanning must not continue."""


#: sidecar 是人或工具寫的小 JSON;超過這個大小代表它不是 sidecar。
_MAX_SIDECAR_BYTES = 64 * 1024

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
    # normalize-html-snapshot writes this provenance sidecar next to its .md output;
    # it is the tool's own bookkeeping, never source evidence.
    "*.source.json",
)


def _read_authority(path: Path, root_resolved: Path, sha256: str) -> SourceAuthority:
    """Read the source's authority from its `.source.json` sidecar.

    **缺席才是 normative,讀不動不是。** 沒有 sidecar 的來源是正式文件 ——
    現存的每一份來源都是,這是事實而非為了相容編出來的預設值。但一個
    *存在卻讀不動*的 sidecar 意味著等級無從判定,而 fail open 的後果是
    一份次級佐證靜默升級成正式文件:它重新進入 `sole_source()` 與
    `build_fingerprint`,`SUPPLEMENTARY_SUPPORT` 一條都不會報,而操作者
    看不到任何差別。一個截斷的寫入或錯誤的權限就足以關掉整個功能。

    宣告必須綁在內容上:`source_file` 與 `imported_sha256` 都要對得上,
    否則一個從別處複製來的兩行 sidecar 就能把一份正式手冊降級。
    """
    sidecar = path.with_suffix(path.suffix + ".source.json")
    if not sidecar.exists():
        return SourceAuthority.NORMATIVE
    if not _within_root(sidecar, root_resolved) or sidecar.is_symlink():
        raise ManifestScanError(f"來源 sidecar 不在來源目錄內：{sidecar}")
    try:
        if sidecar.stat().st_size > _MAX_SIDECAR_BYTES:
            raise ManifestScanError(f"來源 sidecar 過大：{sidecar}")
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestScanError(
            f"來源 sidecar 存在但讀不動，無法判定來源等級：{sidecar}"
        ) from exc
    except ValueError as exc:
        raise ManifestScanError(
            f"來源 sidecar 不是合法 JSON，無法判定來源等級：{sidecar}"
        ) from exc
    if not isinstance(payload, dict) or "authority" not in payload:
        # `import-rendered-url` 寫的 provenance 沒有 authority 欄位 ——
        # 那是一份已驗證出處的正式文件,不是判定失敗。
        return SourceAuthority.NORMATIVE
    try:
        provenance = SupplementaryProvenance.model_validate(payload)
    except ValidationError as exc:
        raise ManifestScanError(
            f"來源 sidecar 宣告了 authority 但格式不合：{sidecar}：{exc}"
        ) from exc
    if provenance.source_file != path.name:
        raise ManifestScanError(
            f"來源 sidecar 的 source_file 與檔名不符：{sidecar}"
        )
    if provenance.imported_sha256 != sha256:
        raise ManifestScanError(
            f"來源 sidecar 的 SHA-256 與來源內容不符：{sidecar}"
        )
    return SourceAuthority.SUPPLEMENTARY


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
                authority=_read_authority(path, root_resolved, sha256),
            )
        )

    return sources
