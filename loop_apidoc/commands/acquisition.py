from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.url_corpus import UrlCorpus
from loop_apidoc.url_safety import redact_url


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
    from loop_apidoc.url_coverage import CoverageInputError, load_coverage

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
    typer.echo(
        f"catalog 已寫入 {output}；發現 {len(catalog.nodes)} 個導航頁面，未擷取任何子頁"
    )


def select_url(
    catalog: Path = typer.Option(..., "--catalog", exists=True, readable=True),
    output: Path = typer.Option(..., "--output", help="輸出的本次擷取 selection JSON"),
    branch: list[str] = typer.Option([], "--branch", help="導航分支關鍵字；可重複指定"),
    term: list[str] = typer.Option(
        [], "--term", help="標題／breadcrumb／URL 關鍵字；可重複指定"
    ),
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


def cache_url_pages(
    catalog: Path = typer.Option(..., "--catalog", exists=True, readable=True),
    output: Path = typer.Option(
        ..., "--output", help="本機原始 HTML、正文與 corpus.json 目錄"
    ),
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
    typer.echo(
        f"corpus 已寫入 {corpus_path}；快取 {fetched} / {len(corpus.pages)} 頁，未送入模型"
    )


def cache_url_entry(
    url: str = typer.Option(..., "--url", help="要直接快取的文件入口 URL"),
    output: Path = typer.Option(
        ..., "--output", help="本機原始 HTML、正文與 corpus.json 目錄"
    ),
    max_bytes: Annotated[int, typer.Option("--max-bytes", min=1)] = 5 * 1024 * 1024,
) -> None:
    """直接快取一個入口頁，供空 catalog 或單頁文件使用。"""
    from loop_apidoc.url_catalog import CatalogNode, UrlCatalog, _canonical_url
    from loop_apidoc.url_corpus import cache_catalog_pages

    entry_url = _canonical_url(url, url) or url
    try:
        output.mkdir(parents=True, exist_ok=True)
        corpus = cache_catalog_pages(
            UrlCatalog(
                entry_url=entry_url,
                nodes=[CatalogNode(url=entry_url, title="Entry page")],
            ),
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
    output.write_text(
        json.dumps(
            [page.model_dump() for page in related], ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    typer.echo(f"related candidates 已寫入 {output}；{len(related)} 頁，未載入正文")


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
                "index_url": redact_url(result.index_url),
                "sources": str(result.sources),
                "coverage": str(result.coverage_path),
                "fetched": result.fetched,
                "fetch_failed": result.failed,
            },
            ensure_ascii=False,
        )
    )


def snapshot_openapi_url_command(
    url: str = typer.Option(..., "--url", help="直接回傳 OpenAPI JSON/YAML 的公開 URL"),
    sources: Path = typer.Option(..., "--sources", help="不可變本機來源快照目錄"),
    coverage: Path = typer.Option(
        ..., "--coverage", help="輸出的單一 URL coverage.json"
    ),
    filename: str | None = typer.Option(
        None, "--filename", help="快照檔名；預設取 URL 檔名"
    ),
    confirmed_by_user: bool = typer.Option(
        False, "--confirmed-by-user", help="標記 URL scope 已由使用者確認"
    ),
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


def import_rendered_url_command(
    input: Path = typer.Option(
        ...,
        "--input",
        exists=True,
        readable=True,
        help="已由瀏覽器儲存或渲染的 HTML/Markdown",
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
    filename: str | None = typer.Option(
        None, "--filename", help="來源檔名；預設沿用輸入檔名"
    ),
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


def normalize_html_snapshot_command(
    input: Path = typer.Option(
        ..., "--input", exists=True, readable=True, help="已下載的 HTML 快照"
    ),
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
