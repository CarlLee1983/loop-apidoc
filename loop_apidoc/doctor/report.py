from __future__ import annotations

from loop_apidoc.doctor.models import CheckResult, DoctorReport


def build_report(checks: list[CheckResult]) -> DoctorReport:
    return DoctorReport(checks=checks)


def render_report(report: DoctorReport) -> str:
    lines = ["loop-apidoc doctor", ""]
    for check in report.checks:
        if check.ok:
            symbol = "✅"
        elif check.required:
            symbol = "❌"
        else:
            symbol = "⚠️"
        lines.append(f"{symbol} {check.name}: {check.detail}")
        if not check.ok and check.remedy:
            lines.append(f"    → {check.remedy}")
    lines.append("")
    lines.append("整體狀態：通過" if report.ok else "整體狀態：未通過")
    return "\n".join(lines)
