from __future__ import annotations

# An agent extraction backend occasionally returns process-level success
# (returncode 0) while the answer is not a real answer: an outright refusal, a
# truncated/continuation-confused reply, or a request for clarification. These
# answers must not be baked into the normalization plan; we surface them as
# retriable so the adapter can raise TransientError and the retry path re-queries
# (spec §11).
#
# Markers are kept tight to avoid flagging legitimate answers. Each is a phrase
# emitted when the backend is NOT answering the question.
_UNRELIABLE_MARKERS = (
    "我目前無法回覆",  # refusal (zh-TW)
    "previous conversation",  # context bleed from accumulated chat history
    "message was cut off",  # truncation/continuation confusion
    "clarify what you would like",  # confused clarification request
    "i cannot answer",  # generic refusal (en)
    "i'm unable to answer",  # generic refusal (en)
    # zh-TW equivalents — the backend answers in the source language, so the same
    # refusal/context-bleed replies appear in Chinese for Chinese sources.
    "似乎被截斷",  # "your message seems truncated"
    "被截斷的訊息",  # "a truncated message"
    "貼上了一段之前的對話",  # "you pasted a previous conversation"
    "似乎貼上",  # "you seem to have pasted ..."
    "想先探討哪",  # "which part would you like to explore first" (clarification)
)


def detect_unreliable_answer(answer: str) -> str | None:
    """Return a human-readable reason if `answer` looks like a refusal or
    context-bleed reply, else None.

    Detection is case-insensitive substring matching against known markers.
    A blank answer is also treated as unreliable.
    """
    stripped = answer.strip()
    if not stripped:
        return "extractor returned a blank answer"

    lowered = stripped.lower()
    for marker in _UNRELIABLE_MARKERS:
        if marker.lower() in lowered:
            return f"extractor answer matched unreliable marker: {marker!r}"
    return None
