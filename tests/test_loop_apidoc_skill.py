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


def test_extraction_schema_rules_multi_mode_endpoints_into_one_operation():
    """來源用同一個 method+path 描述多個模式(多錢包、多金流產品)時,擷取階段就要
    知道只能寫成一個 operation —— 否則 subagent 寫成兩檔、到跨檔閘門才被擋。"""
    text = Path("skills/loop-apidoc/reference/extraction-schemas.md").read_text(
        encoding="utf-8")

    assert "exactly one operation per" in text
    assert "`one_of` union on the body field" in text
    # `server` 不是第二個身份 —— 誤導成這樣會直接撞上 source-conflict 閘門。
    assert "`server` does not help" in text
