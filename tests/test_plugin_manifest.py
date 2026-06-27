# tests/test_plugin_manifest.py
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_json_valid():
    data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    assert data["name"] == "loop-apidoc"
    assert "description" in data


def test_marketplace_lists_plugin():
    data = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
    names = [p["name"] for p in data["plugins"]]
    assert "loop-apidoc" in names


def test_skill_has_frontmatter_and_assemble_call():
    text = (ROOT / "skills" / "loop-apidoc" / "SKILL.md").read_text("utf-8")
    assert text.startswith("---")
    assert "name: loop-apidoc" in text
    assert "loop-apidoc assemble" in text
    assert "CLAUDE_PLUGIN_ROOT" in text
