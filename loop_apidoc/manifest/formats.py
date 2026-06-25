from __future__ import annotations

import mimetypes
from pathlib import Path

from loop_apidoc.manifest.models import SourceFormat

_EXTENSION_FORMATS: dict[str, SourceFormat] = {
    ".pdf": SourceFormat.PDF,
    ".md": SourceFormat.MARKDOWN,
    ".markdown": SourceFormat.MARKDOWN,
    ".docx": SourceFormat.WORD,
    ".doc": SourceFormat.WORD,
    ".json": SourceFormat.OPENAPI_JSON,
    ".yaml": SourceFormat.OPENAPI_YAML,
    ".yml": SourceFormat.OPENAPI_YAML,
}


def detect_format(path: Path) -> SourceFormat:
    return _EXTENSION_FORMATS.get(path.suffix.lower(), SourceFormat.UNKNOWN)


def is_supported(source_format: SourceFormat) -> bool:
    return source_format is not SourceFormat.UNKNOWN


def guess_mime_type(path: Path) -> str | None:
    mime, _ = mimetypes.guess_type(path.name)
    return mime
