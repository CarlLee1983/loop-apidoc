"""Pure, conservative scanning of structured Markdown API facts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from loop_apidoc.markdown_drafts.models import DraftExample, DraftField, EndpointDraft, MarkdownDraft


_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_ENDPOINT = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s`*,)】]+)", re.IGNORECASE)
_FENCE = re.compile(r"^\s{0,3}(?P<fence>`{3,}|~{3,})\s*(?P<info>\S*)")
_BOLD_LABEL = re.compile(r"^\s*\*\*(?P<label>.+?)\*\*\s*$")
_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
_EXAMPLE_LANGUAGES = {"json", "jsonc", "xml", "text", "plaintext", "http", "curl", "yaml", "yml"}


@dataclass
class _OpenEndpoint:
    method: str
    path: str
    heading: str
    level: int
    start_line: int
    fields: list[DraftField] = field(default_factory=list)
    examples: list[DraftExample] = field(default_factory=list)

    def close(self, end_line: int) -> EndpointDraft:
        return EndpointDraft(
            method=self.method,
            path=self.path,
            heading=self.heading,
            start_line=self.start_line,
            end_line=max(self.start_line, end_line),
            fields=tuple(self.fields),
            examples=tuple(self.examples),
        )


def scan_markdown_drafts(relative_path: str, text: str) -> MarkdownDraft:
    """Scan only explicit endpoint headings, labelled tables, and fenced examples."""
    lines = text.splitlines()
    endpoints: list[EndpointDraft] = []
    current: _OpenEndpoint | None = None
    current_label: str | None = None
    omitted_tables = 0
    index = 0

    while index < len(lines):
        line_number = index + 1
        raw = lines[index]
        heading = _HEADING.match(raw)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            declared = _endpoint_heading(title)
            if current is not None and level <= current.level:
                endpoints.append(current.close(index))
                current = None
                current_label = None
            if declared is not None:
                method, path = declared
                current = _OpenEndpoint(method, path, title, level, line_number)
                current_label = None
            elif current is not None:
                current_label = _section_label(title)
            index += 1
            continue

        fence = _FENCE.match(raw)
        if fence:
            closing = _find_closing_fence(lines, index + 1, fence.group("fence"))
            if current is not None:
                language = fence.group("info").lower()
                if language in _EXAMPLE_LANGUAGES:
                    current.examples.append(
                        DraftExample(
                            language=language,
                            label=current_label,
                            start_line=line_number,
                            end_line=closing + 1,
                            content="\n".join(lines[index + 1:closing]),
                        )
                    )
            index = closing + 1
            continue

        if raw.lstrip().startswith("|"):
            rows: list[tuple[int, str]] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append((index + 1, lines[index]))
                index += 1
            fields = _table_fields(rows, current_label)
            if current is not None and fields:
                current.fields.extend(fields)
            else:
                omitted_tables += 1
            continue
        inline = _inline_endpoint(raw)
        if inline is not None:
            if current is not None:
                endpoints.append(current.close(index))
            method, path = inline
            current = _OpenEndpoint(method, path, raw.strip(), 0, line_number)
            current_label = None
            index += 1
            continue
        bold_label = _BOLD_LABEL.match(raw)
        if current is not None and bold_label is not None:
            current_label = _section_label(bold_label.group("label"))
        index += 1

    if current is not None:
        endpoints.append(current.close(len(lines)))
    return MarkdownDraft(
        relative_path=relative_path,
        endpoints=tuple(endpoints),
        omitted_tables=omitted_tables,
    )


def _endpoint_heading(title: str) -> tuple[str, str] | None:
    match = _ENDPOINT.search(title)
    if match is None:
        return None
    return match.group(1).upper(), match.group(2).rstrip("`*.,;:。；、")


def _inline_endpoint(line: str) -> tuple[str, str] | None:
    """Recognize GitBook's literal ``<mark>`POST`</mark> `/path``` form."""
    methods = re.findall(r"`(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)`", line, flags=re.IGNORECASE)
    paths = re.findall(r"`(/[^`\s]+)`", line)
    if len(methods) != 1 or len(paths) != 1:
        return None
    return methods[0].upper(), paths[0]


def _section_label(title: str) -> str | None:
    normalized = " ".join(title.lower().split())
    if "header" in normalized or "標頭" in title:
        return "headers"
    if "query" in normalized or "查詢" in title:
        return "query"
    if "response" in normalized or "回應" in title:
        return "response"
    if "request" in normalized or "body" in normalized or "請求" in title or "本文" in title:
        return "request"
    return None


def _find_closing_fence(lines: list[str], start: int, opening: str) -> int:
    marker = opening[0] * len(opening)
    for index in range(start, len(lines)):
        if lines[index].lstrip().startswith(marker):
            return index
    return len(lines)


def _table_fields(rows: list[tuple[int, str]], label: str | None) -> list[DraftField]:
    if label is None or len(rows) < 3:
        return []
    headers = _cells(rows[0][1])
    separator = _cells(rows[1][1])
    if len(headers) != len(separator) or not all(_SEPARATOR_CELL.fullmatch(cell) for cell in separator):
        return []
    columns = _columns(headers)
    if columns["name"] is None:
        return []
    fields: list[DraftField] = []
    for line, raw in rows[2:]:
        cells = _cells(raw)
        if len(cells) != len(headers):
            continue
        name = cells[columns["name"]].strip(" `")
        if not name or (name.startswith("**") and name.endswith("**")):
            continue
        fields.append(
            DraftField(
                label=label,
                name=name,
                type=_cell_at(cells, columns["type"]),
                required=_cell_at(cells, columns["required"]),
                description=_cell_at(cells, columns["description"]),
                start_line=line,
                end_line=line,
            )
        )
    return fields


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _columns(headers: list[str]) -> dict[str, int | None]:
    normalized = [" ".join(header.lower().split()) for header in headers]
    aliases = {
        "name": {"name", "field", "parameter", "param", "欄位", "參數", "名稱"},
        "type": {"type", "format", "型別", "格式"},
        "required": {"required", "mandatory", "必填", "是否必填"},
        "description": {"description", "desc", "說明", "描述"},
    }
    return {
        key: next((index for index, value in enumerate(normalized) if value in values), None)
        for key, values in aliases.items()
    }


def _cell_at(cells: list[str], index: int | None) -> str | None:
    if index is None or not cells[index]:
        return None
    return cells[index]
