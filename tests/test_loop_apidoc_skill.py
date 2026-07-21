from __future__ import annotations

from pathlib import Path


def test_skill_requires_copying_scaffold_before_verification():
    text = Path("skills/loop-apidoc/SKILL.md").read_text(encoding="utf-8")

    assert "scaffold-extraction --sources" in text
    assert "<WORK>/scaffold" in text
    assert "`--extraction` argument" in text
    assert "Copy its `inventory.json` and `endpoints/` files into `<WORK>/`" in text


def test_skill_recommends_inventory_scaffolding_for_large_sources():
    text = Path("skills/loop-apidoc/SKILL.md").read_text(encoding="utf-8")

    assert "100KB" in text
    assert "30+ endpoints" in text
    assert "complete endpoint inventory" in text
