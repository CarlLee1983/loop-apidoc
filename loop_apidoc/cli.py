from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.run.runid import make_run_id
from loop_apidoc.score.models import ScoreProfile
from loop_apidoc.shadow.models import ArchitectureMode
from loop_apidoc.validate import validate_run_dir, write_reports

app = typer.Typer(
    help="Loop 來源依據式 API 文件 pipeline",
    no_args_is_help=True,
)

from loop_apidoc.foundry.cli import foundry_app  # noqa: E402  (must follow `app` definition)

app.add_typer(foundry_app, name="foundry")


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"loop-apidoc {version('loop-apidoc')}")
        raise typer.Exit()


@app.callback()
def _root(
    version_: Annotated[
        bool,
        typer.Option(
            "--version",
            help="顯示版本後結束",
            callback=_print_version,
            is_eager=True,
        ),
    ] = False,
) -> None:
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
    exclude: list[str] = typer.Option(
        [],
        "--exclude",
        help="額外排除的 glob（可重複）；預設已排除 README/LICENSE/CHANGELOG 等非規格檔",
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
        excludes=tuple(exclude),
    )
    payload = result.model_dump_json(indent=2)
    if output is None:
        typer.echo(payload)
    else:
        output.write_text(payload, encoding="utf-8")
        typer.echo(f"manifest 已寫入 {output}")


