from __future__ import annotations

import sys
from pathlib import Path

from loop_apidoc.notebooklm.commands import build_ask_argv, build_auth_status_argv
from loop_apidoc.notebooklm.config import SkillConfig


def test_build_auth_status_argv_uses_run_py_wrapper():
    config = SkillConfig(skill_root=Path("/skill"))
    argv = build_auth_status_argv(config)
    assert argv == [
        sys.executable,
        str(Path("/skill") / "scripts" / "run.py"),
        "auth_manager.py",
        "status",
    ]


def test_build_ask_argv_uses_hyphenated_flags_via_run_py():
    config = SkillConfig(skill_root=Path("/skill"))
    argv = build_ask_argv(config, question="List endpoints", notebook_url="https://nb/x")
    assert argv[:3] == [sys.executable, str(Path("/skill") / "scripts" / "run.py"), "ask_question.py"]
    assert "--question" in argv and argv[argv.index("--question") + 1] == "List endpoints"
    assert "--notebook-url" in argv and argv[argv.index("--notebook-url") + 1] == "https://nb/x"
    # The skill is only ever invoked via run.py — never the script directly.
    assert "ask_question.py" == argv[2]
