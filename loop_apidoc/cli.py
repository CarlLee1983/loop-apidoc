from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.run.runid import make_run_id
from loop_apidoc.score.models import ScoreProfile
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


@app.command()
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
        f"breaking {report.summary['breaking']}，"
        f"additive {report.summary['additive']}，"
        f"changed {report.summary['changed']}，"
        f"source_only {report.summary['source_only']}；"
        f"報告寫入 {output_dir / 'report.json'}"
    )


@app.command()
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


@app.command()
def assemble(
    sources: Path = typer.Option(
        ..., "--sources", help="本機來源目錄",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    extraction: Path = typer.Option(
        ..., "--extraction",
        help="agent 產出的擷取目錄(inventory.json + endpoints/*.json,選用 integration.json)",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    output: Path = typer.Option(
        ..., "--output", help="輸出根目錄(將建立 <run-id> 子目錄)"
    ),
    url: list[str] = typer.Option([], "--url", help="公開來源 URL,可重複指定"),
    json_out: bool = typer.Option(
        False, "--json", help="把結果以 JSON 印到 stdout(供 agent 解析)"
    ),
    score_report: bool = typer.Option(
        False,
        "--score",
        help="在 assemble 完成後寫出 score/score.{json,md}",
    ),
    target_score: Annotated[
        int | None,
        typer.Option("--target-score", min=0, max=100,
                     help="score 自循環目標分(loop verdict 用);省略取 ci profile 預設 85"),
    ] = None,
    prev_score: Annotated[
        int | None,
        typer.Option("--prev-score", min=0, max=100,
                     help="上一輪 score 總分(agent 跨輪帶入,供高原偵測);首輪省略"),
    ] = None,
    round_index: Annotated[
        int,
        typer.Option("--round-index", min=1,
                     help="目前修正輪次(1 起);loop verdict 用"),
    ] = 1,
    max_rounds: Annotated[
        int,
        typer.Option("--max-rounds", min=1,
                     help="修正輪次上限;達上限且未達標→exhausted"),
    ] = 6,
) -> None:
    """從 agent 產出的擷取 JSON 組裝:manifest→plan→generate→validate(不擷取)。"""
    from loop_apidoc.agentcli.assemble import (
        AssembleInputError,
        RunDirectoryCollisionError,
        run_assemble_pipeline,
    )

    now = datetime.now(timezone.utc)
    try:
        result = run_assemble_pipeline(
            sources_root=sources,
            extraction_dir=extraction,
            output_root=output,
            run_id=make_run_id(now),
            generated_at=now,
            urls=list(url),
        )
    except AssembleInputError as exc:
        typer.echo(f"擷取輸入錯誤:{exc}", err=True)
        raise typer.Exit(code=2) from exc
    except RunDirectoryCollisionError as exc:
        typer.echo(f"run 目錄衝突:{exc}", err=True)
        raise typer.Exit(code=2) from exc

    score_payload = None
    score_error = None
    if score_report:
        from loop_apidoc.score import (
            ScoreInputError,
            evaluate_score,
            load_score_inputs,
            write_reports as write_score_reports,
        )

        try:
            score_inputs = load_score_inputs(Path(result.run_dir))
            score_payload = evaluate_score(score_inputs)
            write_score_reports(score_payload, Path(result.run_dir) / "score")
        except ScoreInputError as exc:
            score_error = str(exc)
            typer.echo(f"score input error: {exc}", err=True)

    loop_payload = None
    if score_payload is not None:
        from loop_apidoc.score import loop_verdict, resolved_min_score

        resolved_target = resolved_min_score(ScoreProfile.CI, target_score)
        loop_payload = loop_verdict(
            prev_score=prev_score,
            curr_score=score_payload.score,
            target=resolved_target,
            round_index=round_index,
            max_rounds=max_rounds,
            findings=score_payload.findings,
        )

    if json_out:
        review_html = str(Path(result.run_dir) / "review.html")
        payload = {
            "run_id": result.run_id,
            "run_dir": result.run_dir,
            "review_html": review_html,
            "ok": result.ok,
            "status": result.status.value,
            "report": result.report.model_dump(mode="json"),
        }
        if score_payload is not None:
            payload["score"] = score_payload.model_dump(mode="json")
        if loop_payload is not None:
            payload["loop"] = loop_payload.model_dump(mode="json")
        if score_error is not None:
            payload["score_error"] = score_error
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        suffix = ""
        if score_payload is not None:
            suffix = (
                f"；score {score_payload.status.value.upper()} "
                f"{score_payload.score}/100"
            )
        elif score_error is not None:
            suffix = f"；score input error: {score_error}"
        typer.echo(
            f"狀態 {result.status.value}:error {len(result.report.errors())}，"
            f"warning {len(result.report.warnings())}；輸出於 {result.run_dir}；"
            f"核對頁 {Path(result.run_dir) / 'review.html'}"
            f"{suffix}"
        )
    raise typer.Exit(code=0 if result.ok else 1)


@app.command()
def preprocess(
    sources: Path = typer.Option(
        ..., "--sources", help="本機來源目錄",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    out: Path = typer.Option(
        ..., "--out", help="markdown 輸出目錄（衍生位置，勿放 sources/ 內）"
    ),
) -> None:
    """把 sources 下每個 PDF 轉成 markdown（pymupdf4llm，保留表格／標題結構），
    非 PDF 文字檔原樣複製。供 agent-native 擷取時 subagent 讀取高保真 markdown。"""
    from loop_apidoc.agentcli.preprocess import prepare_markdown

    result = prepare_markdown(sources, out)
    typer.echo(
        "已前處理 "
        f"converted {len(result.converted)} / "
        f"copied {len(result.copied)} / "
        f"passthrough {len(result.passthrough)} 於 {result.dest_dir}"
    )
    for relative in result.passthrough:
        typer.echo(
            f"passthrough {relative.as_posix()} "
            "(not converted; agent must read source format)"
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
