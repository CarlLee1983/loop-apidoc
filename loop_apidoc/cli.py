from __future__ import annotations

import typer

app = typer.Typer(
    help="Loop 來源依據式 API 文件 pipeline",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """Loop 來源依據式 API 文件 pipeline。"""


def main() -> None:
    app()


if __name__ == "__main__":
    main()
