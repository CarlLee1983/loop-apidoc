"""Shared values for secure DOCX normalization."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class DocxNormalizationError(ValueError):
    """A DOCX source cannot be normalized safely and completely."""


@dataclass(frozen=True)
class DocxNormalizationResult:
    output: Path
    provenance: Path


@dataclass(frozen=True)
class PreparedDocx:
    markdown: bytes
    provenance: dict[str, object]


StageFile = Callable[[Path, bytes], Path]
