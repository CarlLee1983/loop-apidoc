from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop_apidoc.markdown_drafts.markdown import scan_markdown_drafts
from loop_apidoc.markdown_drafts.models import MarkdownDraftIndex


def test_write_scaffold_writes_complete_review_only_tree(tmp_path: Path):
    from loop_apidoc.extraction_scaffold.project import project_scaffold
    from loop_apidoc.extraction_scaffold.write import write_scaffold

    source = "## GET /ping\n"
    bundle = project_scaffold(
        MarkdownDraftIndex(sources=(scan_markdown_drafts("api.md", source),)),
        {"api.md": source},
        "sources",
    )
    output = tmp_path / "scaffold"

    write_scaffold(bundle, output)

    assert json.loads((output / "inventory.json").read_text(encoding="utf-8"))["endpoints"][0]["path"] == "/ping"
    assert json.loads((output / "endpoints" / "ep00.json").read_text(encoding="utf-8"))["method"] == "GET"
    assert json.loads((output / "scaffold-report.json").read_text(encoding="utf-8"))["authoritative"] is False
    readme = (output / "README.md").read_text(encoding="utf-8")
    assert "not the --extraction argument" in readme
    assert "copy" in readme.lower()


def test_write_scaffold_refuses_nonempty_output_without_changing_it(tmp_path: Path):
    from loop_apidoc.extraction_scaffold.project import project_scaffold
    from loop_apidoc.extraction_scaffold.write import ExtractionScaffoldInputError, write_scaffold

    bundle = project_scaffold(MarkdownDraftIndex(), {}, "sources")
    output = tmp_path / "scaffold"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ExtractionScaffoldInputError, match="output already exists"):
        write_scaffold(bundle, output)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_write_scaffold_replaces_an_empty_output_directory_after_finishing_tree(tmp_path: Path):
    from loop_apidoc.extraction_scaffold.project import project_scaffold
    from loop_apidoc.extraction_scaffold.write import write_scaffold

    output = tmp_path / "scaffold"
    output.mkdir()

    write_scaffold(project_scaffold(MarkdownDraftIndex(), {}, "sources"), output)

    assert (output / "README.md").exists()
