from __future__ import annotations

import mimetypes
from pathlib import Path

from loop_apidoc.manifest.models import SourceFormat

_EXTENSION_FORMATS: dict[str, SourceFormat] = {
    ".pdf": SourceFormat.PDF,
    ".md": SourceFormat.MARKDOWN,
    ".markdown": SourceFormat.MARKDOWN,
    ".docx": SourceFormat.WORD,
    ".doc": SourceFormat.WORD_LEGACY,
    ".json": SourceFormat.OPENAPI_JSON,
    ".yaml": SourceFormat.OPENAPI_YAML,
    ".yml": SourceFormat.OPENAPI_YAML,
    ".html": SourceFormat.HTML,
    ".htm": SourceFormat.HTML,
}


def detect_format(path: Path) -> SourceFormat:
    return _EXTENSION_FORMATS.get(path.suffix.lower(), SourceFormat.UNKNOWN)


#: 認得出格式不等於讀得動。舊版二進位 Word 沒有前處理路徑(`preprocess` 只轉
#: `.pdf`/`.docx`),掃描器也讀不了它,所以標成 supported 是一句不成立的宣稱——
#: 而 manifest 是 operator 第一個看到的東西。
_UNSUPPORTED = (SourceFormat.UNKNOWN, SourceFormat.WORD_LEGACY)


def is_supported(source_format: SourceFormat) -> bool:
    return source_format not in _UNSUPPORTED


def guess_mime_type(path: Path) -> str | None:
    mime, _ = mimetypes.guess_type(path.name)
    return mime
