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
    elements = list(_walk(parser.root))
    root = next(
        (
            item
            for tag in ("main", "article", "body")
            for item in elements
            if item.tag == tag
        ),
        parser.root,
    )
    lines: list[tuple[str, bool]] = []
    ignored = {"aside", "footer", "nav", "script", "style", "template"}

    def add_line(value: str, *, deduplicate: bool = True) -> None:
        if value:
            lines.append((value, deduplicate))

    def plain_text(item: _Element, *, exclude_lists: bool = False) -> str:
        parts: list[str] = []

        def visit(node: _Element | str) -> None:
            if isinstance(node, str):
                parts.append(node)
                return
            if node.tag in ignored or (exclude_lists and node.tag in {"ul", "ol"}):
                return
            for child in node.children:
                visit(child)

        visit(item)
        return " ".join("".join(parts).split())

    def inline_text(item: _Element, *, exclude_lists: bool = False) -> str:
        """Render readable inline content without resolving or inventing links."""
        parts: list[str] = []

        def visit(node: _Element | str) -> None:
            if isinstance(node, str):
                parts.append(node)
                return
            if node.tag in ignored or (exclude_lists and node.tag in {"ul", "ol"}):
                return
            if node.tag == "a":
                label = plain_text(node)
                href = node.attrs.get("href", "")
                if label:
                    parts.append(f"[{label}]({href})" if href else label)
                return
            for child in node.children:
                visit(child)

        visit(item)
        return " ".join("".join(parts).split())

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
                inline_text(cell).replace("|", r"\|")
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

    def render_list(list_element: _Element, depth: int) -> list[str]:
        list_lines: list[str] = []

        def nested_lists(item: _Element) -> list[_Element]:
            found: list[_Element] = []

            def visit(node: _Element) -> None:
                for child in node.children:
                    if not isinstance(child, _Element):
                        continue
                    if child.tag in {"ul", "ol"}:
                        found.append(child)
                    else:
                        visit(child)

            visit(item)
            return found

        marker = "-" if list_element.tag == "ul" else None
        index = 0
        for item in list_element.children:
            if not isinstance(item, _Element) or item.tag != "li":
                continue
            index += 1
            value = inline_text(item, exclude_lists=True)
            if value:
                prefix = marker or f"{index}."
                list_lines.append(f"{'  ' * depth}{prefix} {value}")
            for nested_list in nested_lists(item):
                list_lines.extend(render_list(nested_list, depth + 1))
        return list_lines

    def visit(item: _Element) -> None:
        if item.tag in ignored:
            return
        if item.tag == "table":
            rendered = render_table(item)
            if rendered:
                add_line(rendered)
            return
        if item.tag == "pre":
            code = raw_text(item).strip("\n")
            if code:
                add_line(f"```\n{code}\n```")
            return
        if item.tag in {"ul", "ol"}:
            rendered = render_list(item, 0)
            if rendered:
                add_line("\n".join(rendered), deduplicate=False)
            return
        value = inline_text(item)
        if item.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            if value:
                add_line(f"{'#' * int(item.tag[1])} {value}")
            return
        if item.tag == "p" and value:
            add_line(value)
            return
        for child in item.children:
            if isinstance(child, _Element):
                visit(child)

    visit(root)
    unique_lines: list[str] = []
    seen: set[str] = set()
    for line, deduplicate in lines:
        if deduplicate and line in seen:
            continue
        if deduplicate:
            seen.add(line)
        unique_lines.append(line)
    return "\n\n".join(unique_lines) + ("\n" if unique_lines else "")


def normalize_html_snapshot(input_file: Path, url: str, output: Path) -> Path:
    """Write Markdown plus a sidecar binding it to immutable raw evidence."""
    raw = input_file.read_bytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_to_markdown(raw.decode("utf-8", errors="replace")), encoding="utf-8")
    sidecar = output.with_suffix(output.suffix + ".source.json")
    sidecar.write_text(json.dumps({"url": url, "raw_file": str(input_file), "raw_sha256": sha256(raw).hexdigest(), "normalized_file": str(output), "normalized_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar
