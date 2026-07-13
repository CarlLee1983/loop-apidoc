from __future__ import annotations

from pathlib import Path

from loop_apidoc.source_quality.models import SourceDiffReport, SourceQualityReport


def render_markdown(report: SourceQualityReport) -> str:
    lines = ["# 來源品質報告", "", f"結論：**{report.verdict.value}**", ""]
    for finding in report.findings:
        lines.extend([
            f"## {finding.id}：{finding.category}", "",
            f"- 等級：{finding.severity.value}",
            f"- 證據：{finding.source} {finding.locator} — {finding.evidence}",
            f"- 請補：{finding.required_supplement}",
            f"- 驗收：{finding.acceptance_criteria}",
            "",
        ])
    return "\n".join(lines)


def write_reports(report: SourceQualityReport, diff: SourceDiffReport, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "source-quality-report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (output / "source-quality-report.zh-TW.md").write_text(render_markdown(report), encoding="utf-8")
    (output / "source-diff.json").write_text(diff.model_dump_json(indent=2), encoding="utf-8")
    (output / "source-diff.md").write_text("# 來源差異\n", encoding="utf-8")
