from __future__ import annotations

from loop_apidoc.agentcli.commands import build_ask_argv
from loop_apidoc.agentcli.config import AgentConfig
from loop_apidoc.agentcli.parsing import parse_agent_result
from loop_apidoc.agentcli.answer_quality import detect_unreliable_answer
from loop_apidoc.agentcli.errors import SkillError, TransientError
from loop_apidoc.agentcli.models import AskResult
from loop_apidoc.agentcli.runner import ProcessRunner


class ClaudeCodeAdapter:
    """Extraction adapter backed by a headless coding-agent CLI (`claude -p`).
    Each ask() is an independent, stateless invocation that reads the local
    sources directly. `notebook_url` is accepted for interface parity but unused
    (the source is on disk)."""

    def __init__(self, config: AgentConfig, runner: ProcessRunner) -> None:
        self._config = config
        self._runner = runner

    def ask(self, question: str, notebook_url: str = "") -> AskResult:
        result = self._runner(build_ask_argv(self._config, question))
        if result.returncode != 0:
            raise TransientError(
                f"agent CLI exited with code {result.returncode}",
                stdout=result.stdout, stderr=result.stderr,
            )
        answer = parse_agent_result(result.stdout)
        reason = detect_unreliable_answer(answer)
        if reason is not None:
            raise TransientError(reason, stdout=result.stdout, stderr=result.stderr)
        if not answer.strip():
            raise SkillError("agent CLI produced an empty answer", stdout=result.stdout)
        return AskResult(
            question=question,
            notebook_url=notebook_url,
            answer=answer,
            raw_stdout=result.stdout,
            returncode=result.returncode,
        )
