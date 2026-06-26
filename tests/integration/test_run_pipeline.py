# tests/integration/test_run_pipeline.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.runner import CommandResult
from loop_apidoc.run.models import RunStatus
from loop_apidoc.run.pipeline import run_pipeline


def _now() -> datetime:
    return datetime(2026, 6, 26, 10, 43, 0, tzinfo=timezone.utc)


_SEPARATOR = "=" * 60
_FOLLOW_UP = "EXTREMELY IMPORTANT: Is that ALL you need to know?"


def _frame_answer(question: str, answer: str) -> str:
    # Matches loop_apidoc.notebooklm.parsing.parse_ask_answer expectations.
    return (
        f"Question: {question}\n"
        f"{_SEPARATOR}\n"
        f"{answer}\n"
        f"{_FOLLOW_UP}\n"
    )


class _ScriptedRunner:
    """Returns canned stdout per skill invocation, matching the run.py contract."""

    def __init__(self, *, auth_ok: bool, answers: list[str]) -> None:
        self._auth_ok = auth_ok
        self._answers = list(answers)
        self._idx = 0

    def __call__(self, argv: list[str]) -> CommandResult:
        joined = " ".join(argv)
        if "auth_manager.py" in joined:
            line = "Authenticated: Yes" if self._auth_ok else "Authenticated: No"
            return CommandResult(argv=argv, returncode=0, stdout=line, stderr="")
        # ask_question.py — emit the documented Question/separator/follow-up framing.
        answer = self._answers[min(self._idx, len(self._answers) - 1)]
        self._idx += 1
        return CommandResult(
            argv=argv, returncode=0, stdout=_frame_answer("q", answer), stderr=""
        )


def _adapter(runner) -> NotebookLMAdapter:
    return NotebookLMAdapter(SkillConfig(skill_root=Path("notebooklm-skill")), runner)


def test_pipeline_blocks_when_not_authenticated(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "api.md").write_text("# API", encoding="utf-8")
    runner = _ScriptedRunner(auth_ok=False, answers=[])
    result = run_pipeline(
        notebook_url="nb://x",
        sources_root=tmp_path / "src",
        output_root=tmp_path / "out",
        adapter=_adapter(runner),
        run_id="20260626T104300Z",
        generated_at=_now(),
    )
    assert result.status is RunStatus.BLOCKED
    assert not (tmp_path / "out" / "20260626T104300Z" / "openapi.yaml").exists()


def test_pipeline_writes_run_dir_layout(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "api.md").write_text("# API", encoding="utf-8")
    # Minimal answers: enough that extraction completes; content drives a
    # source-missing failure but the run-dir must still be fully materialized.
    runner = _ScriptedRunner(auth_ok=True, answers=["No structured data available."])
    result = run_pipeline(
        notebook_url="nb://x",
        sources_root=tmp_path / "src",
        output_root=tmp_path / "out",
        adapter=_adapter(runner),
        run_id="20260626T104300Z",
        generated_at=_now(),
    )
    run_dir = tmp_path / "out" / "20260626T104300Z"
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "extraction" / "queries.jsonl").exists()
    assert (run_dir / "plan" / "normalization-plan.json").exists()
    assert (run_dir / "openapi.yaml").exists()
    assert (run_dir / "api-guide.zh-TW.md").exists()
    assert (run_dir / "provenance.json").exists()
    assert (run_dir / "validation" / "report.json").exists()
    assert (run_dir / "validation" / "report.md").exists()
    assert result.status in (RunStatus.PASSED, RunStatus.FAILED, RunStatus.EARLY_STOPPED)
    # manifest.json is valid JSON
    json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
