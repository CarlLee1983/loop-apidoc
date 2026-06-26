from __future__ import annotations

from loop_apidoc.extraction.stages import QueryKind, QueryStage, StageMode

# We deliberately send SHORT, self-contained questions with no preamble and no
# embedded prior-answer context. A heavy preamble or an abridged "known so far"
# block made NotebookLM treat the prompt as a truncated/pasted message and reply
# with confused non-answers (and never emit the requested JSON). The notebook
# chat is cleared before each query on the skill side, so every question already
# stands alone. A prompt experiment confirmed `goal + json_hint` reliably yields
# parseable JSON, while the old context-carrying prompts did not.
_LEAD = "Using only the sources in this notebook, "

# For complex structured stages NotebookLM tends to drift into prose unless told
# forcefully to emit nothing but JSON. The bare-object parser then recovers it
# whether or not it adds ```fences.
_JSON_ONLY = (
    "Reply with NOTHING but a single JSON object — no introduction, no "
    "explanation, no prose before or after it. "
)

_PROSE_RULE = (
    " Answer in prose, strictly from the sources, and state explicitly anything "
    "the sources do not cover."
)

# Per-endpoint detail extraction (stage 06). NotebookLM reliably details ONE
# endpoint per focused query but collapses "every endpoint at once" to a single
# entry, so the orchestrator fans this out across the stage-05 endpoint list.
# The shape maps directly onto EndpointEntry's detail fields.
_ENDPOINT_DETAIL_SHAPE = (
    'Use this exact JSON shape: {"method": str, "path": str, "parameters": '
    '[{"name": str, "in": "query"|"header"|"path"|"body"|null, "type": str|null, '
    '"required": bool|null, "description": str|null}], "request": {"content_type": '
    'str|null, "schema": str|null, "required": bool|null, "description": str|null}'
    '|null, "responses": [{"status": str, "description": str|null, "schema": '
    'str|null}], "examples": [obj], "missing": [str]}. For anything the sources do '
    "not state use null/empty and add a label to `missing`. Do not invent values."
)


def build_endpoint_detail_question(
    method: str, path: str, name: str | None = None
) -> str:
    label = f"{method} {path}" + (f" ({name})" if name else "")
    return (
        f"{_JSON_ONLY}{_LEAD}give the full integration details for the {label} "
        "endpoint in this API: every request parameter, the request body, every "
        "response (each with its status code or label), and any examples. "
        f"{_ENDPOINT_DETAIL_SHAPE}"
    )


def build_question(
    stage: QueryStage,
    kind: QueryKind,
    *,
    pending_fields: list[str] | None = None,
) -> str:
    if kind is QueryKind.REVERSE:
        # Keep "Topic: <title>" as a stable anchor for the stage.
        return (
            f"Topic: {stage.title}. {_LEAD}list anything important about this topic "
            "that is easy to miss, anywhere the sources conflict, and anything the "
            "sources do not cover. Answer strictly from the sources — do not guess."
        )

    if kind is QueryKind.FOLLOWUP:
        fields = ", ".join(pending_fields or [])
        return (
            f"{_JSON_ONLY}{_LEAD}{stage.goal} The following items are still unfilled: "
            f"{fields}. Re-output the FULL JSON object; keep anything the sources do "
            f"not state in the `missing` array. {stage.json_hint}"
        )

    # INITIAL
    if stage.mode is StageMode.STRUCTURED:
        return f"{_JSON_ONLY}{_LEAD}{stage.goal}\n{stage.json_hint}"
    return f"{_LEAD}{stage.goal}{_PROSE_RULE}"
