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

    Returned paths are relative to `dest_dir`. The existing flat output naming
    and overwrite-on-name-collision behavior is intentionally preserved.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    converted: list[Path] = []
    copied: list[Path] = []
    passthrough: list[Path] = []

    paths = [sources] if sources.is_file() else sorted(sources.rglob("*"))
    for path in paths:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            relative = Path(f"{path.stem}.md")
            md = pdf_to_markdown(path)
            (dest_dir / relative).write_text(md, encoding="utf-8")
            converted.append(relative)
        elif suffix in _TEXT_SUFFIXES:
            relative = Path(path.name)
            (dest_dir / relative).write_text(
                path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
            )
            copied.append(relative)
        else:
            relative = Path(path.name)
            (dest_dir / relative).write_bytes(path.read_bytes())
            passthrough.append(relative)

    return PreprocessResult(
        dest_dir=dest_dir,
        converted=converted,
        copied=copied,
        passthrough=passthrough,
    )
