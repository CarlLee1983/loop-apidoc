"""Normalize a downloaded HTML documentation page into auditable Markdown."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from loop_apidoc.url_catalog import _Element, _TreeParser, _walk

#: 一個儲存格能橫跨多少欄／列才算可信。真實參數表不會超過這個量級,而超過的值
#: 幾乎都是壞掉的 HTML;把它照單展開會生出一張沒人寫過的表。
_MAX_COLSPAN = 16
_MAX_ROWSPAN = 64


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

    def inline_text(
        item: _Element,
        *,
        exclude_lists: bool = False,
        exclude_tables: bool = False,
    ) -> str:
        """Render readable inline content without resolving or inventing links."""
        parts: list[str] = []

        def visit(node: _Element | str) -> None:
            if isinstance(node, str):
                parts.append(node)
                return
            if node.tag in ignored or (exclude_lists and node.tag in {"ul", "ol"}):
                return
            # A nested table is rendered as its own table, so pulling its text into
            # the enclosing cell would state the same rows twice — once as a run-on
            # sentence that no longer says which value belongs to which column.
            if exclude_tables and node.tag == "table":
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

    def own_rows(table: _Element) -> list[_Element]:
        """This table's own rows, `thead` first, nested tables left to themselves.

        A nested table's rows belong to it. Collecting every descendant `tr`
        appends them to the enclosing table, where they line up against the wrong
        columns — and a misaligned parameter table becomes a source fact the
        source never stated.
        """
        head: list[_Element] = []
        body: list[_Element] = []

        def visit(node: _Element, *, in_head: bool) -> None:
            for child in node.children:
                if not isinstance(child, _Element) or child.tag == "table":
                    continue
                if child.tag == "tr":
                    (head if in_head else body).append(child)
                    continue
                visit(child, in_head=in_head or child.tag == "thead")

        visit(table, in_head=False)
        return head + body

    def nested_tables(table: _Element) -> list[_Element]:
        """The outermost tables inside this one; each renders itself recursively."""
        found: list[_Element] = []

        def visit(node: _Element) -> None:
            for child in node.children:
                if not isinstance(child, _Element):
                    continue
                if child.tag == "table":
                    found.append(child)
                else:
                    visit(child)

        visit(table)
        return found

    def span(cell: _Element, attribute: str, limit: int) -> int:
        """A span the document actually states, or 1.

        Out-of-range and non-numeric values fall back to 1 rather than being
        clamped to the limit: `colspan="9999"` is a broken document, and honouring
        it as "the widest we allow" would invent a shape nobody wrote.
        """
        try:
            value = int(cell.attrs.get(attribute, "1"))
        except ValueError:
            return 1
        return value if 1 <= value <= limit else 1

    def table_grid(rows: list[_Element]) -> list[list[str]]:
        """Expand `colspan`/`rowspan` into a rectangular grid.

        GFM has no spans, so a spanning cell is repeated across the positions it
        occupies in HTML. That is what the document says: the cell *is* in those
        cells. Leaving them blank would drop the group label that tells a reader
        which rows a nested field belongs to.
        """
        cells: dict[tuple[int, int], str] = {}
        for index, row in enumerate(rows):
            column = 0
            for cell in row.children:
                if not isinstance(cell, _Element) or cell.tag not in {"th", "td"}:
                    continue
                while (index, column) in cells:
                    column += 1
                text = inline_text(cell, exclude_tables=True).replace("|", r"\|")
                columns = span(cell, "colspan", _MAX_COLSPAN)
                down = min(span(cell, "rowspan", _MAX_ROWSPAN), len(rows) - index)
                for offset in range(down):
                    for shift in range(columns):
                        cells[(index + offset, column + shift)] = text
                column += columns
        if not cells:
            return []
        width = max(column for _, column in cells) + 1
        height = max(index for index, _ in cells) + 1
        return [
            [cells.get((index, column), "") for column in range(width)]
            for index in range(height)
        ]

    def render_table(table: _Element) -> str:
        rows = table_grid(own_rows(table))
        blocks: list[str] = []
        if rows:
            header, *body = rows
            width = len(header)
            lines = [
                "| " + " | ".join(header) + " |",
                "| " + " | ".join(["---"] * width) + " |",
            ]
            lines += ["| " + " | ".join(row) + " |" for row in body]
            blocks.append("\n".join(lines))
        blocks += [
            rendered
            for rendered in (render_table(nested) for nested in nested_tables(table))
            if rendered
        ]
        return "\n\n".join(blocks)

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
