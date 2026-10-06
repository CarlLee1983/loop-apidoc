from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

from loop_apidoc.manifest.formats import (
    detect_format,
    is_supported,
    unsupported_remedy,
)
from loop_apidoc.run.runid import make_run_id
from loop_apidoc.score.models import ScoreProfile
from loop_apidoc.shadow.models import ArchitectureMode


def verify_extraction(
    sources: Path = typer.Option(
        ...,
        "--sources",
        help="本機來源目錄（source 引用要比對 manifest）",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    extraction: Path = typer.Option(
        ...,
        "--extraction",
        help="agent 產出的擷取目錄(inventory.json + endpoints/*.json,選用 integration.json)",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    url: list[str] = typer.Option([], "--url", help="公開來源 URL,可重複指定"),
    exclude: list[str] = typer.Option(
        [],
        "--exclude",
        help="額外排除的 glob(可重複);預設已排除 README/LICENSE/CHANGELOG 等非規格檔",
    ),
    focus: Path | None = typer.Option(
        None,
        "--focus",
        help="擷取重點指令檔(focus.json);agent 的應答讀自 <extraction>/focus-response.json",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    json_out: bool = typer.Option(
        False, "--json", help="把違規以 JSON 陣列印到 stdout(供 agent 解析)"
    ),
) -> None:
    """檢查 agent 產出的擷取 JSON 是否符合契約;不寫檔、不建立 run 目錄。

    exit 0 乾淨;exit 2 有違規或硬 schema 錯誤（不會是 1——1 代表 validate FAIL）。
    """
    from loop_apidoc.agentcli.assemble import AssembleInputError
    from loop_apidoc.agentcli.verify import (
        preview_error_code_shortfall,
        preview_falsified_expectations,
        verify_extraction,
    )
    from loop_apidoc.focus.loader import FocusInputError

    generated_at = datetime.now(timezone.utc)
    try:
        outcome = verify_extraction(
            sources_root=sources,
            extraction_dir=extraction,
            generated_at=generated_at,
            urls=list(url),
            excludes=tuple(exclude),
            focus_file=focus,
        )
        violations = outcome.violations
    except (AssembleInputError, FocusInputError) as exc:
        if json_out:
            typer.echo(json.dumps([str(exc)], ensure_ascii=False, indent=2))
        else:
            typer.echo(f"擷取輸入錯誤:{exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(violations, ensure_ascii=False, indent=2))
    elif violations:
        typer.echo("擷取輸入不符契約(修正後重跑):", err=True)
        for violation in violations:
            typer.echo(f"  - {violation}", err=True)
    else:
        typer.echo("verify-extraction PASS:擷取輸入符合契約")
    if not violations and not json_out:
        # 語意完整性閘門對哪些來源不會有作用 —— 與 assemble 的
        # SOURCE_FACTS_UNSCANNED 共用同一份投影,只是提早到付出 plan→generate
        # 的成本之前。不進 --json、不動 exit code:能擋就等於把被否決的
        # 「零事實直接 FAIL」強度裝回去。
        unscanned = outcome.unscanned
        if unscanned:
            typer.echo(
                f"預告:{len(unscanned)} 份來源不會被語意完整性閘門判過"
                f"({'; '.join(unscanned)});assemble 會以 SOURCE_FACTS_UNSCANNED "
                "警告提出,不阻擋 run。掃出 0 筆的來源先看它是被壓平成單行"
                "(改走 normalize-html-snapshot / preprocess,重讀無用)、還是結構完好"
                "但 method 與 path 沒寫在同一行(掃描器認不得,請回報);"
                "事實對不上的來源請檢查 extraction 是否漏掉它記載的端點。",
                err=True,
            )
    if not violations and focus is not None:
        # 純預告:讓人在跑完整 assemble 之前就知道要不要先回頭補來源。
        # 刻意不進 --json 輸出、不動 exit code —— 那個陣列的意義是「該擋的違規」,
        # 而落空的斷言該留下 run 目錄與產物,是 validate 的結局。
        falsified = preview_falsified_expectations(
            extraction_dir=extraction, focus_file=focus
        )
        if falsified and not json_out:
            typer.echo(
                f"預告:{len(falsified)} 條 expectation directive 落空"
                f"({'、'.join(falsified)});assemble 會以 FOCUS_UNMET 判定驗證失敗,"
                "但仍會產出 run 目錄供你判斷是來源真的沒有、還是查得不夠。",
                err=True,
            )
        # 呼叫本身也擋在 json_out 外面,不只擋 echo:預告在 `--json` 下是純浪費,
        # 而它跑在 PASS 印出之後,任何例外都會把一次通過的 verify 變成 traceback。
        shortfall = (
            []
            if json_out
            else preview_error_code_shortfall(
                sources_root=sources,
                extraction_dir=extraction,
                generated_at=generated_at,
                focus_file=focus,
                excludes=tuple(exclude),
            )
        )
        if shortfall:
            typer.echo(
                f"預告:{len(shortfall)} 條窮盡型 directive 報得比來源記載的錯誤碼少"
                f"({'; '.join(shortfall)});assemble 會以 FOCUS_INCOMPLETE 提出,"
                "severity 由 directive 的 kind 決定。回到來源把漏掉的碼補進擷取。",
                err=True,
            )
    raise typer.Exit(code=2 if violations else 0)


def assemble(
    sources: Path = typer.Option(
        ...,
        "--sources",
        help="本機來源目錄",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    extraction: Path = typer.Option(
        ...,
        "--extraction",
        help="agent 產出的擷取目錄(inventory.json + endpoints/*.json,選用 integration.json)",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    output: Path = typer.Option(
        ..., "--output", help="輸出根目錄(將建立 <run-id> 子目錄)"
    ),
    url: list[str] = typer.Option([], "--url", help="公開來源 URL,可重複指定"),
    exclude: list[str] = typer.Option(
        [],
        "--exclude",
        help="額外排除的 glob(可重複);預設已排除 README/LICENSE/CHANGELOG 等非規格檔",
    ),
    url_coverage: Path = typer.Option(
        None,
        "--url-coverage",
        help="agent 產出的 url_sources/coverage.json 路徑;有 URL 來源時檢核撈取涵蓋率",
    ),
    source_quality: Path = typer.Option(
        ...,
        "--source-quality",
        help="必填: assess-sources 產出的 pass 報告目錄;會重驗並存入 run-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    extractor_model: str = typer.Option(
        None,
        "--extractor-model",
        help="執行擷取的模型名稱,由 agent 明確帶入並記入 run.json;省略即 null(CLI 不推測)",
    ),
    focus: Path | None = typer.Option(
        None,
        "--focus",
        help="擷取重點指令檔(focus.json);agent 的應答讀自 <extraction>/focus-response.json",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    architecture_mode: ArchitectureMode = typer.Option(
        ArchitectureMode.LEGACY,
        "--architecture-mode",
        case_sensitive=False,
        help="架構執行模式:legacy、非阻斷的 shadow，或阻斷式 strict Core candidate",
    ),
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
        typer.Option(
            "--target-score",
            min=0,
            max=100,
            help="score 自循環目標分(loop verdict 用);省略取 ci profile 預設 85",
        ),
    ] = None,
    prev_score: Annotated[
        int | None,
        typer.Option(
            "--prev-score",
            min=0,
            max=100,
            help="上一輪 score 總分(agent 跨輪帶入,供高原偵測);首輪省略",
        ),
    ] = None,
    round_index: Annotated[
        int,
        typer.Option("--round-index", min=1, help="目前修正輪次(1 起);loop verdict 用"),
    ] = 1,
    max_rounds: Annotated[
        int,
        typer.Option(
            "--max-rounds", min=1, help="修正輪次上限;達上限且未達標→exhausted"
        ),
    ] = 6,
) -> None:
    """從 agent 產出的擷取 JSON 組裝:manifest→plan→generate→validate(不擷取)。"""
    from loop_apidoc.agentcli.assemble import (
        AssembleInputError,
        RunDirectoryCollisionError,
        run_assemble_pipeline,
    )
    from loop_apidoc.focus.loader import FocusInputError

    now = datetime.now(timezone.utc)
    try:
        result = run_assemble_pipeline(
            sources_root=sources,
            extraction_dir=extraction,
            output_root=output,
            run_id=make_run_id(now),
            generated_at=now,
            urls=list(url),
            url_coverage_path=url_coverage,
            source_quality_dir=source_quality,
            excludes=tuple(exclude),
            extractor_model=extractor_model,
            architecture_mode=architecture_mode,
            focus_file=focus,
        )
    except (AssembleInputError, FocusInputError) as exc:
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

    if result.shadow is not None and result.shadow.status == "error":
        typer.echo(
            f"shadow error:{result.shadow.message or 'shadow execution failed'}",
            err=True,
        )
    if result.strict is not None and result.strict.status == "error":
        typer.echo(
            f"strict Core error:{result.strict.message or 'candidate execution failed'}",
            err=True,
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
        if result.toolchain is not None:
            payload["toolchain"] = result.toolchain.model_dump(mode="json")
        if score_payload is not None:
            payload["score"] = score_payload.model_dump(mode="json")
        if loop_payload is not None:
            payload["loop"] = loop_payload.model_dump(mode="json")
        if score_error is not None:
            payload["score_error"] = score_error
        if result.shadow is not None:
            payload["shadow"] = result.shadow.model_dump(mode="json")
        if result.strict is not None:
            payload["strict"] = result.strict.model_dump(mode="json")
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
        if result.shadow is not None:
            suffix += f"；shadow {result.shadow.status}"
        if result.strict is not None:
            suffix += f"；strict {result.strict.status}"
        typer.echo(
            f"狀態 {result.status.value}:error {len(result.report.errors())}，"
            f"warning {len(result.report.warnings())}；輸出於 {result.run_dir}；"
            f"核對頁 {Path(result.run_dir) / 'review.html'}"
            f"{suffix}"
        )
    exit_code = 2 if result.status.value == "blocked" else (0 if result.ok else 1)
    raise typer.Exit(code=exit_code)


def preprocess(
    sources: Path = typer.Option(
        ...,
        "--sources",
        help="本機來源目錄或單一檔案",
        exists=True,
        file_okay=True,
        dir_okay=True,
        readable=True,
    ),
    out: Path = typer.Option(
        ..., "--out", help="markdown 輸出目錄（衍生位置，勿放 sources/ 內）"
    ),
) -> None:
    """把 PDF／DOCX 轉成可掃描 markdown，其餘格式一律原樣複製（byte-for-byte）。"""
    from loop_apidoc.agentcli.preprocess import prepare_markdown

    try:
        result = prepare_markdown(sources, out)
    except (OSError, ValueError) as exc:
        typer.echo(f"preprocess error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        "已前處理 "
        f"converted {len(result.converted)} / "
        f"copied {len(result.copied)} / "
        f"passthrough {len(result.passthrough)} 於 {result.dest_dir}"
    )
    for relative in result.passthrough:
        # `.doc` 是 OLE 複合檔、`.xlsx` 是試算表,「交給 agent 讀原始格式」對兩者
        # 都是做不到的事,而那正是這行訊息原本會讓人以為可行的。認得出格式的,
        # 就用那個格式自己的下一步(ADR 0012);認不出的才回到通則。
        source_format = detect_format(relative)
        if is_supported(source_format):
            typer.echo(
                f"passthrough {relative.as_posix()} "
                "(not converted; agent must read source format)"
            )
        else:
            typer.echo(
                f"passthrough {relative.as_posix()} "
                f"({unsupported_remedy(source_format).en})"
            )
