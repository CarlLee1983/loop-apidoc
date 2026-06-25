from __future__ import annotations

import subprocess
from typing import Protocol

from pydantic import BaseModel

from loop_apidoc.notebooklm.config import SkillConfig


class CommandResult(BaseModel):
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    def __call__(self, argv: list[str]) -> CommandResult: ...


def subprocess_runner(
    config: SkillConfig, timeout_seconds: float = 300.0
) -> ProcessRunner:
    """Real runner: executes argv via subprocess, capturing only the invoked
    script's stdout/stderr — never the skill's browser state or data/ (§11)."""

    def run(argv: list[str]) -> CommandResult:
        try:
            completed = subprocess.run(
                argv,
                cwd=config.skill_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                argv=argv,
                returncode=124,
                stdout=exc.stdout or "",
                stderr="Timeout waiting for answer",
            )
        return CommandResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    return run
