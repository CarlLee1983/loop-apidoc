from __future__ import annotations

from pathlib import Path


def test_architecture_docs_name_the_new_product_boundary():
    assert "Evidence Ledger" in Path("docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "Canonical API Contract IR" in Path("README.en.md").read_text(
        encoding="utf-8"
    )
    assert "Runtime Adapter" in Path("README.md").read_text(encoding="utf-8")


def test_claude_guidance_refers_to_the_canonical_agents_file():
    claude = Path("CLAUDE.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in claude
    assert "canonical" in claude.lower()
