from __future__ import annotations

import json

from loop_apidoc.notebooklm.errors import MalformedOutput, TransientError


def parse_agent_result(stdout: str) -> str:
    """Extract the answer text from a `claude -p --output-format json` envelope.

    The envelope is a single JSON object whose `result` holds the answer; a
    non-zero `is_error` (e.g. a usage limit or transient model error) is mapped
    to TransientError so the retry path can act on it.
    """
    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise MalformedOutput(
            "agent CLI did not return a JSON envelope", stdout=stdout
        ) from exc
    if not isinstance(envelope, dict):
        raise MalformedOutput("agent CLI envelope was not an object", stdout=stdout)
    if envelope.get("is_error"):
        raise TransientError(
            f"agent CLI reported an error: {envelope.get('subtype') or 'unknown'}",
            stdout=stdout,
        )
    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        raise MalformedOutput(
            "agent CLI envelope missing a non-empty 'result'", stdout=stdout
        )
    return result
