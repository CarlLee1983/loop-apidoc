# tests/test_plugin_manifest.py
from __future__ import annotations

import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_json_valid():
    data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    assert data["name"] == "loop-apidoc"
    assert "description" in data


def test_release_versions_are_synced_at_0_9_1():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    init = (ROOT / "loop_apidoc" / "__init__.py").read_text("utf-8")

    assert project["project"]["version"] == "0.9.1"
    assert plugin["version"] == "0.9.1"
    assert '__version__ = "0.9.1"' in init


def test_marketplace_lists_plugin():
    data = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
    names = [p["name"] for p in data["plugins"]]
    assert "loop-apidoc" in names


def test_skill_has_frontmatter_and_assemble_call():
    text = (ROOT / "skills" / "loop-apidoc" / "SKILL.md").read_text("utf-8")
    assert text.startswith("---")
    assert "name: loop-apidoc" in text
    # 可攜形式:CLI 以 <APIDOC> 佔位符呼叫(Claude plugin / Codex 雙棲)
    assert "<APIDOC> assemble" in text
    # 仍須說明 plugin 端的 $CLAUDE_PLUGIN_ROOT 解析規則
    assert "CLAUDE_PLUGIN_ROOT" in text
    # 全域指令 fallback(Codex 端)必須在 CLI invocation 規則中出現
    assert "loop-apidoc" in text


def test_skill_references_real_issue_fields():
    text = (ROOT / "skills" / "loop-apidoc" / "SKILL.md").read_text("utf-8")
    assert "report.issues" in text
    assert "location" in text and "suggested_fix" in text
    # 不得引用不存在的 Issue 欄位(避免誤導修正迴圈)
    assert "`area`/`detail`" not in text


def test_skill_has_model_neutral_orchestration_contract():
    text = (ROOT / "skills" / "loop-apidoc" / "SKILL.md").read_text("utf-8")
    assert "model-neutral" in text
    assert "reference/model-orchestration.md" in text
    assert (ROOT / "skills" / "loop-apidoc" / "reference" / "model-orchestration.md").is_file()


def test_skill_requires_an_output_level_checkpoint_with_minimal_default():
    text = (ROOT / "skills" / "loop-apidoc" / "SKILL.md").read_text("utf-8")

    assert "Output-level checkpoint" in text
    assert "minimal (default)" in text
    assert "review" in text
    assert "handoff" in text
    assert "full" in text
    assert "do not open, summarize, or pass" in text
