from __future__ import annotations

from pathlib import Path

from loop_apidoc.freshness.models import (
    BatchItemResult,
    BatchReport,
    FreshnessReport,
    SourceResult,
)


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


def _batch_rows(items: list[BatchItemResult]) -> list[str]:
    return [
        f"| {i.label} | {i.status.value} | `{i.openapi_version or '-'}` | {i.reason or '-'} |"
        for i in items
    ]


def render_batch_markdown(report: BatchReport) -> str:
    lines = [
        "# 來源新鮮度批次巡檢",
        "",
        f"- 判定:**{report.verdict.value}**",
        f"- 來源總數:{report.total};變動:{report.changed_count};"
        f"需注意(無法判定/錯誤):{report.attention_count};未變:{report.unchanged_count}",
    ]
    if report.items:
        lines += [
            "",
            "| 項目 | 判定 | OpenAPI 版本 | 摘要/原因 |",
            "| --- | --- | --- | --- |",
            *_batch_rows(report.items),
        ]
    return "\n".join(lines) + "\n"


def write_batch_reports(report: BatchReport, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "freshness-scan.json"
    md_path = report_dir / "freshness-scan.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_batch_markdown(report), encoding="utf-8")
    return (json_path, md_path)
