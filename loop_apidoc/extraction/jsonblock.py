from __future__ import annotations

import json
import re

_LABELED = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)
_ANY = re.compile(r"```\s*\n(.*?)```", re.DOTALL)


def _try_load(candidate: str) -> dict | None:
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _find_bare_object(text: str) -> dict | None:
    """Find the first balanced top-level JSON object in `text` and load it.

    NotebookLM frequently emits raw JSON for structured stages — correct content,
    but without ```fences. We brace-match (ignoring braces inside strings) so an
    unfenced object is still recovered."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    block = _try_load(text[start : i + 1])
                    if block is not None:
                        return block
                    break  # malformed from this start; try the next "{"
        start = text.find("{", start + 1)
    return None


def extract_json_block(text: str) -> dict | None:
    for pattern in (_LABELED, _ANY):
        match = pattern.search(text)
        if match:
            block = _try_load(match.group(1).strip())
            if block is not None:
                return block
    return _find_bare_object(text)


def find_gaps(block: dict) -> list[str]:
    gaps: list[str] = []
    for key, value in block.items():
        if key == "missing":
            continue
        if value is None:
            gaps.append(key)
    missing = block.get("missing")
    if isinstance(missing, list):
        for item in missing:
            gaps.append(str(item))
    seen: set[str] = set()
    ordered: list[str] = []
    for gap in gaps:
        if gap not in seen:
            seen.add(gap)
            ordered.append(gap)
    return ordered
