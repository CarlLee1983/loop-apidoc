from __future__ import annotations

from loop_apidoc.doctor.models import CheckResult
from loop_apidoc.doctor.report import build_report, render_report


def test_report_ok_ignores_non_required_failures():
    checks = [
        CheckResult(name="python", ok=True, detail="3.12"),
        CheckResult(name="chrome", ok=False, detail="未偵測到 Chrome", remedy="安裝 Chrome", required=False),
    ]
    report = build_report(checks)
    assert report.ok is True


def test_report_not_ok_when_required_fails():
    checks = [
        CheckResult(name="notebooklm-skill", ok=False, detail="不存在", remedy="git clone ...", required=True),
    ]
    assert build_report(checks).ok is False


def test_render_marks_required_failure_and_remedy():
    checks = [
        CheckResult(name="python", ok=True, detail="Python 3.12.11"),
        CheckResult(name="notebooklm-skill", ok=False, detail="不存在", remedy="git clone ...", required=True),
        CheckResult(name="chrome", ok=False, detail="未偵測到 Chrome", required=False),
    ]
    text = render_report(build_report(checks))
    assert "✅ python" in text
    assert "❌ notebooklm-skill" in text
    assert "→ git clone ..." in text
    assert "⚠️ chrome" in text
    assert "整體狀態：未通過" in text
