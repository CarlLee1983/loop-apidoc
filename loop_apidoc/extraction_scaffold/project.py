"""Pure projection of conservative Markdown facts into extraction-shaped files."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from loop_apidoc.extraction_scaffold.models import ScaffoldBundle, ScaffoldEndpoint
from loop_apidoc.markdown_drafts.models import DraftExample, EndpointDraft, MarkdownDraftIndex


_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_HOST = re.compile(r"https://[A-Za-z0-9.-]+(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?")
_ENDPOINT_TOKENS = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+/?\S*", re.IGNORECASE)
_LABEL_TO_LOCATION = {"headers": "header", "query": "query", "request": "body"}
_TRUE_VALUES = frozenset({"yes", "true", "是", "必填", "y"})
_FALSE_VALUES = frozenset({"no", "false", "否", "選填", "n"})
_JSON_LANGUAGES = frozenset({"json", "jsonc"})


def project_scaffold(
    drafts: MarkdownDraftIndex,
    source_texts: Mapping[str, str],
    sources_root_name: str,
) -> ScaffoldBundle:
    """Create a non-authoritative scaffold without reading or writing files."""
    ordered = sorted(
        ((source.relative_path, endpoint) for source in drafts.sources for endpoint in source.endpoints),
        key=lambda item: (item[0], item[1].start_line, item[1].method, item[1].path),
    )
    endpoint_files: list[ScaffoldEndpoint] = []
    inventory_endpoints: list[dict[str, Any]] = []
    per_endpoint: list[dict[str, Any]] = []
    fields = 0
    projected_examples = 0
    unparsed_examples = 0

    for number, (relative_path, endpoint) in enumerate(ordered):
        citation = _citation(relative_path, endpoint.start_line, endpoint.end_line, endpoint.heading)
        body, example_count, unparsed_count = _project_endpoint(endpoint, citation)
        filename = f"ep{number:02d}.json"
        endpoint_files.append(ScaffoldEndpoint(filename=filename, body=body))
        inventory_endpoints.append({
            "method": endpoint.method,
            "path": endpoint.path,
            "summary": _summary(endpoint),
            "source": citation,
            "server": None,
        })
        fields += len(body["parameters"])
        projected_examples += example_count
        unparsed_examples += unparsed_count
        per_endpoint.append({
            "file": f"endpoints/{filename}",
            "method": endpoint.method,
            "path": endpoint.path,
            "field_count": len(body["parameters"]),
            "example_count": example_count,
            "missing": body["missing"],
        })

    inventory_missing = [
        "overview not mechanically derived",
        "security schemes not mechanically derived",
        "schemas not mechanically derived",
        "operational details not mechanically derived",
    ]
    if not _has_concrete_host(source_texts.values()):
        inventory_missing.append("API base URL not stated in scanned sources")
    errors = _appendix_errors(source_texts, drafts)
    inventory = {
        "title": _title(source_texts, sources_root_name),
        "version": None,
        "overview": "",
        "environments": [],
        "security_schemes": [],
        "endpoints": inventory_endpoints,
        "schemas": [],
        "errors": errors,
        "operational": [],
        "missing": inventory_missing,
    }
    report = {
        "kind": "extraction_scaffold",
        "authoritative": False,
        "sources_scanned": len(drafts.sources),
        "endpoints": len(endpoint_files),
        "fields": fields,
        "examples_projected": projected_examples,
        "examples_unparsed": unparsed_examples,
        "omitted_tables": sum(source.omitted_tables for source in drafts.sources),
        "errors_projected": len(errors),
        "per_endpoint": per_endpoint,
        "notes": ["security and signing documents are not mechanically projected"],
    }
    return ScaffoldBundle(inventory=inventory, endpoints=tuple(endpoint_files), report=report)


def parse_required(value: str | None) -> bool | None:
    """Return only an explicit required/optional assertion."""
    normalized = (value or "").strip().casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return None


def _project_endpoint(endpoint: EndpointDraft, citation: str) -> tuple[dict[str, Any], int, int]:
    parameters: list[dict[str, Any]] = []
    missing: list[str] = []
    for field in endpoint.fields:
        location = _LABEL_TO_LOCATION.get(field.label)
        if location is None:
            continue
        required = parse_required(field.required)
        if required is None:
            missing.append(f"required flag missing for {field.name}")
        parameters.append({
            "name": field.name,
            "in": location,
            "type": field.type,
            "required": required,
            "description": field.description,
        })
    has_request_example = any(example.label == "request" for example in endpoint.examples)
    has_response_example = any(example.label == "response" for example in endpoint.examples)
    has_response_fields = any(field.label == "response" for field in endpoint.fields)
    request = (
        {"content_type": "application/json", "schema": None, "required": None, "description": None}
        if any(parameter["in"] == "body" for parameter in parameters) or has_request_example
        else None
    )
    responses = (
        [{"status": "default", "description": None, "schema": None, "schema_ref": None}]
        if has_response_example or has_response_fields
        else []
    )
    if not responses:
        missing.append("response shape not mechanically derived")
    examples, unparsed = _examples(endpoint.examples, missing)
    return ({
        "method": endpoint.method,
        "path": endpoint.path,
        "source": citation,
        "parameters": parameters,
        "request": request,
        "responses": responses,
        "tags": [],
        "security": [],
        "examples": examples,
        "missing": missing,
    }, len(examples), unparsed)


def _examples(examples: tuple[DraftExample, ...], missing: list[str]) -> tuple[list[dict[str, Any]], int]:
    projected: list[dict[str, Any]] = []
    unparsed = 0
    for example in examples:
        line_range = f"{example.start_line}-{example.end_line}"
        if example.language not in _JSON_LANGUAGES:
            missing.append(f"non-JSON example lines {line_range}")
            unparsed += 1
            continue
        try:
            value = json.loads(example.content)
        except json.JSONDecodeError:
            missing.append(f"unparsed JSON example lines {line_range}")
            unparsed += 1
            continue
        projected.append({
            "title": example.label or "example",
            "content_type": "application/json",
            "value": value,
        })
    return projected, unparsed


def _summary(endpoint: EndpointDraft) -> str:
    stripped = _ENDPOINT_TOKENS.sub("", endpoint.heading).strip(" -—:：`*")
    return stripped or endpoint.heading


def _citation(relative_path: str, start_line: int, end_line: int, heading: str | None) -> str:
    citation = f"{relative_path} lines {start_line}-{end_line}"
    return f"{citation} # {heading}" if heading else citation


def _title(source_texts: Mapping[str, str], sources_root_name: str) -> str | None:
    top_level = [path for path in source_texts if "/" not in path and path.endswith(".md")]
    named = [path for path in top_level if path.removesuffix(".md") == sources_root_name]
    candidates = named if len(named) == 1 else top_level if len(top_level) == 1 else []
    if len(candidates) != 1:
        return None
    for line in source_texts[candidates[0]].splitlines():
        match = _HEADING.match(line)
        if match and line.lstrip().startswith("# "):
            return match.group(1).strip()
    return None


def _has_concrete_host(texts: Any) -> bool:
    return any(_HOST.search(_outside_fences(text)) for text in texts)


def _outside_fences(text: str) -> str:
    kept: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        match = _FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker[0]
            elif marker.startswith(fence):
                fence = None
            continue
        if fence is None:
            kept.append(line)
    return "\n".join(kept)


def _appendix_errors(source_texts: Mapping[str, str], drafts: MarkdownDraftIndex) -> list[dict[str, Any]]:
    ranges = {
        source.relative_path: [(endpoint.start_line, endpoint.end_line) for endpoint in source.endpoints]
        for source in drafts.sources
    }
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative_path, text in source_texts.items():
        lines = text.splitlines()
        heading: str | None = None
        index = 0
        while index < len(lines):
            match = _HEADING.match(lines[index])
            if match:
                heading = match.group(1).strip()
            if not lines[index].lstrip().startswith("|"):
                index += 1
                continue
            start = index
            rows: list[tuple[int, str]] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append((index + 1, lines[index]))
                index += 1
            if _within_endpoint(start + 1, ranges.get(relative_path, [])):
                continue
            errors.extend(_error_rows(relative_path, rows, heading, seen))
    return errors


def _within_endpoint(line: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= line <= end for start, end in ranges)


def _error_rows(
    relative_path: str,
    rows: list[tuple[int, str]],
    heading: str | None,
    seen: set[str],
) -> list[dict[str, Any]]:
    if len(rows) < 3:
        return []
    headers = _cells(rows[0][1])
    if len(headers) != len(_cells(rows[1][1])):
        return []
    normalized = [" ".join(header.lower().split()) for header in headers]
    code_index = next((i for i, value in enumerate(normalized) if value in {"code", "error code", "錯誤碼", "错误码"}), None)
    meaning_index = next((i for i, value in enumerate(normalized) if value in {"meaning", "message", "description", "說明", "说明", "描述"}), None)
    if code_index is None or meaning_index is None:
        return []
    results: list[dict[str, Any]] = []
    for line, raw in rows[2:]:
        cells = _cells(raw)
        if len(cells) != len(headers):
            continue
        code = cells[code_index].strip(" `")
        if not code.isdecimal() or code in seen:
            continue
        seen.add(code)
        citation = _citation(relative_path, line, line, heading)
        results.append({
            "code": code,
            "meaning": cells[meaning_index] or None,
            "http_status": None,
            "applicable_to": [],
            "source": citation,
        })
    return results


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]
