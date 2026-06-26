from __future__ import annotations

import subprocess

from loop_apidoc.agentcli.config import AgentConfig
from loop_apidoc.notebooklm.runner import CommandResult, ProcessRunner


def subprocess_runner(config: AgentConfig) -> ProcessRunner:
    """Real runner: executes the agent CLI argv, capturing only its stdout/stderr.

    Runs from the sources directory's parent so relative source paths resolve and
    the agent's read-only tools can reach the local documents.
    """
    cwd = config.sources_dir.parent if config.sources_dir.parent.exists() else None

    def run(argv: list[str]) -> CommandResult:
        try:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr or ""
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            return CommandResult(
                argv=argv, returncode=124,
                stdout=exc.stdout or "",
                stderr=f"Timeout waiting for answer: {stderr}",
            )
        return CommandResult(
            argv=argv, returncode=completed.returncode,
            stdout=completed.stdout, stderr=completed.stderr,
        )

    return run
