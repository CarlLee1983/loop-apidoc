from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

foundry_app = typer.Typer(
    help="Foundry API 專案本地資產治理（docset / candidate / asset）",
    no_args_is_help=True,
)


def _parse_source(raw: str) -> object:
    from loop_apidoc.foundry.models import SourceRef, SourceRole

    path, _, role_str = raw.partition(":")
    role = SourceRole(role_str) if role_str else SourceRole.PRIMARY
    kind = "url" if path.startswith(("http://", "https://")) else "file"
    return SourceRef(kind=kind, path=path, role=role)


@foundry_app.command("init")
def init(
    project: Path = typer.Option(Path("."), "--project", help="專案根目錄"),
    docset: str = typer.Option(..., "--docset", help="docset 識別碼"),
    title: str = typer.Option(..., "--title", help="docset 標題"),
    provider: str = typer.Option(..., "--provider", help="API 供應商"),
    product: str = typer.Option(..., "--product", help="產品/子系統名稱"),
    scope: str = typer.Option("", "--scope", help="來源範圍描述"),
    source: list[str] = typer.Option([], "--source", help="來源 path[:role]，可重複"),
    exist_ok: bool = typer.Option(False, "--exist-ok", help="docset 已存在時更新而非報錯"),
) -> None:
    """建立或更新一個 docset。"""
    from loop_apidoc.foundry.models import Docset, FoundryInputError
    from loop_apidoc.foundry.register import register_docset

    ds = Docset(
        docset_id=docset,
        title=title,
        provider=provider,
        product=product,
        source_scope=scope,
        sources=[_parse_source(s) for s in source],
    )
    try:
        result = register_docset(project, ds, exist_ok=exist_ok)
    except FoundryInputError as exc:
        typer.echo(f"foundry init input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"docset 已寫入：{result.docset_id}")


@foundry_app.command("import")
def import_(
    project: Path = typer.Option(Path("."), "--project", help="專案根目錄"),
    docset: str = typer.Option(..., "--docset", help="目標 docset 識別碼"),
    run: Path = typer.Option(..., "--run", help="已完成的 run 目錄"),
    overwrite: bool = typer.Option(False, "--overwrite", help="覆寫已存在的 candidate"),
) -> None:
    """將一個 run 目錄匯入為 candidate。"""
    from loop_apidoc.foundry.importer import import_run
    from loop_apidoc.foundry.models import FoundryInputError

    try:
        result = import_run(project, docset, run, overwrite=overwrite)
    except FoundryInputError as exc:
        typer.echo(f"foundry import input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"candidate 已匯入：{result.run_id}")


@foundry_app.command("approve")
def approve(
    project: Path = typer.Option(Path("."), "--project", help="專案根目錄"),
    docset: str = typer.Option(..., "--docset", help="docset 識別碼"),
    run: str = typer.Option(..., "--run", help="candidate 的 run id"),
    by: str = typer.Option(..., "--by", help="核准者身分或自動化閘門，如 human-review / ci-score-90"),
    min_score: Annotated[int | None, typer.Option("--min-score", min=0, max=100, help="核准所需最低分數")] = None,
    allow_failing: bool = typer.Option(False, "--allow-failing", help="即使 validation 失敗仍核准"),
    known_gap: list[str] = typer.Option([], "--known-gap", help="已知缺口，可重複"),
    json_out: bool = typer.Option(False, "--json", help="以 JSON 輸出 asset"),
) -> None:
    """將 candidate 核准為版本化 asset 並更新 current 指標。"""
    from loop_apidoc.foundry.approve import approve_candidate
    from loop_apidoc.foundry.models import FoundryApprovalError, FoundryInputError

    try:
        asset = approve_candidate(
            project, docset, run,
            approved_by=by,
            now=datetime.now(timezone.utc),
            min_score=min_score,
            allow_failing=allow_failing,
            known_gaps=list(known_gap),
        )
    except FoundryInputError as exc:
        typer.echo(f"foundry approve input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except FoundryApprovalError as exc:
        typer.echo(f"foundry approve rejected: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_out:
        typer.echo(asset.model_dump_json(indent=2))
    else:
        typer.echo(f"asset 已核准：{asset.asset_id}（current 已更新）")


@foundry_app.command("list")
def list_(
    project: Path = typer.Option(Path("."), "--project", help="專案根目錄"),
    json_out: bool = typer.Option(False, "--json", help="以 JSON 輸出目錄"),
) -> None:
    """列出所有 docset 及其 current asset。"""
    from loop_apidoc.foundry.query import list_docsets

    catalog = list_docsets(project)
    if json_out:
        typer.echo(catalog.model_dump_json(indent=2))
    else:
        for entry in catalog.docsets:
            typer.echo(f"{entry.docset_id}\t{entry.title}\tcurrent={entry.current_asset}")


@foundry_app.command("current")
def current(
    project: Path = typer.Option(Path("."), "--project", help="專案根目錄"),
    docset: str = typer.Option(..., "--docset", help="docset 識別碼"),
    json_out: bool = typer.Option(False, "--json", help="以 JSON 輸出 current 指標"),
) -> None:
    """顯示 docset 的 current 指標。"""
    from loop_apidoc.foundry import store

    pointer = store.load_current(project, docset)
    if pointer is None:
        typer.echo(f"foundry current input error: no current asset for {docset}", err=True)
        raise typer.Exit(code=2)
    if json_out:
        typer.echo(pointer.model_dump_json(indent=2))
    else:
        typer.echo(f"{pointer.current_asset}\tvalidation.ok={pointer.validation.ok}\tscore={pointer.validation.score}")
