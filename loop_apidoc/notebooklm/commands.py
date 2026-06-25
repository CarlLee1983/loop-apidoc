from __future__ import annotations

from loop_apidoc.notebooklm.config import SkillConfig


def build_auth_status_argv(config: SkillConfig) -> list[str]:
    return [config.python, str(config.run_py), "auth_manager.py", "status"]


def build_ask_argv(config: SkillConfig, question: str, notebook_url: str) -> list[str]:
    return [
        config.python,
        str(config.run_py),
        "ask_question.py",
        "--question",
        question,
        "--notebook-url",
        notebook_url,
    ]
