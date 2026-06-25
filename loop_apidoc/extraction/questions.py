from __future__ import annotations

from loop_apidoc.extraction.stages import QueryKind, QueryStage, StageMode

_HEADER = (
    "You are answering one independent question about a NotebookLM notebook. There is "
    "no conversation history, so this message carries all the context you need.\n"
    "Notebook: {notebook_url}\n"
    "Known so far (from earlier questions, for context only — re-verify against the "
    "sources):\n{known_summary}\n"
)


def build_known_summary(prior_answers: list[tuple[str, str]]) -> str:
    if not prior_answers:
        return "(none yet)"
    lines = []
    for title, answer in prior_answers:
        flat = " ".join(answer.split())[:280]
        lines.append(f"- {title}: {flat}")
    return "\n".join(lines)


def _context(stage: QueryStage, notebook_url: str, known_summary: str) -> str:
    return _HEADER.format(notebook_url=notebook_url, known_summary=known_summary)


def build_question(
    stage: QueryStage,
    kind: QueryKind,
    *,
    notebook_url: str,
    known_summary: str,
    pending_fields: list[str] | None = None,
) -> str:
    context = _context(stage, notebook_url, known_summary)

    if kind is QueryKind.REVERSE:
        body = (
            f"Topic: {stage.title}. Review the earlier answers on this topic and list "
            "anything they may have missed, anything where the sources conflict, and any "
            "claim that is not supported by the sources. If the sources are silent on "
            "something, say so plainly — do not guess."
        )
        return context + body

    if kind is QueryKind.FOLLOWUP:
        fields = ", ".join(pending_fields or [])
        body = (
            f"Topic: {stage.title}. The following items are still unfilled: {fields}. "
            "For each, state only what the sources provide. Then re-output the FULL JSON "
            "block for this topic; keep any item the sources still do not provide in the "
            f"`missing` array. {stage.json_hint}"
        )
        return context + body

    # INITIAL
    if stage.mode is StageMode.STRUCTURED:
        body = f"Task: {stage.goal}\n{stage.json_hint}"
    else:
        body = (
            f"Task: {stage.goal} Answer in prose, strictly from the sources, and state "
            "explicitly anything the sources do not cover."
        )
    return context + body
