from __future__ import annotations

import sys
from pathlib import Path

from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.runner import CommandResult, subprocess_runner


def test_skill_config_paths(tmp_path: Path):
    config = SkillConfig(skill_root=tmp_path)
    assert config.run_py == tmp_path / "scripts" / "run.py"
    assert config.is_present() is False
    assert config.venv_initialized() is False

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text("", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    assert config.is_present() is True
    assert config.venv_initialized() is True


def test_subprocess_runner_captures_streams_and_code(tmp_path: Path):
    config = SkillConfig(skill_root=tmp_path)
    run = subprocess_runner(config)
    argv = [sys.executable, "-c", "import sys; print('hi'); sys.stderr.write('e'); sys.exit(3)"]

    result = run(argv)

    assert isinstance(result, CommandResult)
    assert result.returncode == 3
    assert result.stdout.strip() == "hi"
    assert result.stderr == "e"
    assert result.argv == argv


def test_subprocess_runner_timeout_is_marked_transient(tmp_path: Path):
    config = SkillConfig(skill_root=tmp_path)
    run = subprocess_runner(config, timeout_seconds=0.5)
    argv = [sys.executable, "-c", "import time; time.sleep(5)"]

    result = run(argv)

    assert result.returncode == 124
    assert "Timeout waiting for answer" in result.stderr
