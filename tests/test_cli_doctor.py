from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()


def test_doctor_passes_when_skill_present_and_no_venv(tmp_path: Path):
    # Skill present but no .venv -> auth check is skipped (no real subprocess),
    # required checks (python, skill-present, validation-tools) pass -> exit 0.
    skill = tmp_path / "notebooklm-skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "scripts" / "run.py").write_text("", encoding="utf-8")
    (skill / "requirements.txt").write_text("patchright==1.55.2\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "--skill-root", str(skill)])

    assert result.exit_code == 0, result.stdout
    assert "loop-apidoc doctor" in result.stdout
    assert "整體狀態：通過" in result.stdout
    assert "✅ notebooklm-skill" in result.stdout


def test_doctor_fails_when_skill_missing(tmp_path: Path):
    missing = tmp_path / "absent-skill"

    result = runner.invoke(app, ["doctor", "--skill-root", str(missing)])

    assert result.exit_code == 1
    assert "❌ notebooklm-skill" in result.stdout
    assert "整體狀態：未通過" in result.stdout
