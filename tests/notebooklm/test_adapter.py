from __future__ import annotations

from pathlib import Path

import pytest

from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.errors import AuthRequired, MalformedOutput, TransientError
from loop_apidoc.notebooklm.runner import CommandResult

SEP = "=" * 60


def _runner(result: CommandResult):
    def run(argv: list[str]) -> CommandResult:
        return CommandResult(argv=argv, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    return run


def _ok(stdout: str) -> CommandResult:
    return CommandResult(argv=[], returncode=0, stdout=stdout, stderr="")


def _fail(stdout: str) -> CommandResult:
    return CommandResult(argv=[], returncode=1, stdout=stdout, stderr="")


def _config() -> SkillConfig:
    return SkillConfig(skill_root=Path("/skill"))


def test_auth_status_parses_success():
    adapter = NotebookLMAdapter(_config(), _runner(_ok("  Authenticated: Yes\n")))
    status = adapter.auth_status()
    assert status.authenticated is True


def test_ask_returns_parsed_answer():
    stdout = (
        f"{SEP}\nQuestion: List endpoints\n{SEP}\n\n"
        "GET /users.\n\n"
        "EXTREMELY IMPORTANT: Is that ALL you need to know?\n\n"
        f"{SEP}\n"
    )
    adapter = NotebookLMAdapter(_config(), _runner(_ok(stdout)))
    result = adapter.ask("List endpoints", "https://nb/x")
    assert result.answer == "GET /users."
    assert result.question == "List endpoints"
    assert result.notebook_url == "https://nb/x"
    assert result.raw_stdout == stdout


def test_ask_raises_auth_required_on_marker():
    adapter = NotebookLMAdapter(_config(), _runner(_fail("⚠️ Not authenticated")))
    with pytest.raises(AuthRequired):
        adapter.ask("q", "https://nb/x")


def test_ask_raises_transient_on_timeout():
    adapter = NotebookLMAdapter(_config(), _runner(_fail("❌ Timeout waiting for answer")))
    with pytest.raises(TransientError):
        adapter.ask("q", "https://nb/x")


def test_ask_raises_malformed_on_unparsable_success():
    adapter = NotebookLMAdapter(_config(), _runner(_ok("garbage with no markers")))
    with pytest.raises(MalformedOutput):
        adapter.ask("q", "https://nb/x")
