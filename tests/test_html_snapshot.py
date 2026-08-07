from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.html_snapshot import html_to_markdown


def test_table_becomes_markdown_pipe_table():
    """來源表格必須保留欄位結構，不可壓成單行(參數/型別會誤對齊)。"""
    html = (
        "<main><table><thead><tr><th>參數</th><th>必要</th></tr></thead>"
        "<tbody><tr><td>action</td><td>Y</td></tr>"
        "<tr><td>ts</td><td>N</td></tr></tbody></table></main>"
    )

    md = html_to_markdown(html)

    assert "| 參數 | 必要 |" in md
    assert "| --- | --- |" in md
    assert "| action | Y |" in md
    assert "| ts | N |" in md
    # 不可退化成壓平的單行
    assert "參數 必要 action Y ts N" not in md


def test_table_cell_pipe_is_escaped():
    html = "<main><table><tbody><tr><td>a|b</td><td>c</td></tr></tbody></table></main>"

    md = html_to_markdown(html)

    assert r"a\|b" in md


def test_pre_block_preserves_line_breaks():
    """程式碼區塊必須保留換行，否則多行 JSON/範例會被壓成一行。"""
    html = "<main><pre>line1\nline2\nline3</pre></main>"

    md = html_to_markdown(html)

    assert "```\nline1\nline2\nline3\n```" in md


def test_pre_with_span_lines_preserves_line_breaks():
    """語法高亮把每行包在 span、以換行文字節點分隔時仍須保留換行。"""
    html = "<main><pre><code><span>a: 1</span>\n<span>b: 2</span></code></pre></main>"

    md = html_to_markdown(html)

    assert "```\na: 1\nb: 2\n```" in md


def test_article_is_selected_when_main_is_absent():
    html = (
        "<p>Site announcement</p><article><h1>Transfer API</h1>"
        "<p>Authoritative documentation.</p></article><footer>Copyright</footer>"
    )

    md = html_to_markdown(html)

    assert md == "# Transfer API\n\nAuthoritative documentation.\n"


def test_body_is_selected_when_main_and_article_are_absent():
    html = "<p>Outside document</p><body><nav>Menu</nav><p>Transfer details</p></body>"

    md = html_to_markdown(html)

    assert md == "Transfer details\n"


def test_main_takes_precedence_over_article_and_body():
    html = "<body><article><p>Article details</p></article><main><p>Main details</p></main></body>"

    md = html_to_markdown(html)

    assert md == "Main details\n"


def test_nested_lists_keep_structure_and_repeated_source_items():
    html = (
        "<main><ol><li>Prepare<ul><li>Sign request</li><li>Sign request</li></ul>"
        "</li><li>Send request</li></ol></main>"
    )

    md = html_to_markdown(html)

    assert md == "1. Prepare\n  - Sign request\n  - Sign request\n2. Send request\n"


def test_nested_list_inside_a_wrapper_is_preserved():
    html = "<main><ul><li>Parent<div><ol><li>Child</li></ol></div></li></ul></main>"

    md = html_to_markdown(html)

    assert md == "- Parent\n  1. Child\n"


def test_repeated_list_blocks_are_not_globally_deduplicated():
    html = "<main><ul><li>Retry</li></ul><ul><li>Retry</li></ul></main>"

    md = html_to_markdown(html)

    assert md == "- Retry\n\n- Retry\n"


def test_repeated_paragraphs_keep_the_existing_single_rendering():
    html = "<main><p>Same text</p><p>Same text</p></main>"

    md = html_to_markdown(html)

    assert md == "Same text\n"


def test_labelled_anchor_keeps_its_document_provided_href():
    html = (
        '<main><p>Read <a href="../guide?lang=zh-TW#authentication">the guide</a> '
        'and <a href="https://docs.example.com/status">status</a>.<a href="/empty"></a></p></main>'
    )

    md = html_to_markdown(html)

    assert md == (
        "Read [the guide](../guide?lang=zh-TW#authentication) and "
        "[status](https://docs.example.com/status).\n"
    )


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
    assert provenance["raw_sha256"] == sha256(raw.read_bytes()).hexdigest()
