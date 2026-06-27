from __future__ import annotations

from pathlib import Path

import pymupdf4llm

# Source formats we can flatten to markdown text for the agent to read. Other
# formats (already-text) are copied as-is.
_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


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


def prepare_markdown(sources_dir: Path, dest_dir: Path) -> Path:
    """Convert every PDF under `sources_dir` to markdown in `dest_dir` (a derived
    location OUTSIDE sources/ so it never pollutes the source manifest). Returns
    the dest dir. Non-PDF text sources are copied verbatim."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(sources_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            md = pdf_to_markdown(path)
            (dest_dir / f"{path.stem}.md").write_text(md, encoding="utf-8")
        elif suffix in _TEXT_SUFFIXES:
            (dest_dir / path.name).write_text(
                path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
            )
    return dest_dir
