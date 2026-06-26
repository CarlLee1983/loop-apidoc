from __future__ import annotations

import subprocess
from pathlib import Path

import loop_apidoc.notebooklm.runner as runner_mod
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.runner import subprocess_runner


def test_timeout_preserves_stderr(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0] if args else "x", timeout=1, output="partial", stderr="boom"
        )

    monkeypatch.setattr(runner_mod.subprocess, "run", fake_run)
    runner = subprocess_runner(SkillConfig(skill_root=Path("notebooklm-skill")))
    result = runner(["python", "scripts/run.py", "ask_question.py"])
    assert result.returncode != 0
    assert "boom" in result.stderr
