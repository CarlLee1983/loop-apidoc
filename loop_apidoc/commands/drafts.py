from __future__ import annotations

import json
from pathlib import Path

import typer


def extract_markdown_drafts_command(
    sources: Path = typer.Option(
        ...,
        "--sources",
        help="本機 Markdown 來源目錄",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    manifest: Path = typer.Option(
        ..., "--manifest", help="manifest.json", exists=True, readable=True
    ),
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
    typer.echo(
        f"Markdown API drafts 已寫入 {output}；掃描 {len(drafts.sources)} 個來源，僅供擷取輔助"
    )


def scaffold_extraction_command(
    sources: Path = typer.Option(
        ...,
        "--sources",
        help="本機 Markdown 來源目錄",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    manifest: Path = typer.Option(
        ..., "--manifest", help="manifest.json", exists=True, readable=True
    ),
    output: Path = typer.Option(
        ..., "--output", help="非權威 extraction scaffold 輸出目錄"
    ),
) -> None:
    """從 Markdown 草稿投影出待人工覆核的 extraction scaffold。"""
    from loop_apidoc.extraction_scaffold.collect import (
        ExtractionScaffoldInputError,
        collect_scaffold_inputs,
    )
    from loop_apidoc.extraction_scaffold.project import project_scaffold
    from loop_apidoc.extraction_scaffold.write import write_scaffold
    from loop_apidoc.markdown_drafts.collect import (
        MarkdownDraftInputError,
        load_manifest,
    )

    try:
        inputs = collect_scaffold_inputs(sources, load_manifest(manifest))
        bundle = project_scaffold(inputs.drafts, inputs.source_texts, sources.name)
        write_scaffold(bundle, output)
    except (ExtractionScaffoldInputError, MarkdownDraftInputError, OSError) as exc:
        typer.echo(f"scaffold-extraction error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(bundle.summary(str(output)), ensure_ascii=False))
