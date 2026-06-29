from __future__ import annotations

from pathlib import Path

from loop_apidoc.diff.models import DiffImpact, DiffReport

_HEADINGS = {
    DiffImpact.BREAKING: "Breaking",
    DiffImpact.ADDITIVE: "Additive",
    DiffImpact.CHANGED: "Changed",
    DiffImpact.SOURCE_ONLY: "Source Only",
}


def render_markdown(report: DiffReport) -> str:
    lines = [
        "# Version Diff Report",
        "",
        f"Base: `{report.base_run}`",
        f"Head: `{report.head_run}`",
        "",
        "## Summary",
        "",
        "| Impact | Count |",
        "| --- | ---: |",
    ]
    for impact in DiffImpact:
        lines.append(f"| {impact.value} | {report.summary.get(impact.value, 0)} |")
    if not report.findings:
        lines.extend(["", "No differences found."])
        return "\n".join(lines) + "\n"

    for impact in DiffImpact:
        grouped = [finding for finding in report.findings if finding.impact is impact]
        if not grouped:
            continue
        lines.extend(["", f"## {_HEADINGS[impact]}", ""])
        for finding in grouped:
            lines.append(f"- `{finding.location}`: {finding.summary}")
    return "\n".join(lines) + "\n"


def write_reports(report: DiffReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
