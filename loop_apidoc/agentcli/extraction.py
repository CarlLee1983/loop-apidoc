from __future__ import annotations

import json

# Which inventory key feeds which plan stage; each becomes that stage's INITIAL
# structured answer so build_normalization_plan consumes it unchanged.
_INVENTORY_STAGES: tuple[tuple[str, str], ...] = (
    ("03", "environments"),
    ("04", "security_schemes"),
    ("05", "endpoints"),
    ("07", "schemas"),
    ("08", "errors"),
    ("09", "operational"),
)


def _block(key: str, inventory: dict) -> str:
    # The global `missing` list is surfaced once via stage 10; copying it into
    # every inventory stage block here would make the plan record each gap once
    # per stage and the guide repeat it N times.
    value = inventory.get(key)
    payload = {key: value if isinstance(value, list) else []}
    return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def _stage00(inventory: dict) -> str:
    """Encode the source title (and optional document version) for stage 00.

    Title-only stays plain text (the long-standing contract); when a source
    version is present we emit a small JSON object so the version survives the
    text-artifact seam into the plan and OpenAPI `info.version`."""
    title = str(inventory.get("title") or "").strip()
    version = str(inventory.get("version") or "").strip()
    if version:
        payload = {"title": title or None, "version": version}
        return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    return title


def inventory_to_stage_answers(inventory: dict) -> dict[str, str]:
    """Split one inventory JSON into per-stage answer texts (pure).

    The agent-native `assemble` path writes inventory.json directly; this maps it
    into the per-stage INITIAL answers build_normalization_plan consumes."""
    answers: dict[str, str] = {
        "00": _stage00(inventory),
        "01": "Source inventory: a single source manual was provided and read.",
        "02": str(inventory.get("overview") or "").strip()
        or "(no overview stated)",
        # Stage 10 is the one global gap/conflict stage. Keep its payload
        # structured so `build_normalization_plan` can preserve these missing
        # items for completeness validation without duplicating them into every
        # inventory stage.
        "10": "```json\n" + json.dumps(
            {"missing": inventory.get("missing") or []}, ensure_ascii=False
        ) + "\n```",
    }
    for stage_id, key in _INVENTORY_STAGES:
        answers[stage_id] = _block(key, inventory)
    return answers
