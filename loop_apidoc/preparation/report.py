from __future__ import annotations

from pathlib import Path

from loop_apidoc.preparation.models import PreparationReport


def render_markdown(report: PreparationReport) -> str:
    lines = [
        "# Preparation Readiness Report",
        "",
        f"Overall status: `{report.status.value}`",
        "",
        "## Summary",
        "",
        "| Phase status | Count |",
        "| --- | ---: |",
    ]
    for key in ("blocked", "needs_attention", "ready"):
        lines.append(f"| {key} | {report.summary.get(key, 0)} |")

    for phase in report.phases:
        lines.extend(["", f"## {phase.label}", ""])
        lines.append(f"Status: `{phase.status.value}`")
        if phase.metrics:
            lines.extend(["", "| Metric | Value |", "| --- | ---: |"])
            for key in sorted(phase.metrics):
                lines.append(f"| {key} | {phase.metrics[key]} |")
        if not phase.findings:
            lines.extend(["", "No findings."])
            continue
        lines.extend(
            [
                "",
                "| Severity | Finding | Target | Suggested action |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding in phase.findings:
            target = finding.target_file or "-"
            if finding.field_path:
                target = f"{target}{finding.field_path}"
            lines.append(
                f"| {finding.severity.value} | {finding.summary} | "
                f"`{target}` | {finding.suggested_action} |"
            )
    return "\n".join(lines) + "\n"


def write_reports(report: PreparationReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "preparation-report.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (output_dir / "preparation-report.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )
