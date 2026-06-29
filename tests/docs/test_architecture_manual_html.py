from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "docs" / "architecture-manual.html"
MARKDOWN = ROOT / "docs" / "ARCHITECTURE.md"


def test_architecture_manual_uses_native_architecture_map():
    html = HTML.read_text(encoding="utf-8")

    assert 'class="architecture-map"' in html
    assert "const moduleDataset = {" in html
    assert "function selectModule(key)" in html
    assert 'class="module-card active"' in html
    assert 'id="module-detail-content"' in html


def test_architecture_manual_does_not_load_mermaid_runtime():
    html = HTML.read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net/npm/mermaid" not in html
    assert "mermaid.initialize" not in html
    assert '<div class="mermaid">' not in html


def test_architecture_markdown_keeps_mermaid_fallback():
    markdown = MARKDOWN.read_text(encoding="utf-8")

    assert "```mermaid" in markdown
    assert "flowchart TD" in markdown
