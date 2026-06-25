from __future__ import annotations

from loop_apidoc.notebooklm.errors import MalformedOutput
from loop_apidoc.notebooklm.models import AuthStatus

SEPARATOR = "=" * 60
FOLLOW_UP_MARKER = "EXTREMELY IMPORTANT: Is that ALL you need to know?"
_AUTH_YES = "Authenticated: Yes"
_AUTH_NO = "Authenticated: No"
_STALE_PREFIX = "⚠️ Browser state is"


def parse_auth_status(stdout: str) -> AuthStatus:
    if _AUTH_YES in stdout:
        authenticated = True
    elif _AUTH_NO in stdout:
        authenticated = False
    else:
        raise MalformedOutput(
            "auth_manager status output missing 'Authenticated:' line",
            stdout=stdout,
        )
    stale_warning = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(_STALE_PREFIX):
            stale_warning = stripped
            break
    return AuthStatus(
        authenticated=authenticated, raw_stdout=stdout, stale_warning=stale_warning
    )


def parse_ask_answer(stdout: str) -> str:
    follow_idx = stdout.find(FOLLOW_UP_MARKER)
    if follow_idx == -1:
        raise MalformedOutput(
            "ask_question output missing follow-up reminder marker", stdout=stdout
        )
    head = stdout[:follow_idx]
    question_idx = head.find("Question:")
    if question_idx == -1:
        raise MalformedOutput(
            "ask_question output missing 'Question:' header", stdout=stdout
        )
    sep_idx = head.find(SEPARATOR, question_idx)
    if sep_idx == -1:
        raise MalformedOutput(
            "ask_question output missing closing separator after question",
            stdout=stdout,
        )
    answer = head[sep_idx + len(SEPARATOR) :].strip()
    if not answer:
        raise MalformedOutput("ask_question produced an empty answer", stdout=stdout)
    return answer
