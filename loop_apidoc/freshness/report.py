from __future__ import annotations

from pathlib import Path

from loop_apidoc.freshness.models import FreshnessReport, SourceResult


def _rows(results: list[SourceResult]) -> list[str]:
    return [f"| `{r.id}` | {r.kind.value} | {r.status.value} | {r.reason or '-'} |" for r in results]


def render_markdown(report: FreshnessReport) -> str:
    lines = [
        "# 來源新鮮度檢查",
        "",
        f"- 判定:**{report.verdict.value}**",
        f"- OpenAPI 版本:`{report.openapi_version or '-'}`",
        f"- 來源總數:{report.sources_total};未變:{report.unchanged_count};"
        f"變動:{len(report.changed)};無法判定:{len(report.inconclusive)}",
    ]
    flagged = report.changed + report.inconclusive
    if flagged:
        lines += ["", "| 來源 | 類型 | 狀態 | 原因 |", "| --- | --- | --- | --- |", *_rows(flagged)]
    return "\n".join(lines) + "\n"


def write_reports(report: FreshnessReport, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "freshness-report.json"
    md_path = report_dir / "freshness-report.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return (json_path, md_path)
