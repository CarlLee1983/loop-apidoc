from __future__ import annotations

from pathlib import Path

from loop_apidoc.validate.models import Issue, Severity, ValidationReport


def _bullet(issue: Issue) -> str:
    return (
        f"- **{issue.code.value}** ({issue.severity.value}) @ `{issue.location}`\n"
        f"  - 證據：{issue.evidence}\n"
        f"  - 建議修正：{issue.suggested_fix}\n"
        f"  - 可自動修正：{'是' if issue.auto_fixable else '否'}"
    )


def render_markdown(report: ValidationReport) -> str:
    errors = report.errors()
    warnings = report.warnings()
    status = "PASS" if report.ok else "FAIL"
    lines = [
        "# 驗證報告",
        "",
        f"結果：**{status}**（error：{len(errors)}，warning：{len(warnings)}）",
        "",
    ]
    ordered = errors + warnings
    if not ordered:
        lines.append("_未發現問題。_")
    else:
        lines.extend(_bullet(issue) for issue in ordered)
    return "\n".join(lines).rstrip() + "\n"


def write_reports(report: ValidationReport, validation_dir: Path) -> None:
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8")
    (validation_dir / "report.md").write_text(
        render_markdown(report), encoding="utf-8")
