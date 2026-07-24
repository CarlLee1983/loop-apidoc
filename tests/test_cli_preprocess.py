from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from loop_apidoc.agentcli.preprocess import PreprocessResult, prepare_markdown
from loop_apidoc.cli import app

runner = CliRunner()


def test_prepare_markdown_returns_categorized_relative_paths_and_passthrough_bytes(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "notes.md").write_text("# Hello\nGET /ping", encoding="utf-8")
    docx_bytes = b"PK\x03\x04docx\x00\xff"
    json_bytes = b'{"openapi":"3.1.0"}\n'
    yaml_bytes = b"openapi: 3.1.0\n"
    (sources / "manual.docx").write_bytes(docx_bytes)
    (sources / "openapi.json").write_bytes(json_bytes)
    (sources / "openapi.yaml").write_bytes(yaml_bytes)
    out = tmp_path / "md"

    result = prepare_markdown(sources, out)

    assert isinstance(result, PreprocessResult)
    assert result.dest_dir == out
    assert result.converted == []
    assert result.copied == [Path("notes.md")]
    assert result.passthrough == [
        Path("manual.docx"),
        Path("openapi.json"),
        Path("openapi.yaml"),
    ]
    assert (out / "notes.md").read_text(encoding="utf-8") == "# Hello\nGET /ping"
    assert (out / "manual.docx").read_bytes() == docx_bytes
    assert (out / "openapi.json").read_bytes() == json_bytes
    assert (out / "openapi.yaml").read_bytes() == yaml_bytes


def test_prepare_markdown_preserves_source_paths_and_disambiguates_pdf_output(
    tmp_path: Path,
):
    sources = tmp_path / "sources"
    (sources / "merchant-a").mkdir(parents=True)
    (sources / "merchant-b").mkdir()
    (sources / "merchant-a" / "guide.md").write_text("# A", encoding="utf-8")
    (sources / "merchant-b" / "guide.md").write_text("# B", encoding="utf-8")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "PDF guide")
    doc.save(str(sources / "merchant-a" / "guide.pdf"))
    doc.close()
    out = tmp_path / "prepared"

    result = prepare_markdown(sources, out)

    assert result.copied == [Path("merchant-a/guide.md"), Path("merchant-b/guide.md")]
    assert result.converted == [Path("merchant-a/guide.pdf.md")]
    assert (out / "merchant-a" / "guide.md").read_text(encoding="utf-8") == "# A"
    assert (out / "merchant-b" / "guide.md").read_text(encoding="utf-8") == "# B"
    assert (out / "merchant-a" / "guide.pdf.md").exists()


def test_prepare_markdown_rejects_remaining_derived_output_collisions(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "PDF guide")
    doc.save(str(sources / "guide.pdf"))
    doc.close()
    (sources / "guide.pdf.md").write_text("# Existing markdown", encoding="utf-8")
    out = tmp_path / "prepared"

    with pytest.raises(ValueError, match="preprocess output collision"):
        prepare_markdown(sources, out)

    assert not (out / "guide.pdf.md").exists()


def test_preprocess_copies_text_sources(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "notes.md").write_text("# Hello\nGET /ping", encoding="utf-8")
    out = tmp_path / "md"

    res = runner.invoke(app, ["preprocess", "--sources", str(sources), "--out", str(out)])

    assert res.exit_code == 0
    assert (out / "notes.md").read_text(encoding="utf-8") == "# Hello\nGET /ping"
    assert "converted 0 / copied 1 / passthrough 0" in res.stdout


def test_preprocess_accepts_a_single_source_file(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    selected = sources / "selected.md"
    selected.write_text("# Selected\nGET /selected", encoding="utf-8")
    (sources / "unselected.md").write_text("# Unselected", encoding="utf-8")
    out = tmp_path / "md"

    res = runner.invoke(app, ["preprocess", "--sources", str(selected), "--out", str(out)])

    assert res.exit_code == 0
    assert (out / "selected.md").read_text(encoding="utf-8") == "# Selected\nGET /selected"
    assert not (out / "unselected.md").exists()
    assert "converted 0 / copied 1 / passthrough 0" in res.stdout


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
    md = (out / "manual.pdf.md").read_text(encoding="utf-8")
    assert "Payment API" in md
    assert "<!-- page 1 -->" in md
    assert "converted 1 / copied 0 / passthrough 0" in res.stdout


def test_preprocess_cli_lists_passthrough_files(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "guide.docx").write_bytes(b"docx bytes")
    (sources / "contract.json").write_bytes(b'{"paths":{}}')
    out = tmp_path / "md"

    res = runner.invoke(app, ["preprocess", "--sources", str(sources), "--out", str(out)])

    assert res.exit_code == 0
    assert "converted 0 / copied 0 / passthrough 2" in res.stdout
    assert "passthrough guide.docx (not converted; agent must read source format)" in res.stdout
    assert (
        "passthrough contract.json (not converted; agent must read source format)"
        in res.stdout
    )
    assert (out / "guide.docx").read_bytes() == b"docx bytes"
    assert (out / "contract.json").read_bytes() == b'{"paths":{}}'
