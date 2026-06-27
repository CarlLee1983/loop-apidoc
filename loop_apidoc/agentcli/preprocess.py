from __future__ import annotations

from pathlib import Path

import fitz  # pymupdf

# Source formats we can flatten to markdown text for the agent to read. Other
# formats (already-text) are copied as-is.
_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


def pdf_to_markdown(pdf_path: Path) -> str:
    """Flatten a PDF to plain markdown-ish text, one page at a time, with page
    markers so the agent can cite pages. Reading this (~tens of K tokens) is far
    cheaper per query than re-parsing the PDF every time."""
    parts: list[str] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            parts.append(f"\n\n<!-- page {i + 1} -->\n")
            parts.append(page.get_text())
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
