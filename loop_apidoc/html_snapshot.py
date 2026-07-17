"""Normalize a downloaded HTML documentation page into auditable Markdown."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from loop_apidoc.url_catalog import _Element, _TreeParser, _walk


def html_to_markdown(html: str) -> str:
    """Extract readable main-document text without inventing content."""
    parser = _TreeParser()
    parser.feed(html)
    parser.close()
    root = next((item for item in _walk(parser.root) if item.tag == "main"), parser.root)
    lines: list[str] = []
    ignored = {"aside", "footer", "nav", "script", "style", "template"}

    def text(item: _Element) -> str:
        """Inline text with whitespace collapsed (headings, cells, paragraphs)."""
        parts: list[str] = []
        for child in item.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in ignored:
                parts.append(text(child))
        return " ".join(" ".join(parts).split())

    def raw_text(item: _Element) -> str:
        """Descendant text with line breaks preserved (code blocks)."""
        parts: list[str] = []
        for child in item.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in ignored:
                parts.append(raw_text(child))
        return "".join(parts)

    def render_table(table: _Element) -> str:
        rows: list[list[str]] = []
        for row in (e for e in _walk(table) if e.tag == "tr"):
            cells = [
                text(cell).replace("|", r"\|")
                for cell in row.children
                if isinstance(cell, _Element) and cell.tag in {"th", "td"}
            ]
            if cells:
                rows.append(cells)
        if not rows:
            return ""
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        header, *body = rows
        out = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * width) + " |",
        ]
        out += ["| " + " | ".join(row) + " |" for row in body]
        return "\n".join(out)

    consumed: set[int] = set()
    for item in _walk(root):
        if id(item) in consumed or item.tag in ignored:
            continue
        if item.tag == "table":
            for descendant in _walk(item):
                consumed.add(id(descendant))
            rendered = render_table(item)
            if rendered:
                lines.append(rendered)
            continue
        if item.tag == "pre":
            for descendant in _walk(item):
                consumed.add(id(descendant))
            code = raw_text(item).strip("\n")
            if code:
                lines.append(f"```\n{code}\n```")
            continue
        value = text(item)
        if not value:
            continue
        if item.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            lines.append(f"{'#' * int(item.tag[1])} {value}")
        elif item.tag == "li":
            lines.append(f"- {value}")
        elif item.tag == "p":
            lines.append(value)
    return "\n\n".join(dict.fromkeys(line for line in lines if line)) + ("\n" if lines else "")


def normalize_html_snapshot(input_file: Path, url: str, output: Path) -> Path:
    """Write Markdown plus a sidecar binding it to immutable raw evidence."""
    raw = input_file.read_bytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_to_markdown(raw.decode("utf-8", errors="replace")), encoding="utf-8")
    sidecar = output.with_suffix(output.suffix + ".source.json")
    sidecar.write_text(json.dumps({"url": url, "raw_file": str(input_file), "raw_sha256": sha256(raw).hexdigest(), "normalized_file": str(output), "normalized_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar
