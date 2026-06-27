from __future__ import annotations

from pathlib import Path

import pymupdf
from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()


def test_preprocess_copies_text_sources(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "notes.md").write_text("# Hello\nGET /ping", encoding="utf-8")
    out = tmp_path / "md"
    res = runner.invoke(app, ["preprocess", "--sources", str(sources), "--out", str(out)])
    assert res.exit_code == 0
    assert (out / "notes.md").read_text(encoding="utf-8") == "# Hello\nGET /ping"


def test_preprocess_converts_pdf_to_markdown(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Payment API")
    doc.save(str(sources / "manual.pdf"))
    doc.close()
    out = tmp_path / "md"
    res = runner.invoke(app, ["preprocess", "--sources", str(sources), "--out", str(out)])
    assert res.exit_code == 0
    md = (out / "manual.md").read_text(encoding="utf-8")
    assert "Payment API" in md
    assert "<!-- page 1 -->" in md
