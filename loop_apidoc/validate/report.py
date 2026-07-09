from __future__ import annotations

from pathlib import Path

from loop_apidoc.validate.models import Issue, ValidationReport


def _bullet(issue: Issue) -> str:
    return (
        f"- **{issue.code.value}** ({issue.severity.value}) @ `{issue.location}`\n"
        f"  - 證據：{issue.evidence}\n"
        f"  - 建議修正：{issue.suggested_fix}\n"
        f"  - 可自動修正：{'是' if issue.auto_fixable else '否'}"
    )


def _root_cause_bullet(cause) -> str:
    return (
        f"- **{cause.code.value}** ({cause.severity.value}) @ `{cause.target_file}`"
        f" — 影響 {len(cause.affected_locations)} 處\n"
        f"  - 一次修完：{cause.fix_once}\n"
        f"  - 影響位置：{'、'.join(f'`{loc}`' for loc in cause.affected_locations)}"
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
    if report.root_causes:
        lines += ["## 根因（優先處理）", ""]
        lines += [_root_cause_bullet(c) for c in report.root_causes]
        lines += ["", "## 逐筆問題", ""]
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
