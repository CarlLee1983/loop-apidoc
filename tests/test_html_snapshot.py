from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app


def test_normalize_html_snapshot_writes_markdown_and_provenance(tmp_path: Path):
    raw = tmp_path / "page.html"
    raw.write_text("<nav>menu</nav><main><h1>Transfer</h1><p>Body text</p></main>", encoding="utf-8")
    output = tmp_path / "sources" / "transfer.md"

    result = CliRunner().invoke(app, ["normalize-html-snapshot", "--input", str(raw), "--url", "https://docs.example.com/transfer", "--output", str(output)])

    assert result.exit_code == 0, result.stdout
    assert output.read_text(encoding="utf-8") == "# Transfer\n\nBody text\n"
    provenance = json.loads(output.with_suffix(".md.source.json").read_text(encoding="utf-8"))
    assert provenance["url"] == "https://docs.example.com/transfer"
    assert provenance["raw_file"] == str(raw)
