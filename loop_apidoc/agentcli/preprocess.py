from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf4llm

# Source formats we can flatten to markdown text for the agent to read. Other
# formats are copied byte-for-byte so no declared source silently disappears.
_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


@dataclass(frozen=True)
class PreprocessResult:
    dest_dir: Path
    converted: list[Path]
    copied: list[Path]
    passthrough: list[Path]


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
    planned: list[tuple[Path, Path, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        source_relative = Path(path.name) if sources.is_file() else path.relative_to(sources)
        if suffix == ".pdf":
            relative = source_relative.with_name(f"{source_relative.name}.md")
            kind = "converted"
        elif suffix in _TEXT_SUFFIXES:
            relative = source_relative
            kind = "copied"
        else:
            relative = source_relative
            kind = "passthrough"
        planned.append((path, relative, kind))

    destinations: dict[Path, Path] = {}
    for path, relative, _kind in planned:
        prior = destinations.setdefault(relative, path)
        if prior != path:
            raise ValueError(
                "preprocess output collision: "
                f"{prior} and {path} both map to {dest_dir / relative}"
            )

    for path, relative, kind in planned:
        output_path = dest_dir / relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "converted":
            output_path.write_text(pdf_to_markdown(path), encoding="utf-8")
            converted.append(relative)
        elif kind == "copied":
            output_path.write_text(
                path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
            )
            copied.append(relative)
        else:
            output_path.write_bytes(path.read_bytes())
            passthrough.append(relative)

    return PreprocessResult(
        dest_dir=dest_dir,
        converted=converted,
        copied=copied,
        passthrough=passthrough,
    )
