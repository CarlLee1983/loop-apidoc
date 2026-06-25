from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel


class SkillConfig(BaseModel):
    """Locates the notebooklm-skill checkout and the interpreter used to launch
    its scripts/run.py wrapper (spec §4.1: all scripts run via run.py)."""

    skill_root: Path
    python: str = sys.executable

    @property
    def run_py(self) -> Path:
        return self.skill_root / "scripts" / "run.py"

    def is_present(self) -> bool:
        return self.run_py.is_file()

    def venv_initialized(self) -> bool:
        return (self.skill_root / ".venv").is_dir()
