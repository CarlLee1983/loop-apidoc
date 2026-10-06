from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from loop_apidoc.score.models import ScoreProfile
from loop_apidoc.validate import validate_run_dir, write_reports


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
    # 這個入口只讀 run 目錄,來源與 focus 應答都不在裡面,所以三項檢查在此無法
    # 重建 —— 而它剛剛用一份沒有那些問題的報告覆寫了 assemble 寫出的那份。
    # 擋不了覆寫(那正是這個命令的用途),就必須講出來,否則 SOURCE_FACTS_UNSCANNED
    # 會被一次 re-validate 靜靜抹掉,而那正是這筆警告存在的理由。
    typer.echo(
        "注意:此報告不含需要來源或 focus 應答才能判定的檢查"
        "(SOURCE_FACTS_UNSCANNED、FOCUS_UNMET、FOCUS_INCOMPLETE);"
        "它們只在 assemble 產生,重跑此命令會把它們從報告中移除。"
        "要保留完整結論,請以 assemble 的報告為準。",
        err=True,
    )
    raise typer.Exit(code=0 if report.ok else 1)


def diff(
    base: Path = typer.Option(
        ...,
        "--base",
        help="舊版/基準 run 目錄",
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    head: Path = typer.Option(
        ...,
        "--head",
        help="新版/待比較 run 目錄",
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="diff report 輸出目錄；省略時寫入 <head>/diff",
    ),
) -> None:
    """比較兩個已完成 run 目錄並輸出版本差異報告。"""
    from loop_apidoc.diff import (
        DiffInputError,
        build_diff_report,
        load_run_artifacts,
        write_reports,
    )

    output_dir = output or (head / "diff")
    if output_dir.exists() and output_dir.is_file():
        typer.echo(f"diff input error: output path is a file: {output_dir}", err=True)
        raise typer.Exit(code=2)

    try:
        base_artifacts = load_run_artifacts(base)
        head_artifacts = load_run_artifacts(head)
        report = build_diff_report(base_artifacts, head_artifacts)
    except DiffInputError as exc:
        typer.echo(f"diff input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    write_reports(report, output_dir)
    typer.echo(
        "diff COMPLETE: "
        f"breaking {report.summary.get('breaking', 0)}，"
        f"additive {report.summary.get('additive', 0)}，"
        f"changed {report.summary.get('changed', 0)}，"
        f"source_only {report.summary.get('source_only', 0)}；"
        f"報告寫入 {output_dir / 'report.json'}"
    )


def score(
    output: Path = typer.Option(
        ...,
        "--output",
        help="已完成的 run 目錄（含 openapi.yaml / provenance.json / validation/report.json）",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    profile: ScoreProfile = typer.Option(
        ScoreProfile.CI,
        "--profile",
        case_sensitive=False,
        help="評分嚴格度：ci 較嚴格，review 較適合人工健檢",
    ),
    min_score: Annotated[
        int | None,
        typer.Option("--min-score", min=0, max=100, help="覆寫 profile 預設分數門檻"),
    ] = None,
    json_out: bool = typer.Option(
        False,
        "--json",
        help="把 score report JSON 印到 stdout",
    ),
) -> None:
    """評分既有 run 目錄並寫出 score/score.{json,md}。"""
    from loop_apidoc.score import (
        ScoreInputError,
        evaluate_score,
        load_score_inputs,
        write_reports as write_score_reports,
    )

    score_dir = output / "score"
    try:
        inputs = load_score_inputs(output)
        report = evaluate_score(inputs, profile=profile, min_score=min_score)
    except ScoreInputError as exc:
        typer.echo(f"score input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    write_score_reports(report, score_dir)
    if json_out:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(
            f"score {report.status.value.upper()}: {report.score}/100 "
            f"(profile {report.profile.value}, min {report.min_score})；"
            f"報告寫入 {score_dir / 'score.json'}"
        )
    raise typer.Exit(code=0 if report.status.value == "pass" else 1)


def evaluate(
    baseline: Path = typer.Option(
        ...,
        "--baseline",
        help="基準 runtime 的已保存 ReplayReport JSON",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    candidate: Path = typer.Option(
        ...,
        "--candidate",
        help="候選 runtime 的已保存 ReplayReport JSON",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        help="evaluation-report.{json,md} 輸出目錄",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="把 comparison report JSON 印到 stdout",
    ),
) -> None:
    """比較兩份同一案例版本的 runtime replay 結果；不變更 production contract。"""
    from loop_apidoc.evaluation.models import EvaluationInputError
    from loop_apidoc.evaluation import (
        build_comparison_report,
        load_replay_report,
        write_reports as write_evaluation_reports,
    )

    if output.exists() and output.is_file():
        typer.echo(f"evaluate input error: output path is a file: {output}", err=True)
        raise typer.Exit(code=2)
    try:
        baseline_report = load_replay_report(baseline, label="baseline")
        candidate_report = load_replay_report(candidate, label="candidate")
        report = build_comparison_report(baseline_report, candidate_report)
    except EvaluationInputError as exc:
        typer.echo(f"evaluate input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    write_evaluation_reports(report, output)
    if json_out:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(
            "evaluate COMPLETE: "
            f"case {report.case.id}@{report.case.version}；"
            f"報告寫入 {output / 'evaluation-report.json'}"
        )


def review(
    project: Path = typer.Option(
        Path("."), "--project", help="Foundry 專案根目錄", exists=True, file_okay=False
    ),
    docset: str = typer.Option(..., "--docset", help="要審核的 Foundry docset"),
    run: Path = typer.Option(
        ...,
        "--run",
        help="剛完成、要自動匯入的 run 目錄",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    port: Annotated[
        int,
        typer.Option("--port", min=0, max=65535, help="本機 GUI port；0 表示自動選擇"),
    ] = 0,
    no_open: bool = typer.Option(
        False, "--no-open", help="只印出 URL，不嘗試開啟瀏覽器"
    ),
) -> None:
    """自動匯入候選、比較 current，並啟動本機人工審核 GUI。"""
    import webbrowser

    from loop_apidoc.review import (
        ReviewConflictError,
        ReviewInputError,
        ReviewRequest,
        ReviewWorkflow,
    )
    from loop_apidoc.review.web import ReviewWebAdapter

    workflow = ReviewWorkflow(project)
    try:
        snapshot = workflow.open_review(ReviewRequest(docset_id=docset, run_dir=run))
        adapter = ReviewWebAdapter(workflow, snapshot, port=port)
    except (ReviewConflictError, ReviewInputError, OSError) as exc:
        typer.echo(f"review input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"review GUI: {adapter.url}")
    if not no_open:
        try:
            webbrowser.open(adapter.url)
        except OSError:
            typer.echo(
                "review browser launch failed; open the printed URL manually", err=True
            )
    try:
        adapter.serve_forever()
    except KeyboardInterrupt:
        typer.echo("review GUI stopped")
    finally:
        adapter.shutdown()
