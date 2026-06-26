from __future__ import annotations

from loop_apidoc.notebooklm.answer_quality import detect_unreliable_answer
from loop_apidoc.notebooklm.classify import classify_failure
from loop_apidoc.notebooklm.commands import build_ask_argv, build_auth_status_argv
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.errors import TransientError
from loop_apidoc.notebooklm.models import AskResult, AuthStatus
from loop_apidoc.notebooklm.parsing import parse_ask_answer, parse_auth_status
from loop_apidoc.notebooklm.runner import ProcessRunner


class NotebookLMAdapter:
    """Stateless wrapper over the notebooklm-skill run.py contract. Each ask()
    is an independent session with no conversational context (spec §4.2)."""

    def __init__(self, config: SkillConfig, runner: ProcessRunner) -> None:
        self._config = config
        self._runner = runner

    def auth_status(self) -> AuthStatus:
        result = self._runner(build_auth_status_argv(self._config))
        if result.returncode != 0:
            raise classify_failure(result)
        return parse_auth_status(result.stdout)

    def ask(self, question: str, notebook_url: str) -> AskResult:
        result = self._runner(build_ask_argv(self._config, question, notebook_url))
        if result.returncode != 0:
            raise classify_failure(result)
        answer = parse_ask_answer(result.stdout)
        reason = detect_unreliable_answer(answer)
        if reason is not None:
            # Skill exited 0 but the answer is a refusal or context-bleed reply;
            # treat as transient so the retry path re-queries (spec §11).
            raise TransientError(reason, stdout=result.stdout, stderr=result.stderr)
        return AskResult(
            question=question,
            notebook_url=notebook_url,
            answer=answer,
            raw_stdout=result.stdout,
            returncode=result.returncode,
        )
