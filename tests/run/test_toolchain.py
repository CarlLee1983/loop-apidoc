from __future__ import annotations

import json
from pathlib import Path

from loop_apidoc import __version__
from loop_apidoc.run.toolchain import (
    EXTRACTION_CONTRACT_VERSION,
    build_toolchain,
    read_skill_version,
)


def _plugin_root(tmp_path: Path, version: str = "9.9.9") -> Path:
    manifest_dir = tmp_path / ".claude-plugin"
    manifest_dir.mkdir()
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": "loop-apidoc", "version": version}), encoding="utf-8"
    )
    return tmp_path


def test_build_toolchain_records_cli_and_contract_versions() -> None:
    toolchain = build_toolchain()
    assert toolchain.cli_version == __version__
    assert toolchain.extraction_contract_version == EXTRACTION_CONTRACT_VERSION


def test_build_toolchain_model_defaults_to_none_and_is_never_guessed() -> None:
    assert build_toolchain().model is None
    assert build_toolchain(model="claude-opus-4-8").model == "claude-opus-4-8"


def test_read_skill_version_reads_plugin_manifest(tmp_path) -> None:
    assert read_skill_version(_plugin_root(tmp_path)) == "9.9.9"


def test_read_skill_version_is_none_when_unresolvable(tmp_path) -> None:
    assert read_skill_version(tmp_path / "nope") is None


def test_read_skill_version_is_none_when_manifest_malformed(tmp_path) -> None:
    root = tmp_path
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text("{ not json", encoding="utf-8")
    assert read_skill_version(root) is None


def test_read_skill_version_is_none_when_version_missing(tmp_path) -> None:
    root = tmp_path
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "loop-apidoc"}), encoding="utf-8"
    )
    assert read_skill_version(root) is None


def test_build_toolchain_prefers_claude_plugin_root_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(_plugin_root(tmp_path, "1.2.3")))
    assert build_toolchain().skill_version == "1.2.3"


def test_build_toolchain_falls_back_to_repo_manifest(monkeypatch) -> None:
    """未設 CLAUDE_PLUGIN_ROOT 時退回套件所在 repo 的 plugin.json。"""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    assert build_toolchain().skill_version is not None
