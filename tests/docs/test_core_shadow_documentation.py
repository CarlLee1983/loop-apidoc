from __future__ import annotations

from pathlib import Path

import pytest


REQUIRED_DOCS = (
    "README.en.md",
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/introduction.en.html",
    "docs/introduction.html",
    "docs/onboarding.en.html",
    "docs/onboarding.html",
    "docs/operator-manual.en.html",
    "docs/operator-manual.html",
    "docs/architecture-manual.en.html",
    "docs/architecture-manual.html",
    "skills/loop-apidoc/reference/assemble-and-correction.md",
    "AGENTS.md",
    "CLAUDE.md",
)


@pytest.mark.parametrize("path", REQUIRED_DOCS)
def test_shadow_mode_and_artifact_directory_are_documented(path: str):
    text = Path(path).read_text(encoding="utf-8")

    assert "--architecture-mode shadow" in text
    assert "core/" in text


def test_agent_guides_name_shadow_report_as_file_io_exit():
    for path in ("AGENTS.md", "CLAUDE.md"):
        text = Path(path).read_text(encoding="utf-8")
        assert "shadow/report.py" in text


@pytest.mark.parametrize("path", ["README.en.md", "README.md"])
def test_readme_assemble_synopsis_includes_architecture_mode(path: str):
    text = Path(path).read_text(encoding="utf-8")
    assert "[--architecture-mode legacy|shadow]" in text


@pytest.mark.parametrize(
    "path",
    [
        "README.en.md",
        "README.md",
        "docs/operator-manual.en.html",
        "docs/operator-manual.html",
    ],
)
def test_output_tree_lists_score_and_complete_core_artifacts(path: str):
    text = Path(path).read_text(encoding="utf-8")
    assert "score/score.json" in text or "├── score.json" in text
    for filename in (
        "source-set.json",
        "evidence.json",
        "runtime-result.json",
        "claims.json",
        "contract.json",
        "decision.json",
        "workflow.json",
        "events.json",
        "comparison.json",
    ):
        assert filename in text


@pytest.mark.parametrize(
    "path",
    [
        "docs/ARCHITECTURE.md",
        "docs/architecture-manual.en.html",
        "docs/architecture-manual.html",
    ],
)
def test_architecture_file_io_inventory_names_shadow_report(path: str):
    assert "shadow/report.py" in Path(path).read_text(encoding="utf-8")
