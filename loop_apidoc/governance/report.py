from __future__ import annotations

from pathlib import Path

from loop_apidoc.governance.models import GovernanceReport


def render_markdown(report: GovernanceReport) -> str:
    lines = [
        "# 來源與契約治理觸發",
        "",
        f"- 狀態:**{report.status.value}**",
        f"- 已巡檢項目:{report.scanned_count}",
    ]
    if report.triggers:
        lines += [
            "",
            "| 項目 | 觸發原因 | 摘要/原因 | Run 目錄 |",
            "| --- | --- | --- | --- |",
            *[
                f"| {trigger.label} | {trigger.kind.value} | {trigger.reason or '-'} | `{trigger.run_dir or '-'}` |"
                for trigger in report.triggers
            ],
        ]
    return "\n".join(lines) + "\n"


def write_reports(report: GovernanceReport, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "governance-trigger.json"
    markdown_path = report_dir / "governance-trigger.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path
