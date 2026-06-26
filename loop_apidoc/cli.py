from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer

from loop_apidoc.doctor.checks import run_checks
from loop_apidoc.doctor.report import build_report, render_report
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.validate import validate_run_dir, write_reports

app = typer.Typer(
    help="Loop 來源依據式 API 文件 pipeline",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """Loop 來源依據式 API 文件 pipeline。"""


@app.command()
def manifest(
    sources: Path = typer.Option(
        ...,
        "--sources",
        help="本機來源目錄",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    url: list[str] = typer.Option(
        [],
        "--url",
        help="公開來源 URL，可重複指定",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="manifest.json 輸出路徑；省略則輸出至 stdout",
    ),
) -> None:
    """掃描本機來源並建立來源 manifest。"""
    generated_at = datetime.now(timezone.utc)
    result = build_manifest(
        sources_root=sources,
        urls=list(url),
        generated_at=generated_at,
    )
    payload = result.model_dump_json(indent=2)
    if output is None:
        typer.echo(payload)
    else:
        output.write_text(payload, encoding="utf-8")
        typer.echo(f"manifest 已寫入 {output}")


@app.command()
def doctor(
    skill_root: Path = typer.Option(
        Path("notebooklm-skill"),
        "--skill-root",
        envvar="LOOP_APIDOC_SKILL_ROOT",
        help="notebooklm-skill checkout 目錄",
    ),
) -> None:
    """檢查執行環境：Python、NotebookLM skill、依賴、Chrome、驗證狀態與驗證工具。"""
    config = SkillConfig(skill_root=skill_root)
    report = build_report(run_checks(config))
    typer.echo(render_report(report))
    raise typer.Exit(code=0 if report.ok else 1)


@app.command()
def validate(
    output: Path = typer.Option(
        ...,
        "--output",
        help="輸出 run 目錄（含 openapi.yaml / provenance.json / plan 等）",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
) -> None:
    """驗證 run 目錄的輸出（結構／完整性／一致性／禁止推測）。"""
    report = validate_run_dir(output)
    write_reports(report, output / "validation")
    status = "PASS" if report.ok else "FAIL"
    typer.echo(
        f"驗證 {status}：error {len(report.errors())}，warning {len(report.warnings())}；"
        f"報告寫入 {output / 'validation'}"
    )
    raise typer.Exit(code=0 if report.ok else 1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
