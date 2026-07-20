from __future__ import annotations

from pathlib import Path


def test_architecture_docs_name_the_new_product_boundary():
    assert "Evidence Ledger" in Path("docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "Canonical API Contract IR" in Path("README.en.md").read_text(
        encoding="utf-8"
    )
    assert "Runtime Adapter" in Path("README.md").read_text(encoding="utf-8")


def test_agent_guidance_stays_synchronized():
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    claude = Path("CLAUDE.md").read_text(encoding="utf-8")
    assert (
        agents[agents.index("## What this is") :]
        == claude[claude.index("## What this is") :]
    )
