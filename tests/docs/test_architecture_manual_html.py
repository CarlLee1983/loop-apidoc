from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "docs" / "architecture-manual.html"
HTML_EN = ROOT / "docs" / "architecture-manual.en.html"
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


def test_architecture_manual_documents_source_risk_in_both_languages():
    for path in (HTML_EN, HTML):
        html = path.read_text(encoding="utf-8")

        assert '<div class="command-chip">inspect-source-risk</div>' in html
        assert 'data-module="source-risk"' in html
        assert "load_verified_source_risk_report" in html
        assert "source-risk-report.zh-TW.md" in html


def test_architecture_markdown_keeps_mermaid_fallback():
    markdown = MARKDOWN.read_text(encoding="utf-8")

    assert "```mermaid" in markdown
    assert "flowchart TD" in markdown
