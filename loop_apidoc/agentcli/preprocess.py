from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pymupdf4llm

from loop_apidoc.docx_normalization import (
    PreparedDocx,
    prepare_docx,
    write_prepared_docx,
)

# Source formats we can flatten to markdown text for the agent to read. Other
# formats are copied byte-for-byte so no declared source silently disappears.
_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


@dataclass(frozen=True)
class PreprocessResult:
    dest_dir: Path
    converted: list[Path]
    copied: list[Path]
    passthrough: list[Path]


class PreprocessKind(Enum):
    CONVERTED_PDF = "converted-pdf"
    CONVERTED_DOCX = "converted-docx"
    COPIED_TEXT = "copied"
    PASSTHROUGH = "passthrough"

    @classmethod
    def from_suffix(cls, suffix: str) -> PreprocessKind:
        if suffix == ".pdf":
            return cls.CONVERTED_PDF
        if suffix == ".docx":
            return cls.CONVERTED_DOCX
        if suffix in _TEXT_SUFFIXES:
            return cls.COPIED_TEXT
        return cls.PASSTHROUGH

    @property
    def converts_to_markdown(self) -> bool:
        return self in {self.CONVERTED_PDF, self.CONVERTED_DOCX}

    @property
    def requires_docx_preflight(self) -> bool:
        return self is self.CONVERTED_DOCX


@dataclass(frozen=True)
class PreprocessItem:
    source: Path
    relative: Path
    kind: PreprocessKind

    @classmethod
    def from_source(cls, source: Path, source_relative: Path) -> PreprocessItem:
        kind = PreprocessKind.from_suffix(source.suffix.lower())
        relative = (
            source_relative.with_name(f"{source_relative.name}.md")
            if kind.converts_to_markdown
            else source_relative
        )
        return cls(source=source, relative=relative, kind=kind)

    @property
    def claimed_outputs(self) -> tuple[Path, ...]:
        if self.kind.requires_docx_preflight:
            sidecar = self.relative.with_suffix(self.relative.suffix + ".source.json")
            return self.relative, sidecar
        return (self.relative,)


def pdf_to_markdown(pdf_path: Path) -> str:
    """Convert a PDF to GitHub-flavoured markdown, one page at a time, with page
    markers so the agent can cite pages. Unlike raw text extraction this
    preserves tables (as markdown tables) and heading structure — critical for
    faithfully recovering parameter tables into schemas. Reading this (~tens of K
    tokens) is far cheaper per query than re-parsing the PDF every time."""
    chunks = pymupdf4llm.to_markdown(
        str(pdf_path), page_chunks=True, show_progress=False
    )
    parts: list[str] = []
    for chunk in chunks:
        page_no = chunk["metadata"]["page_number"]
        parts.append(f"\n\n<!-- page {page_no} -->\n")
        parts.append(chunk["text"])
    return "".join(parts)


def prepare_markdown(sources: Path, dest_dir: Path) -> PreprocessResult:
    """Convert a source directory or one source file into `dest_dir`.

    Returned paths are relative to `dest_dir`. Directory input preserves each
    source's relative path. Converted PDFs add ``.md`` to their original
    filename, so ``guide.pdf`` becomes ``guide.pdf.md`` without colliding with
    a sibling ``guide.md``.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    converted: list[Path] = []
    copied: list[Path] = []
    passthrough: list[Path] = []

    paths = [sources] if sources.is_file() else sorted(sources.rglob("*"))
    planned: list[PreprocessItem] = []
    for path in paths:
        if not path.is_file():
            continue
        source_relative = Path(path.name) if sources.is_file() else path.relative_to(sources)
        planned.append(PreprocessItem.from_source(path, source_relative))

    destinations: dict[Path, Path] = {}
    for item in planned:
        for claim in item.claimed_outputs:
            prior = destinations.setdefault(claim, item.source)
            if prior != item.source:
                raise ValueError(
                    "preprocess output collision: "
                    f"{prior} and {item.source} both map to {dest_dir / claim}"
                )

    for item in planned:
        if not item.kind.requires_docx_preflight:
            continue
        if any((dest_dir / claim).exists() for claim in item.claimed_outputs):
            raise ValueError("DOCX normalization output already exists")

    prepared_docx: dict[Path, PreparedDocx] = {
        item.source: prepare_docx(item.source, item.relative.name)
        for item in planned
        if item.kind.requires_docx_preflight
    }

    for item in planned:
        output_path = dest_dir / item.relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if item.kind is PreprocessKind.CONVERTED_PDF:
            output_path.write_text(pdf_to_markdown(item.source), encoding="utf-8")
            converted.append(item.relative)
        elif item.kind is PreprocessKind.CONVERTED_DOCX:
            write_prepared_docx(prepared_docx[item.source], output_path)
            converted.append(item.relative)
        elif item.kind is PreprocessKind.COPIED_TEXT:
            output_path.write_text(
                item.source.read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8",
            )
            copied.append(item.relative)
        else:
            output_path.write_bytes(item.source.read_bytes())
            passthrough.append(item.relative)

    return PreprocessResult(
        dest_dir=dest_dir,
        converted=converted,
        copied=copied,
        passthrough=passthrough,
    )
