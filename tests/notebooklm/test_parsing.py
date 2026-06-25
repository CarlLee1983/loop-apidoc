from __future__ import annotations

import pytest

from loop_apidoc.notebooklm.errors import MalformedOutput
from loop_apidoc.notebooklm.parsing import parse_ask_answer, parse_auth_status

SEP = "=" * 60


def _ask_stdout(answer: str = "GET /users and POST /users.") -> str:
    return (
        "💬 Asking: List endpoints\n"
        "📚 Notebook: https://nb/x\n"
        "  ✅ Got answer!\n\n"
        f"{SEP}\n"
        "Question: List endpoints\n"
        f"{SEP}\n\n"
        f"{answer}\n\n"
        "EXTREMELY IMPORTANT: Is that ALL you need to know? You can always ask another question!\n\n"
        f"{SEP}\n"
    )


def test_parse_auth_status_yes_with_stale_warning():
    stdout = (
        "⚠️ Browser state is 9.2 days old, may need re-authentication\n"
        "🔐 Authentication Status:\n"
        "  Authenticated: Yes\n"
        "  State file: /x/state.json\n"
    )
    status = parse_auth_status(stdout)
    assert status.authenticated is True
    assert status.stale_warning is not None
    assert "9.2 days old" in status.stale_warning
    assert status.raw_stdout == stdout


def test_parse_auth_status_no():
    status = parse_auth_status("🔐 Authentication Status:\n  Authenticated: No\n")
    assert status.authenticated is False
    assert status.stale_warning is None


def test_parse_auth_status_unparsable_raises():
    with pytest.raises(MalformedOutput):
        parse_auth_status("totally unrelated output")


def test_parse_ask_answer_extracts_between_markers():
    assert parse_ask_answer(_ask_stdout()) == "GET /users and POST /users."


def test_parse_ask_answer_multiline_answer():
    answer = "Line one.\nLine two.\nLine three."
    assert parse_ask_answer(_ask_stdout(answer)) == answer


def test_parse_ask_answer_missing_followup_raises():
    bad = f"{SEP}\nQuestion: q\n{SEP}\n\nsome answer\n"  # no follow-up marker
    with pytest.raises(MalformedOutput):
        parse_ask_answer(bad)


def test_parse_ask_answer_empty_answer_raises():
    with pytest.raises(MalformedOutput):
        parse_ask_answer(_ask_stdout(answer="   "))
