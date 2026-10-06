from __future__ import annotations

from importlib.metadata import version
from typing import Annotated

import typer

from loop_apidoc.commands.acquisition import (
    cache_gitbook_llms_command,
    cache_url_entry,
    cache_url_pages,
    catalog_url,
    import_rendered_url_command,
    import_supplementary_note_command,
    manifest,
    normalize_html_snapshot_command,
    related_url_pages,
    select_url,
    snapshot_openapi_url_command,
)
from loop_apidoc.commands.drafts import (
    extract_markdown_drafts_command,
    scaffold_extraction_command,
)
from loop_apidoc.commands.extraction import assemble, preprocess, verify_extraction
from loop_apidoc.commands.freshness import (
    check_freshness_batch_command,
    check_freshness_command,
    record_fingerprint_command,
)
from loop_apidoc.commands.governance import (
    governance_review_plan_command,
    governance_scan_command,
)
from loop_apidoc.commands.runs import diff, evaluate, review, score, validate
from loop_apidoc.commands.source_quality import assess_sources, inspect_source_risk

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


app.command()(manifest)
app.command(name="catalog-url")(catalog_url)
app.command(name="select-url")(select_url)
app.command(name="cache-url-pages")(cache_url_pages)
app.command(name="cache-url-entry")(cache_url_entry)
app.command(name="cache-gitbook-llms")(cache_gitbook_llms_command)
app.command(name="extract-markdown-drafts")(extract_markdown_drafts_command)
app.command(name="scaffold-extraction")(scaffold_extraction_command)
app.command(name="snapshot-openapi-url")(snapshot_openapi_url_command)
app.command(name="import-supplementary-note")(import_supplementary_note_command)
app.command(name="import-rendered-url")(import_rendered_url_command)
app.command(name="record-fingerprint")(record_fingerprint_command)
app.command(name="check-freshness")(check_freshness_command)
app.command(name="check-freshness-batch")(check_freshness_batch_command)
app.command(name="governance-scan")(governance_scan_command)
app.command(name="governance-review-plan")(governance_review_plan_command)
app.command(name="normalize-html-snapshot")(normalize_html_snapshot_command)
app.command(name="related-url-pages")(related_url_pages)
app.command(name="inspect-source-risk")(inspect_source_risk)
app.command(name="assess-sources")(assess_sources)
app.command(name="verify-extraction")(verify_extraction)
app.command()(validate)
app.command()(diff)
app.command()(review)
app.command()(score)
app.command()(evaluate)
app.command()(assemble)
app.command()(preprocess)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
