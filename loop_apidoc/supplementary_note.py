"""Import a hand-written excerpt of supplier correspondence as a supplementary source.

供應商信件與通訊軟體裡的補充說明常常是規範性資訊的唯一出處,但它不是
文件:沒有 URL、沒有版本、`check-freshness` 無法週期性重走。這條路徑讓
它進得來、留得下出處,而不冒充正式文件 —— manifest 會把它標成
`supplementary`,填得了 `missing`,支撐不了 `explicit_support`。

形狀取自 `rendered_url.py`:那條路徑要解的問題完全相同 —— 一份沒有可
驗證出處的檔案,靠強制記錄出處欄位、帶時區的時間戳、檔案雜湊、版本化
sidecar 與 fail-closed 的讀取端驗證,換得可追溯性。

**接受的破口**:摘錄是人寫的,摘錄者可能寫錯或過度解讀,pipeline 無法
分辨。`excerpted_by` 記下的是**可追責**,不是可驗證。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


SUPPLEMENTARY_SUFFIXES = {".md", ".markdown"}


class SupplementaryNoteError(ValueError):
    """The excerpt provenance is invalid or would overwrite existing evidence."""


class SupplementaryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    authority: Literal["supplementary"]
    received_from: str
    received_at: datetime
    subject: str | None = None
    excerpted_by: str
    imported_sha256: str
    source_file: str

    @field_validator("received_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("received_at must include a timezone offset")
        return value


@dataclass(frozen=True)
class SupplementaryNoteImport:
    source_path: Path
    provenance_path: Path
    sha256: str


def _received_time(value: str) -> datetime:
    """Return the normalized instant, not the operator's spelling.

    `+0800` 與 `+08:00`、結尾 `Z` 與 `+00:00` 是同一個時刻的不同寫法。
    保留原樣會讓兩份 sidecar 的時間欄位無法直接比較,而 `rendered_url.py`
    寫的是 `isoformat()` —— 形狀既然取自它,這裡就不該各走各的。
    """
    try:
        received_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SupplementaryNoteError(
            "received_at must be an ISO-8601 timestamp"
        ) from exc
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise SupplementaryNoteError("received_at must include a timezone offset")
    return received_at


def _source_name(input_file: Path, filename: str | None) -> str:
    name = filename or input_file.name
    candidate = Path(name)
    if candidate.name != name or name in {".", ".."}:
        raise SupplementaryNoteError("filename must be a single file name")
    if candidate.suffix.lower() not in SUPPLEMENTARY_SUFFIXES:
        raise SupplementaryNoteError("supplementary excerpt must be Markdown")
    return name


def import_supplementary_note(
    input_file: Path,
    *,
    received_from: str,
    received_at: str,
    excerpted_by: str,
    sources: Path,
    subject: str | None = None,
    filename: str | None = None,
) -> SupplementaryNoteImport:
    """Copy the excerpt into `sources/` and write its immutable provenance."""
    if not received_from.strip():
        raise SupplementaryNoteError("received_from must not be empty")
    if not excerpted_by.strip():
        raise SupplementaryNoteError("excerpted_by must not be empty")
    received = _received_time(received_at)
    name = _source_name(input_file, filename)
    source_path = sources / name
    provenance_path = source_path.with_suffix(source_path.suffix + ".source.json")
    for output in (source_path, provenance_path):
        if output.exists() or output.is_symlink():
            raise SupplementaryNoteError(f"output already exists: {output}")

    try:
        raw = input_file.read_bytes()
    except OSError as exc:
        raise SupplementaryNoteError(f"cannot read excerpt: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    # 寫入端與讀取端共用同一個模型:手組 dict 會讓 schema 與實際寫出的
    # 檔案無聲漂移,而讀取端是 fail-closed 的,漂移會變成拒絕。
    provenance = SupplementaryProvenance(
        schema_version=1,
        authority="supplementary",
        received_from=received_from,
        received_at=received,
        subject=subject,
        excerpted_by=excerpted_by,
        imported_sha256=digest,
        source_file=name,
    ).model_dump(mode="json", exclude_none=True)

    sources.mkdir(parents=True, exist_ok=True)
    with source_path.open("xb") as handle:
        handle.write(raw)
    with provenance_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(provenance, ensure_ascii=False, indent=2))
    return SupplementaryNoteImport(
        source_path=source_path,
        provenance_path=provenance_path,
        sha256=digest,
    )
