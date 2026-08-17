from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.manifest.formats import (
    detect_format,
    is_supported,
    unsupported_remedy,
)
from loop_apidoc.run.runid import make_run_id
from loop_apidoc.score.models import ScoreProfile
from loop_apidoc.shadow.models import ArchitectureMode
from loop_apidoc.url_corpus import UrlCorpus
from loop_apidoc.validate import validate_run_dir, write_reports

app = typer.Typer(
    help="Loop 來源依據式 API 文件 pipeline",
    no_args_is_help=True,
)

from loop_apidoc.foundry.cli import foundry_app  # noqa: E402  (must follow `app` definition)
from loop_apidoc.feedback.cli import feedback_app  # noqa: E402

app.add_typer(foundry_app, name="foundry")
app.add_typer(feedback_app, name="feedback")


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
        help="本機來源目錄或單一來源檔案",
        exists=True,
        file_okay=True,
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
    url_coverage: Path | None = typer.Option(
        None,
        "--url-coverage",
        exists=True,
        readable=True,
        help="URL coverage.json；驗證匹配的 rendered snapshot 後可免 origin fetch",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="manifest.json 輸出路徑；省略則輸出至 stdout",
    ),
) -> None:
    """掃描本機來源並建立來源 manifest。"""
    generated_at = datetime.now(timezone.utc)
    sources_root = sources.parent if sources.is_file() else sources
    selected_relative_path = (
        sources.relative_to(sources_root).as_posix() if sources.is_file() else None
    )
    from loop_apidoc.manifest.builder import ManifestInputError
    from loop_apidoc.manifest.scanner import ManifestScanError
    from loop_apidoc.preparation.coverage import CoverageInputError, load_coverage

    try:
        parsed_coverage = load_coverage(url_coverage) if url_coverage else None
        if parsed_coverage is not None and not url:
            raise ManifestInputError(
                "--url-coverage requires at least one matching --url source"
            )
        result = build_manifest(
            sources_root=sources_root,
            urls=list(url),
            generated_at=generated_at,
            excludes=tuple(exclude),
            url_coverage=parsed_coverage,
        )
    except (CoverageInputError, ManifestScanError) as exc:
        typer.echo(f"manifest error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if selected_relative_path is not None:
        result = result.model_copy(
            update={
                "local_sources": [
                    source
                    for source in result.local_sources
                    if source.relative_path == selected_relative_path
                ]
            }
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


def _emit_spa_shell_warning(corpus: UrlCorpus) -> None:
    documents = [page for page in corpus.pages if page.source_kind == "document"]
    shells = sum(page.spa_shell_detected for page in documents)
    if shells:
        typer.echo(
            f"{shells}/{len(documents)} pages look like un-rendered SPA shells",
            err=True,
        )


@app.command(name="cache-url-pages")
def cache_url_pages(
    catalog: Path = typer.Option(..., "--catalog", exists=True, readable=True),
    output: Path = typer.Option(..., "--output", help="本機原始 HTML、正文與 corpus.json 目錄"),
    max_pages: Annotated[
        int,
        typer.Option(
            "--max-pages",
            min=1,
            help="本次可快取的最大總頁數（含探測取得的 OpenAPI 規格）",
        ),
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
    _emit_spa_shell_warning(corpus)
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
    _emit_spa_shell_warning(corpus)
    fetched = sum(
        page.status == "fetched" and page.source_kind == "document"
        for page in corpus.pages
    )
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


@app.command(name="scaffold-extraction")
def scaffold_extraction_command(
    sources: Path = typer.Option(
        ..., "--sources", help="本機 Markdown 來源目錄", exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    manifest: Path = typer.Option(..., "--manifest", help="manifest.json", exists=True, readable=True),
    output: Path = typer.Option(..., "--output", help="非權威 extraction scaffold 輸出目錄"),
) -> None:
    """從 Markdown 草稿投影出待人工覆核的 extraction scaffold。"""
    from loop_apidoc.extraction_scaffold.collect import (
        ExtractionScaffoldInputError,
        collect_scaffold_inputs,
    )
    from loop_apidoc.extraction_scaffold.project import project_scaffold
    from loop_apidoc.extraction_scaffold.write import write_scaffold
    from loop_apidoc.markdown_drafts.collect import MarkdownDraftInputError, load_manifest

    try:
        inputs = collect_scaffold_inputs(sources, load_manifest(manifest))
        bundle = project_scaffold(inputs.drafts, inputs.source_texts, sources.name)
        write_scaffold(bundle, output)
    except (ExtractionScaffoldInputError, MarkdownDraftInputError, OSError) as exc:
        typer.echo(f"scaffold-extraction error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(bundle.summary(str(output)), ensure_ascii=False))


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


@app.command(name="import-supplementary-note")
def import_supplementary_note_command(
    input: Path = typer.Option(
        ..., "--input", exists=True, readable=True, help="人工摘錄的 Markdown"
    ),
    received_from: str = typer.Option(
        ..., "--from", help="誰給的：寄件者、通訊軟體帳號或提供者"
    ),
    received_at: str = typer.Option(
        ..., "--received-at", help="含時區的 ISO-8601 收到時間"
    ),
    excerpted_by: str = typer.Option(..., "--excerpted-by", help="摘錄者"),
    sources: Path = typer.Option(..., "--sources", help="不可變本機來源目錄"),
    subject: str | None = typer.Option(None, "--subject", help="信件主旨或標題"),
    filename: str | None = typer.Option(
        None, "--filename", help="來源檔名；預設沿用輸入檔名"
    ),
) -> None:
    """匯入供應商補充說明的人工摘錄，標記為次級佐證。"""
    from loop_apidoc.supplementary_note import (
        SupplementaryNoteError,
        import_supplementary_note,
    )

    try:
        result = import_supplementary_note(
            input,
            received_from=received_from,
            received_at=received_at,
            excerpted_by=excerpted_by,
            sources=sources,
            subject=subject,
            filename=filename,
        )
    except (SupplementaryNoteError, OSError) as exc:
        typer.echo(f"import-supplementary-note error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"次級佐證已寫入 {result.source_path}；SHA-256 {result.sha256}；"
        f"provenance 已寫入 {result.provenance_path}"
    )


@app.command(name="import-rendered-url")
def import_rendered_url_command(
    input: Path = typer.Option(
        ..., "--input", exists=True, readable=True, help="已由瀏覽器儲存或渲染的 HTML/Markdown"
    ),
    url: str = typer.Option(..., "--url", help="快照的原始公開 URL"),
    captured_at: str = typer.Option(
        ..., "--captured-at", help="含時區的 ISO-8601 擷取時間"
    ),
    capture_method: str = typer.Option(
        ..., "--capture-method", help="browser_save 或 playwright"
    ),
    sources: Path = typer.Option(..., "--sources", help="不可變本機來源目錄"),
    coverage: Path = typer.Option(..., "--coverage", help="輸出的 URL coverage.json"),
    filename: str | None = typer.Option(None, "--filename", help="來源檔名；預設沿用輸入檔名"),
    confirmed_by_user: bool = typer.Option(
        False, "--confirmed-by-user", help="標記 URL scope 已由使用者確認"
    ),
) -> None:
    """離線匯入 browser-rendered URL source、provenance 與 coverage。"""
    from loop_apidoc.rendered_url import RenderedUrlImportError, import_rendered_url

    try:
        result = import_rendered_url(
            input,
            original_url=url,
            captured_at=captured_at,
            capture_method=capture_method,
            sources=sources,
            coverage_output=coverage,
            filename=filename,
            confirmed_by_user=confirmed_by_user,
        )
    except (RenderedUrlImportError, OSError) as exc:
        typer.echo(f"import-rendered-url error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"rendered source 已寫入 {result.source_path}；SHA-256 {result.sha256}；"
        f"provenance 已寫入 {result.provenance_path}；coverage 已寫入 {result.coverage_path}"
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


@app.command(name="governance-scan")
def governance_scan_command(
    watchlist: Path = typer.Option(..., "--watchlist", exists=True, readable=True, help="巡檢清單 freshness-watchlist.json"),
    json_output: bool = typer.Option(False, "--json", help="輸出機器可讀 JSON"),
    report_dir: Path | None = typer.Option(None, "--report-dir", help="另存 governance-trigger.{json,md}"),
    snapshot_dir: Path | None = typer.Option(None, "--snapshot-dir", help="保留 changed 來源的不可覆寫證據快照"),
) -> None:
    """建立需人工審核的來源變動觸發；不會生成、匯入或核准契約。"""
    from loop_apidoc.freshness.batch import load_watchlist, scan_watchlist
    from loop_apidoc.freshness.models import EXIT_CODES, FreshnessInputError, FreshnessVerdict
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
            report = report.model_copy(update={"snapshot": write_snapshot(scan, snapshot_dir)})
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


@app.command(name="governance-review-plan")
def governance_review_plan_command(
    trigger: Path = typer.Option(..., "--trigger", exists=True, readable=True, help="governance-trigger.json"),
    snapshot: Path | None = typer.Option(None, "--snapshot", help="immutable governance snapshot 目錄"),
    output: Path = typer.Option(..., "--output", help="governance-review-plan.{json,md} 輸出目錄"),
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
        typer.echo(f"governance-review-plan error: output path is a file: {output}", err=True)
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
        typer.echo(f"governance-review-plan COMPLETE: {len(plan.items)} item(s)；報告寫入 {output}")


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


@app.command(name="inspect-source-risk")
def inspect_source_risk(
    sources: Path = typer.Option(
        ..., "--sources", exists=True, file_okay=False, readable=True
    ),
    manifest: Path = typer.Option(..., "--manifest", exists=True, readable=True),
    output: Path = typer.Option(..., "--output"),
    max_bytes: Annotated[
        int,
        typer.Option(
            "--max-bytes",
            min=1,
            help="每個文字來源可完整掃描的最大位元組數",
        ),
    ] = 5 * 1024 * 1024,
) -> None:
    """Inspect manifest sources for deterministic pre-agent content risks."""
    import hashlib

    from loop_apidoc.source_quality.loader import (
        SourceQualityInputError,
        load_manifest,
    )
    from loop_apidoc.source_risk import SourceRiskInputError, inspect_source_risks
    from loop_apidoc.source_risk.report import write_reports as write_risk_reports

    try:
        manifest_bytes = manifest.read_bytes()
        parsed_manifest = load_manifest(manifest)
        report = inspect_source_risks(
            sources_root=sources,
            manifest=parsed_manifest,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            max_bytes=max_bytes,
        )
        write_risk_reports(report, output)
    except (OSError, SourceQualityInputError, SourceRiskInputError) as exc:
        typer.echo(f"inspect-source-risk error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"source risk {report.verdict.value}: reports written to {output}")
    raise typer.Exit(code=0 if report.verdict.value == "pass" else 1)


@app.command(name="assess-sources")
def assess_sources(
    sources: Path = typer.Option(..., "--sources", exists=True, file_okay=False),
    manifest: Path = typer.Option(..., "--manifest", exists=True),
    source_risk: Path = typer.Option(
        ...,
        "--source-risk",
        exists=True,
        file_okay=False,
        readable=True,
        help="inspect-source-risk 產出的 pass report 目錄",
    ),
    observations: Path = typer.Option(..., "--observations", exists=True),
    source_set: str = typer.Option(..., "--source-set"),
    output: Path = typer.Option(..., "--output"),
    base_manifest: Path | None = typer.Option(None, "--base-manifest", exists=True),
) -> None:
    """Assess source quality before extraction and write supplement reports."""
    import hashlib

    from loop_apidoc.source_quality.assess import assess_source_quality
    from loop_apidoc.source_quality.diff import build_source_diff
    from loop_apidoc.source_quality.loader import (
        SourceQualityInputError,
        load_manifest,
        load_observations,
    )
    from loop_apidoc.source_quality.models import SourceDiffReport
    from loop_apidoc.source_quality.report import write_reports as write_quality_reports
    from loop_apidoc.source_risk import (
        SourceRiskInputError,
        load_verified_source_risk_report,
    )

    try:
        manifest_bytes = manifest.read_bytes()
        parsed_manifest = load_manifest(manifest)
        parsed_source_risk = load_verified_source_risk_report(
            source_risk,
            manifest=parsed_manifest,
            sources_root=sources,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        )
        parsed_observations = load_observations(observations)
    except (OSError, SourceQualityInputError, SourceRiskInputError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    report = assess_source_quality(
        manifest=parsed_manifest,
        source_set=source_set,
        observations=parsed_observations,
        base_report=None,
        source_risk=parsed_source_risk,
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
    focus: Path | None = typer.Option(
        None, "--focus",
        help="擷取重點指令檔(focus.json);agent 的應答讀自 <extraction>/focus-response.json",
        exists=True, file_okay=True, dir_okay=False, readable=True,
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
            extraction_dir=extraction, focus_file=focus)
        if falsified and not json_out:
            typer.echo(
                f"預告:{len(falsified)} 條 expectation directive 落空"
                f"({'、'.join(falsified)});assemble 會以 FOCUS_UNMET 判定驗證失敗,"
                "但仍會產出 run 目錄供你判斷是來源真的沒有、還是查得不夠。",
                err=True,
            )
        # 呼叫本身也擋在 json_out 外面,不只擋 echo:預告在 `--json` 下是純浪費,
        # 而它跑在 PASS 印出之後,任何例外都會把一次通過的 verify 變成 traceback。
        shortfall = [] if json_out else preview_error_code_shortfall(
            sources_root=sources,
            extraction_dir=extraction,
            generated_at=generated_at,
            focus_file=focus,
            excludes=tuple(exclude),
        )
        if shortfall:
            typer.echo(
                f"預告:{len(shortfall)} 條窮盡型 directive 報得比來源記載的錯誤碼少"
                f"({'; '.join(shortfall)});assemble 會以 FOCUS_INCOMPLETE 提出,"
                "severity 由 directive 的 kind 決定。回到來源把漏掉的碼補進擷取。",
                err=True,
            )
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
    port: Annotated[int, typer.Option("--port", min=0, max=65535, help="本機 GUI port；0 表示自動選擇")] = 0,
    no_open: bool = typer.Option(False, "--no-open", help="只印出 URL，不嘗試開啟瀏覽器"),
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
            typer.echo("review browser launch failed; open the printed URL manually", err=True)
    try:
        adapter.serve_forever()
    except KeyboardInterrupt:
        typer.echo("review GUI stopped")
    finally:
        adapter.shutdown()


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
        None, "--focus",
        help="擷取重點指令檔(focus.json);agent 的應答讀自 <extraction>/focus-response.json",
        exists=True, file_okay=True, dir_okay=False, readable=True,
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


@app.command()
def preprocess(
    sources: Path = typer.Option(
        ..., "--sources", help="本機來源目錄或單一檔案",
        exists=True, file_okay=True, dir_okay=True, readable=True,
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
