from __future__ import annotations

from pathlib import Path

import typer


def governance_scan_command(
    watchlist: Path = typer.Option(
        ...,
        "--watchlist",
        exists=True,
        readable=True,
        help="巡檢清單 freshness-watchlist.json",
    ),
    json_output: bool = typer.Option(False, "--json", help="輸出機器可讀 JSON"),
    report_dir: Path | None = typer.Option(
        None, "--report-dir", help="另存 governance-trigger.{json,md}"
    ),
    snapshot_dir: Path | None = typer.Option(
        None, "--snapshot-dir", help="保留 changed 來源的不可覆寫證據快照"
    ),
) -> None:
    """建立需人工審核的來源變動觸發；不會生成、匯入或核准契約。"""
    from loop_apidoc.freshness.batch import load_watchlist, scan_watchlist
    from loop_apidoc.freshness.models import (
        EXIT_CODES,
        FreshnessInputError,
        FreshnessVerdict,
    )
    from loop_apidoc.governance.models import GovernanceStatus
    from loop_apidoc.governance.report import render_markdown, write_reports
    from loop_apidoc.governance.scan import build_governance_report
    from loop_apidoc.governance.snapshot import GovernanceSnapshotError, write_snapshot

    try:
        loaded = load_watchlist(watchlist)
    except FreshnessInputError as exc:
        typer.echo(f"governance-scan error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    scan = scan_watchlist(loaded, base_dir=watchlist.parent)
    report = build_governance_report(scan)
    if snapshot_dir is not None:
        try:
            report = report.model_copy(
                update={"snapshot": write_snapshot(scan, snapshot_dir)}
            )
        except GovernanceSnapshotError as exc:
            typer.echo(f"governance-scan error: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    if report_dir is not None:
        write_reports(report, report_dir)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_markdown(report))
    exit_code = {
        GovernanceStatus.NO_ACTION: EXIT_CODES[FreshnessVerdict.UNCHANGED],
        GovernanceStatus.REVIEW_REQUIRED: EXIT_CODES[FreshnessVerdict.CHANGED],
        GovernanceStatus.ATTENTION_REQUIRED: EXIT_CODES[FreshnessVerdict.INCONCLUSIVE],
    }[report.status]
    raise typer.Exit(code=exit_code)


def governance_review_plan_command(
    trigger: Path = typer.Option(
        ..., "--trigger", exists=True, readable=True, help="governance-trigger.json"
    ),
    snapshot: Path | None = typer.Option(
        None, "--snapshot", help="immutable governance snapshot 目錄"
    ),
    output: Path = typer.Option(
        ..., "--output", help="governance-review-plan.{json,md} 輸出目錄"
    ),
    json_output: bool = typer.Option(False, "--json", help="輸出機器可讀 JSON"),
) -> None:
    """把治理觸發轉成 bounded review handoff；不會重新擷取、生成或核准。"""
    from loop_apidoc.governance.review_plan import (
        GovernanceReviewPlanError,
        build_review_plan,
        load_review_plan_inputs,
        write_review_plan,
    )

    if output.exists() and output.is_file():
        typer.echo(
            f"governance-review-plan error: output path is a file: {output}", err=True
        )
        raise typer.Exit(code=2)
    try:
        report, snapshot_data = load_review_plan_inputs(trigger, snapshot)
        plan = build_review_plan(report, snapshot_data)
    except GovernanceReviewPlanError as exc:
        typer.echo(f"governance-review-plan error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    write_review_plan(plan, output)
    if json_output:
        typer.echo(plan.model_dump_json(indent=2))
    else:
        typer.echo(
            f"governance-review-plan COMPLETE: {len(plan.items)} item(s)；報告寫入 {output}"
        )
