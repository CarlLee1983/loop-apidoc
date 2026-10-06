from __future__ import annotations

from pathlib import Path

import typer


def record_fingerprint_command(
    run_dir: Path = typer.Option(
        ..., "--run-dir", exists=True, file_okay=False, help="已完成的 run 目錄"
    ),
    output: Path = typer.Option(..., "--output", help="輸出的 source-fingerprint.json"),
    force: bool = typer.Option(False, "--force", help="覆寫既有 fingerprint"),
) -> None:
    """從 run 目錄擷取各來源便宜訊號,寫成基準 fingerprint 側檔。"""
    from loop_apidoc.freshness.models import FreshnessInputError
    from loop_apidoc.freshness.record import build_fingerprint, write_fingerprint

    try:
        fingerprint = build_fingerprint(run_dir)
        write_fingerprint(fingerprint, output, force=force)
    except FreshnessInputError as exc:
        typer.echo(f"record-fingerprint error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"fingerprint 已寫入 {output};OpenAPI 版本 {fingerprint.openapi_version or '-'};"
        f"來源 {len(fingerprint.sources)} 筆"
    )


def check_freshness_command(
    fingerprint: Path = typer.Option(
        ..., "--fingerprint", exists=True, readable=True, help="基準 fingerprint 側檔"
    ),
    sources: Path | None = typer.Option(
        None, "--sources", help="本地來源根目錄(fingerprint 含本地檔時必填)"
    ),
    json_output: bool = typer.Option(False, "--json", help="輸出機器可讀 JSON"),
    report_dir: Path | None = typer.Option(
        None, "--report-dir", help="另存 freshness-report.{json,md}"
    ),
) -> None:
    """比對來源當下訊號與基準,回報是否需要重新解析(退出碼 0/1/2)。"""
    from loop_apidoc.freshness.check import check_freshness
    from loop_apidoc.freshness.models import (
        EXIT_CODES,
        FreshnessInputError,
        SourceFingerprint,
    )
    from loop_apidoc.freshness.report import render_markdown, write_reports

    try:
        loaded = SourceFingerprint.model_validate_json(
            fingerprint.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        typer.echo(f"check-freshness error: 無法讀取 fingerprint: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        report = check_freshness(loaded, sources_root=sources)
    except (
        FreshnessInputError
    ) as exc:  # defensive; check_freshness normally returns a report
        typer.echo(f"check-freshness error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if report_dir is not None:
        write_reports(report, report_dir)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_markdown(report))
    raise typer.Exit(code=EXIT_CODES[report.verdict])


def check_freshness_batch_command(
    watchlist: Path = typer.Option(
        ...,
        "--watchlist",
        exists=True,
        readable=True,
        help="巡檢清單 freshness-watchlist.json",
    ),
    json_output: bool = typer.Option(False, "--json", help="輸出機器可讀 JSON"),
    report_dir: Path | None = typer.Option(
        None, "--report-dir", help="另存 freshness-scan.{json,md}"
    ),
) -> None:
    """對巡檢清單逐項比對來源新鮮度,彙總成一份報表(退出碼 0/1/2)。"""
    from loop_apidoc.freshness.batch import load_watchlist, scan_watchlist
    from loop_apidoc.freshness.models import EXIT_CODES, FreshnessInputError
    from loop_apidoc.freshness.report import render_batch_markdown, write_batch_reports

    try:
        loaded = load_watchlist(watchlist)
    except FreshnessInputError as exc:
        typer.echo(f"check-freshness-batch error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    report = scan_watchlist(loaded, base_dir=watchlist.parent)

    if report_dir is not None:
        write_batch_reports(report, report_dir)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_batch_markdown(report))
    raise typer.Exit(code=EXIT_CODES[report.verdict])
