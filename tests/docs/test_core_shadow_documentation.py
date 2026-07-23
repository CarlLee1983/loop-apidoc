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
)


@pytest.mark.parametrize("path", REQUIRED_DOCS)
def test_shadow_mode_and_artifact_directory_are_documented(path: str):
    text = Path(path).read_text(encoding="utf-8")

    assert "--architecture-mode shadow" in text
    assert "core/" in text


def test_agent_guides_name_shadow_report_as_file_io_exit():
    assert "shadow/report.py" in Path("AGENTS.md").read_text(encoding="utf-8")


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


@pytest.mark.parametrize(
    "path",
    [
        "README.en.md",
        "README.md",
        "docs/ARCHITECTURE.md",
        "docs/operator-manual.en.html",
        "docs/operator-manual.html",
    ],
)
def test_shadow_docs_explain_semantic_support_and_degraded_legacy_refs(path: str):
    text = Path(path).read_text(encoding="utf-8")
    assert "explicit_support" in text
    assert "insufficient" in text
    assert "relationships.json" in text
    assert "legacy" in text.lower()


def test_agent_guides_keep_fragment_io_inventory_aligned():
    text = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "adapters/fragments.py" in text
    assert "shadow/report.py" in text


def test_canonical_design_decisions_cover_semantic_evidence():
    design = Path("docs/DESIGN_DECISIONS.md").read_text(encoding="utf-8")
    checklist = Path("docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

    assert "explicit_support" in design
    assert "insufficient" in design
    assert "model-independent Core" in design
    assert "13 required cases" in checklist
    assert "13 benchmark cases" in checklist
