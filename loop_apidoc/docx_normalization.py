"""Securely normalize one OOXML Word document into auditable Markdown.

This façade preserves the public normalization interface while package validation,
rendering, and publication remain cohesive sibling modules.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from loop_apidoc.docx_models import (
    DocxNormalizationError,
    DocxNormalizationResult,
    PreparedDocx,
    StageFile,
)
from loop_apidoc.docx_publish import write_prepared_docx
from loop_apidoc.docx_render import document_to_markdown
from loop_apidoc.docx_validation import SECURITY_POLICY_VERSION, validate_docx_package


MAX_ARCHIVE_BYTES = 25 * 1024 * 1024


def _read_source(input_file: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow and input_file.is_symlink():
        raise DocxNormalizationError("DOCX-SOURCE-TYPE: source must be a regular file")
    try:
        descriptor = os.open(input_file, flags | nofollow)
    except OSError as exc:
        raise DocxNormalizationError("input is not a readable DOCX package") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise DocxNormalizationError(
                "DOCX-SOURCE-TYPE: source must be a regular file"
            )
        if metadata.st_size > MAX_ARCHIVE_BYTES:
            raise DocxNormalizationError("DOCX-ZIP-SIZE: archive exceeds policy")
        chunks: list[bytes] = []
        remaining = MAX_ARCHIVE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise DocxNormalizationError("DOCX-ZIP-SIZE: archive exceeds policy")
        return raw
    except OSError as exc:
        raise DocxNormalizationError("input is not a readable DOCX package") from exc
    finally:
        os.close(descriptor)


def prepare_docx(input_file: Path, normalized_name: str) -> PreparedDocx:
    """Validate and render one DOCX fully in memory before any output is written."""
    raw = _read_source(input_file)
    document = validate_docx_package(raw)
    normalized = document_to_markdown(document).encode("utf-8")
    provenance = {
        "schema_version": 1,
        "security_policy_version": SECURITY_POLICY_VERSION,
        "normalizer": "loop-apidoc-docx",
        "source_file": input_file.name,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_size_bytes": len(raw),
        "normalized_file": normalized_name,
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        "normalized_size_bytes": len(normalized),
    }
    return PreparedDocx(markdown=normalized, provenance=provenance)


def normalize_docx(input_file: Path, output: Path) -> DocxNormalizationResult:
    """Normalize one DOCX without executing or resolving package relationships."""
    return write_prepared_docx(prepare_docx(input_file, output.name), output)


__all__ = [
    "DocxNormalizationError",
    "DocxNormalizationResult",
    "PreparedDocx",
    "SECURITY_POLICY_VERSION",
    "StageFile",
    "normalize_docx",
    "prepare_docx",
    "write_prepared_docx",
]
