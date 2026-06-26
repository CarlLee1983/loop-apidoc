from __future__ import annotations

import os
from pathlib import Path

import pytest

from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.runner import subprocess_runner

pytestmark = pytest.mark.smoke

_ENABLED = os.environ.get("LOOP_APIDOC_SMOKE") == "1"
_NOTEBOOK = os.environ.get("LOOP_APIDOC_SMOKE_NOTEBOOK", "")
_SKILL_ROOT = os.environ.get("LOOP_APIDOC_SKILL_ROOT", "notebooklm-skill")


@pytest.mark.skipif(not _ENABLED, reason="set LOOP_APIDOC_SMOKE=1 to run real-skill smoke")
def test_real_ask_returns_answer() -> None:
    assert _NOTEBOOK, "set LOOP_APIDOC_SMOKE_NOTEBOOK to a test notebook url"
    config = SkillConfig(skill_root=Path(_SKILL_ROOT))
    adapter = NotebookLMAdapter(config, subprocess_runner(config))
    status = adapter.auth_status()
    assert status.authenticated, "skill must be authenticated for smoke test"
    result = adapter.ask("What endpoints exist?", _NOTEBOOK)
    assert result.answer.strip(), "expected a non-empty answer body"
    # Documented framing: the raw stdout wraps the question + a 60-char rule.
    assert "Question:" in result.raw_stdout
    assert "=" * 60 in result.raw_stdout
