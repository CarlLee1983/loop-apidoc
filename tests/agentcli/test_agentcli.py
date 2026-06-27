from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop_apidoc.agentcli.adapter import ClaudeCodeAdapter
from loop_apidoc.agentcli.commands import GROUNDING_SYSTEM_PROMPT, build_ask_argv
from loop_apidoc.agentcli.config import AgentConfig
from loop_apidoc.agentcli.parsing import parse_agent_result
from loop_apidoc.notebooklm.errors import MalformedOutput, TransientError
from loop_apidoc.notebooklm.runner import CommandResult


def _config() -> AgentConfig:
    return AgentConfig(executable="claude", sources_dir=Path("/repo/sources"))


def _runner(result: CommandResult):
    def run(argv: list[str]) -> CommandResult:
        return CommandResult(argv=argv, returncode=result.returncode,
                             stdout=result.stdout, stderr=result.stderr)
    return run


def _envelope(result: str, *, is_error: bool = False) -> str:
    return json.dumps({"type": "result", "subtype": "success",
                       "is_error": is_error, "result": result})


def test_build_argv_is_read_only_and_grounded():
    argv = build_ask_argv(_config(), "List endpoints.")
    assert argv[0] == "claude" and argv[1] == "-p"
    assert "List endpoints." in argv[2]
    assert "/repo/sources" in argv[2]
    assert "--output-format" in argv and "json" in argv
    assert GROUNDING_SYSTEM_PROMPT in argv
    # read-only: file tools allowed, no Bash/Edit/Write/Web
    i = argv.index("--allowedTools")
    allowed = argv[i + 1:i + 4]
    assert "Read" in allowed
    assert not ({"Bash", "Edit", "Write", "WebSearch", "WebFetch"} & set(argv))


def test_build_argv_adds_model_when_set():
    cfg = AgentConfig(executable="claude", sources_dir=Path("/s"), model="opus")
    argv = build_ask_argv(cfg, "q")
    assert "--model" in argv and "opus" in argv


def test_parse_result_extracts_answer():
    assert parse_agent_result(_envelope("GET /users")) == "GET /users"


def test_parse_result_raises_on_non_json():
    with pytest.raises(MalformedOutput):
        parse_agent_result("not json at all")


def test_parse_result_raises_transient_on_error_envelope():
    with pytest.raises(TransientError):
        parse_agent_result(_envelope("", is_error=True))


def test_parse_result_raises_on_missing_result():
    with pytest.raises(MalformedOutput):
        parse_agent_result(json.dumps({"type": "result", "is_error": False}))


def test_adapter_returns_parsed_answer():
    adapter = ClaudeCodeAdapter(_config(), _runner(
        CommandResult(argv=[], returncode=0,
                      stdout=_envelope("POST /mpg_gateway"), stderr="")))
    result = adapter.ask("q", "")
    assert result.answer == "POST /mpg_gateway"


def test_adapter_raises_transient_on_nonzero_exit():
    adapter = ClaudeCodeAdapter(_config(), _runner(
        CommandResult(argv=[], returncode=1, stdout="", stderr="boom")))
    with pytest.raises(TransientError):
        adapter.ask("q", "")


def test_adapter_flags_refusal_answer():
    adapter = ClaudeCodeAdapter(_config(), _runner(
        CommandResult(argv=[], returncode=0,
                      stdout=_envelope("我目前無法回覆。"), stderr="")))
    with pytest.raises(TransientError):
        adapter.ask("q", "")
