from __future__ import annotations

from pathlib import Path

from loop_apidoc.doctor.checks import (
    check_auth,
    check_python,
    check_skill_present,
    check_validation_tools,
    run_checks,
)
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.runner import CommandResult


def _skill(tmp_path: Path, *, with_run_py: bool = False, with_venv: bool = False) -> SkillConfig:
    if with_run_py:
        (tmp_path / "scripts").mkdir(exist_ok=True)
        (tmp_path / "scripts" / "run.py").write_text("", encoding="utf-8")
    if with_venv:
        (tmp_path / ".venv").mkdir(exist_ok=True)
    return SkillConfig(skill_root=tmp_path)


def test_check_python_passes_on_current_runtime():
    result = check_python()
    assert result.ok is True
    assert result.required is True


def test_check_validation_tools_present():
    # openapi-spec-validator / jsonschema / pyyaml are project dependencies.
    result = check_validation_tools()
    assert result.ok is True


def test_check_skill_present_false_when_missing(tmp_path: Path):
    result = check_skill_present(_skill(tmp_path))
    assert result.ok is False
    assert result.remedy is not None


def test_check_auth_skipped_without_venv(tmp_path: Path):
    # No real subprocess must run when the skill .venv is absent.
    result = check_auth(_skill(tmp_path, with_run_py=True), runner=None)
    assert result.ok is False
    assert result.required is False
    assert "略過" in result.detail


def test_check_auth_uses_injected_runner_when_ready(tmp_path: Path):
    config = _skill(tmp_path, with_run_py=True, with_venv=True)

    def fake_runner(argv: list[str]) -> CommandResult:
        return CommandResult(argv=argv, returncode=0, stdout="  Authenticated: Yes\n", stderr="")

    result = check_auth(config, runner=fake_runner)
    assert result.ok is True


def test_run_checks_returns_all_six(tmp_path: Path):
    def fake_runner(argv: list[str]) -> CommandResult:
        return CommandResult(argv=argv, returncode=0, stdout="  Authenticated: No\n", stderr="")

    results = run_checks(_skill(tmp_path, with_run_py=True, with_venv=True), runner=fake_runner)
    names = [r.name for r in results]
    assert names == ["python", "notebooklm-skill", "skill-requirements", "chrome", "validation-tools", "auth"]
