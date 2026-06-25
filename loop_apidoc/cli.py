from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer

from loop_apidoc.manifest.builder import build_manifest

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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
