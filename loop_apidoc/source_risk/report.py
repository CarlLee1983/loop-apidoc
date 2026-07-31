from __future__ import annotations

from pathlib import Path

from loop_apidoc.source_risk.models import SourceRiskReport


def render_markdown(report: SourceRiskReport) -> str:
    lines = [
        "# 來源風險報告",
        "",
        f"結論：**{report.verdict.value}**",
        f"格式版本：`{report.schema_version}`",
        f"規則版本：`{report.ruleset_version}`",
        f"每檔掃描上限：`{report.max_bytes}` bytes",
        f"來源綁定：`{report.source_binding_digest}`",
        "",
        "## 風險結果",
        "",
    ]
    if report.findings:
        lines.extend(
            f"- `{finding.rule_id}` {finding.severity.value}："
            f"`{finding.source_ref}` {finding.locator}"
            for finding in report.findings
        )
    else:
        lines.append("- 無")
    lines.extend(["", "## 掃描涵蓋", ""])
    lines.extend(
        f"- `{entry.source_ref}`：{entry.status.value}"
        + (f"（{entry.reason}）" if entry.reason else "")
        for entry in report.coverage
    )
    lines.append("")
    return "\n".join(lines)


def write_reports(report: SourceRiskReport, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "source-risk-report.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (output / "source-risk-report.zh-TW.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )
