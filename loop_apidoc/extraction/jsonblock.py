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


def extract_json_block(text: str) -> dict | None:
    for pattern in (_LABELED, _ANY):
        match = pattern.search(text)
        if match:
            block = _try_load(match.group(1).strip())
            if block is not None:
                return block
    return None


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
