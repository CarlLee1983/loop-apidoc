from __future__ import annotations

from pathlib import Path

from loop_apidoc.diff.models import DiffReport


def render_markdown(report: DiffReport) -> str:
    return f"# Version Diff Report\n\nBase: {report.base_run}\nHead: {report.head_run}\n"


def write_reports(report: DiffReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