@app.command(name="catalog-url")
def catalog_url(
    url: str = typer.Option(..., "--url", help="文件入口 URL；只會下載這一頁"),
    output: Path = typer.Option(..., "--output", help="輸出的 navigation catalog JSON"),
    max_bytes: Annotated[
        int,
        typer.Option("--max-bytes", min=1, help="入口 HTML 的最大下載位元組數"),
    ] = 5 * 1024 * 1024,
) -> None:
    """下載入口頁一次，建立側欄索引；絕不自動擷取子頁。"""
    from loop_apidoc.url_catalog import CatalogFetchError, fetch_catalog

    try:
        catalog = fetch_catalog(url, max_bytes=max_bytes)
    except (CatalogFetchError, ValueError) as exc:
        typer.echo(f"catalog-url error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    output.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"catalog 已寫入 {output}；發現 {len(catalog.nodes)} 個導航頁面，未擷取任何子頁")


@app.command(name="select-url")
def select_url(
    catalog: Path = typer.Option(..., "--catalog", exists=True, readable=True),
    output: Path = typer.Option(..., "--output", help="輸出的本次擷取 selection JSON"),
    branch: list[str] = typer.Option([], "--branch", help="導航分支關鍵字；可重複指定"),
    term: list[str] = typer.Option([], "--term", help="標題／breadcrumb／URL 關鍵字；可重複指定"),
    url: list[str] = typer.Option([], "--url", help="明確選取的 URL；可重複指定"),
) -> None:
    """依明確範圍選取 catalog 節點；不下載任何 URL。"""
    from pydantic import ValidationError

    from loop_apidoc.url_catalog import UrlCatalog, select_catalog

    try:
        source = UrlCatalog.model_validate_json(catalog.read_text(encoding="utf-8"))
        selection = select_catalog(source, branches=branch, terms=term, urls=url)
    except (OSError, ValidationError, ValueError) as exc:
        typer.echo(f"select-url error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    output.write_text(selection.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(
        f"selection 已寫入 {output}；選取 {len(selection.selected)} / {len(source.nodes)} 頁，"
        "尚未下載正文"
    )


@app.command(name="cache-url-pages")
def cache_url_pages(
    catalog: Path = typer.Option(..., "--catalog", exists=True, readable=True),
    output: Path = typer.Option(..., "--output", help="本機原始 HTML、正文與 corpus.json 目錄"),
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", min=1, help="本次可快取的最大頁數"),
    ] = 200,
    max_bytes_per_page: Annotated[
        int,
        typer.Option("--max-bytes-per-page", min=1, help="每頁原始 HTML 最大位元組數"),
    ] = 5 * 1024 * 1024,
) -> None:
    """快取 catalog 全部頁面並建立本機正文／連結／實體索引，不呼叫模型。"""
    from pydantic import ValidationError

    from loop_apidoc.url_catalog import UrlCatalog
    from loop_apidoc.url_corpus import cache_catalog_pages

    try:
        source = UrlCatalog.model_validate_json(catalog.read_text(encoding="utf-8"))
        output.mkdir(parents=True, exist_ok=True)
        corpus = cache_catalog_pages(
            source,
            output,
            max_pages=max_pages,
            max_bytes_per_page=max_bytes_per_page,
        )
    except (OSError, ValidationError, ValueError) as exc:
        typer.echo(f"cache-url-pages error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    corpus_path = output / "corpus.json"
    corpus_path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")
    fetched = sum(page.status == "fetched" for page in corpus.pages)
    typer.echo(f"corpus 已寫入 {corpus_path}；快取 {fetched} / {len(corpus.pages)} 頁，未送入模型")


@app.command(name="cache-url-entry")
def cache_url_entry(
    url: str = typer.Option(..., "--url", help="要直接快取的文件入口 URL"),
    output: Path = typer.Option(..., "--output", help="本機原始 HTML、正文與 corpus.json 目錄"),
    max_bytes: Annotated[int, typer.Option("--max-bytes", min=1)] = 5 * 1024 * 1024,
) -> None:
    """直接快取一個入口頁，供空 catalog 或單頁文件使用。"""
    from loop_apidoc.url_catalog import CatalogNode, UrlCatalog, _canonical_url
    from loop_apidoc.url_corpus import cache_catalog_pages

    entry_url = _canonical_url(url, url) or url
    try:
        output.mkdir(parents=True, exist_ok=True)
        corpus = cache_catalog_pages(
            UrlCatalog(entry_url=entry_url, nodes=[CatalogNode(url=entry_url, title="Entry page")]),
            output,
            max_pages=1,
            max_bytes_per_page=max_bytes,
        )
    except (OSError, ValueError) as exc:
        typer.echo(f"cache-url-entry error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    corpus_path = output / "corpus.json"
    corpus_path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")
    fetched = sum(page.status == "fetched" for page in corpus.pages)
    typer.echo(f"corpus 已寫入 {corpus_path}；快取 {fetched} / 1 個入口頁，未送入模型")


@app.command(name="cache-gitbook-llms")
def cache_gitbook_llms_command(
    url: str = typer.Option(..., "--url", help="GitBook 文件入口 URL"),
    sources: Path = typer.Option(..., "--sources", help="不可變本機 Markdown 來源目錄"),
    coverage: Path = typer.Option(..., "--coverage", help="輸出的 URL coverage JSON"),
    max_bytes: Annotated[int, typer.Option("--max-bytes", min=1)] = 5 * 1024 * 1024,
) -> None:
    """從 GitBook llms.txt 快取所有安全、同範圍的 Markdown 頁面。"""
    from loop_apidoc.gitbook_llms import GitBookLlmsError, cache_gitbook_llms

    try:
        result = cache_gitbook_llms(
            url,
            sources=sources,
            coverage_output=coverage,
            max_bytes=max_bytes,
        )
    except GitBookLlmsError as exc:
        typer.echo(f"cache-gitbook-llms error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        json.dumps(
            {
                "index_url": result.index_url,
                "sources": str(result.sources),
                "coverage": str(result.coverage_path),
                "fetched": result.fetched,
                "fetch_failed": result.failed,
            },
            ensure_ascii=False,
        )
    )


@app.command(name="extract-markdown-drafts")
def extract_markdown_drafts_command(
    sources: Path = typer.Option(
        ..., "--sources", help="本機 Markdown 來源目錄", exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    manifest: Path = typer.Option(..., "--manifest", help="manifest.json", exists=True, readable=True),
    output: Path = typer.Option(..., "--output", help="輸出的 markdown-api-facts.json"),
) -> None:
    """從 manifest 指名的 Markdown 產生非權威 API facts 草稿。"""
    from loop_apidoc.markdown_drafts.collect import (
        MarkdownDraftInputError,
        collect_markdown_drafts,
        load_manifest,
    )

    try:
        if output.exists():
            raise MarkdownDraftInputError(f"output already exists: {output}")
        drafts = collect_markdown_drafts(sources, load_manifest(manifest))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(drafts.model_dump_json(indent=2), encoding="utf-8")
    except (MarkdownDraftInputError, OSError) as exc:
        typer.echo(f"extract-markdown-drafts error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Markdown API drafts 已寫入 {output}；掃描 {len(drafts.sources)} 個來源，僅供擷取輔助")


@app.command(name="snapshot-openapi-url")
def snapshot_openapi_url_command(
    url: str = typer.Option(..., "--url", help="直接回傳 OpenAPI JSON/YAML 的公開 URL"),
    sources: Path = typer.Option(..., "--sources", help="不可變本機來源快照目錄"),
    coverage: Path = typer.Option(..., "--coverage", help="輸出的單一 URL coverage.json"),
    filename: str | None = typer.Option(None, "--filename", help="快照檔名；預設取 URL 檔名"),
    confirmed_by_user: bool = typer.Option(False, "--confirmed-by-user", help="標記 URL scope 已由使用者確認"),
    max_bytes: Annotated[int, typer.Option("--max-bytes", min=1)] = 5 * 1024 * 1024,
) -> None:
    """下載單一 OpenAPI JSON/YAML 為來源快照與 coverage ledger。"""
    from loop_apidoc.openapi_snapshot import OpenApiSnapshotError, snapshot_openapi_url

    try:
        result = snapshot_openapi_url(
            url,
            sources=sources,
            coverage_output=coverage,
            filename=filename,
            confirmed_by_user=confirmed_by_user,
            max_bytes=max_bytes,
        )
    except OpenApiSnapshotError as exc:
        typer.echo(f"snapshot-openapi-url error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"OpenAPI snapshot 已寫入 {result.snapshot_path}；SHA-256 {result.sha256}；"
        f"coverage 已寫入 {result.coverage_path}"
    )


@app.command(name="record-fingerprint")
def record_fingerprint_command(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False, help="已完成的 run 目錄"),
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


@app.command(name="check-freshness")
def check_freshness_command(
    fingerprint: Path = typer.Option(..., "--fingerprint", exists=True, readable=True, help="基準 fingerprint 側檔"),
    sources: Path | None = typer.Option(None, "--sources", help="本地來源根目錄(fingerprint 含本地檔時必填)"),
    json_output: bool = typer.Option(False, "--json", help="輸出機器可讀 JSON"),
    report_dir: Path | None = typer.Option(None, "--report-dir", help="另存 freshness-report.{json,md}"),
) -> None:
    """比對來源當下訊號與基準,回報是否需要重新解析(退出碼 0/1/2)。"""
    from loop_apidoc.freshness.check import check_freshness
    from loop_apidoc.freshness.models import EXIT_CODES, FreshnessInputError, SourceFingerprint
    from loop_apidoc.freshness.report import render_markdown, write_reports

    try:
        loaded = SourceFingerprint.model_validate_json(fingerprint.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        typer.echo(f"check-freshness error: 無法讀取 fingerprint: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        report = check_freshness(loaded, sources_root=sources)
    except FreshnessInputError as exc:  # defensive; check_freshness normally returns a report
        typer.echo(f"check-freshness error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if report_dir is not None:
        write_reports(report, report_dir)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_markdown(report))
    raise typer.Exit(code=EXIT_CODES[report.verdict])


@app.command(name="check-freshness-batch")
def check_freshness_batch_command(
    watchlist: Path = typer.Option(..., "--watchlist", exists=True, readable=True, help="巡檢清單 freshness-watchlist.json"),
    json_output: bool = typer.Option(False, "--json", help="輸出機器可讀 JSON"),
    report_dir: Path | None = typer.Option(None, "--report-dir", help="另存 freshness-scan.{json,md}"),
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


@app.command(name="normalize-html-snapshot")
def normalize_html_snapshot_command(
    input: Path = typer.Option(..., "--input", exists=True, readable=True, help="已下載的 HTML 快照"),
    url: str = typer.Option(..., "--url", help="快照的原始公開 URL"),
    output: Path = typer.Option(..., "--output", help="輸出的 Markdown 快照"),
) -> None:
    """把靜態 HTML 快照正規化為受支援 Markdown，並保留 URL/hash provenance。"""
    from loop_apidoc.html_snapshot import normalize_html_snapshot

    try:
        sidecar = normalize_html_snapshot(input, url, output)
    except OSError as exc:
        typer.echo(f"normalize-html-snapshot error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"normalized snapshot 已寫入 {output}；provenance 已寫入 {sidecar}")


@app.command(name="related-url-pages")
def related_url_pages(
    corpus: Path = typer.Option(..., "--corpus", exists=True, readable=True),
    url: str = typer.Option(..., "--url", help="作為關聯起點的已快取頁面 URL"),
    output: Path = typer.Option(..., "--output", help="候選頁卡片 JSON"),
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, help="最多輸出的候選頁數"),
    ] = 20,
) -> None:
    """依正文連結與共享實體輸出候選頁卡片，不載入正文給模型。"""
    from pydantic import ValidationError

    from loop_apidoc.url_corpus import UrlCorpus, find_related_pages

    try:
        source = UrlCorpus.model_validate_json(corpus.read_text(encoding="utf-8"))
        related = find_related_pages(source, url, limit=limit)
    except (OSError, ValidationError, ValueError) as exc:
        typer.echo(f"related-url-pages error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    output.write_text(json.dumps([page.model_dump() for page in related], ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"related candidates 已寫入 {output}；{len(related)} 頁，未載入正文")


@app.command(name="assess-sources")
def assess_sources(
    sources: Path = typer.Option(..., "--sources", exists=True, file_okay=False),
    manifest: Path = typer.Option(..., "--manifest", exists=True),
    observations: Path = typer.Option(..., "--observations", exists=True),
    source_set: str = typer.Option(..., "--source-set"),
    output: Path = typer.Option(..., "--output"),
    base_manifest: Path | None = typer.Option(None, "--base-manifest", exists=True),
) -> None:
    """Assess source quality before extraction and write supplement reports."""
    from loop_apidoc.source_quality.assess import assess_source_quality
    from loop_apidoc.source_quality.diff import build_source_diff
    from loop_apidoc.source_quality.loader import (
        SourceQualityInputError,
        load_manifest,
        load_observations,
    )
    from loop_apidoc.source_quality.models import SourceDiffReport
    from loop_apidoc.source_quality.report import write_reports as write_quality_reports

    try:
        parsed_manifest = load_manifest(manifest)
        parsed_observations = load_observations(observations)
    except SourceQualityInputError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    report = assess_source_quality(
        manifest=parsed_manifest,
        source_set=source_set,
        observations=parsed_observations,
        base_report=None,
    )
    diff = build_source_diff(base=load_manifest(base_manifest), head=parsed_manifest) if base_manifest else SourceDiffReport()
    write_quality_reports(report, diff, output)
    typer.echo(f"source quality {report.verdict.value}: reports written to {output}")
    raise typer.Exit(code=0 if report.verdict.value == "pass" else 1)


@app.command(name="verify-extraction")
def verify_extraction(
    sources: Path = typer.Option(
        ..., "--sources", help="本機來源目錄（source 引用要比對 manifest）",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    extraction: Path = typer.Option(
        ..., "--extraction",
        help="agent 產出的擷取目錄(inventory.json + endpoints/*.json,選用 integration.json)",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    url: list[str] = typer.Option([], "--url", help="公開來源 URL,可重複指定"),
    exclude: list[str] = typer.Option(
        [], "--exclude",
        help="額外排除的 glob(可重複);預設已排除 README/LICENSE/CHANGELOG 等非規格檔",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="把違規以 JSON 陣列印到 stdout(供 agent 解析)"
    ),
) -> None:
    """檢查 agent 產出的擷取 JSON 是否符合契約;不寫檔、不建立 run 目錄。

    exit 0 乾淨;exit 2 有違規或硬 schema 錯誤（不會是 1——1 代表 validate FAIL）。
    """
    from loop_apidoc.agentcli.assemble import AssembleInputError
    from loop_apidoc.agentcli.verify import verify_extraction_dir

    try:
        violations = verify_extraction_dir(
            sources_root=sources,
            extraction_dir=extraction,
            generated_at=datetime.now(timezone.utc),
            urls=list(url),
            excludes=tuple(exclude),
        )
    except AssembleInputError as exc:
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
    raise typer.Exit(code=2 if violations else 0)


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
        f"breaking {report.summary.get('breaking', 0)}，"
        f"additive {report.summary.get('additive', 0)}，"
        f"changed {report.summary.get('changed', 0)}，"
        f"source_only {report.summary.get('source_only', 0)}；"
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
    exclude: list[str] = typer.Option(
        [], "--exclude",
        help="額外排除的 glob(可重複);預設已排除 README/LICENSE/CHANGELOG 等非規格檔",
    ),
    url_coverage: Path = typer.Option(
        None, "--url-coverage",
        help="agent 產出的 url_sources/coverage.json 路徑;有 URL 來源時檢核撈取涵蓋率",
    ),
    source_quality: Path = typer.Option(
        None,
        "--source-quality",
        help="assess-sources 產出的報告目錄;reject 會阻止組裝並把通過報告存入 run-dir",
    ),
    extractor_model: str = typer.Option(
        None,
        "--extractor-model",
        help="執行擷取的模型名稱,由 agent 明確帶入並記入 run.json;省略即 null(CLI 不推測)",
    ),
    architecture_mode: ArchitectureMode = typer.Option(
        ArchitectureMode.LEGACY,
        "--architecture-mode",
        case_sensitive=False,
        help="架構執行模式:legacy 或非阻斷的 Core shadow",
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
            url_coverage_path=url_coverage,
            source_quality_dir=source_quality,
            excludes=tuple(exclude),
            extractor_model=extractor_model,
            architecture_mode=architecture_mode,
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

    if result.shadow is not None and result.shadow.status == "error":
        typer.echo(
            f"shadow error:{result.shadow.message or 'shadow execution failed'}",
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
