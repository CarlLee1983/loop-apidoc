from __future__ import annotations

from pathlib import Path


def test_architecture_docs_name_the_new_product_boundary():
    assert "Evidence Ledger" in Path("docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "Canonical API Contract IR" in Path("README.en.md").read_text(
        encoding="utf-8"
    )
    assert "Runtime Adapter" in Path("README.md").read_text(encoding="utf-8")


def test_architecture_docs_keep_source_risk_before_model_reading():
    architecture = Path("docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    readme = Path("README.en.md").read_text(encoding="utf-8")

    inspect_stage = architecture.index('SR["inspect-source-risk')
    quality_review = architecture.index('QR["agent source-quality review')

    assert inspect_stage < quality_review
    assert "pre-model `inspect-source-risk` gate" in readme
    assert "never the matched payload" in readme


def test_claude_guidance_refers_to_the_canonical_agents_file():
    claude = Path("CLAUDE.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in claude
    assert "canonical" in claude.lower()
