from __future__ import annotations

from pathlib import Path


CANONICAL = Path("docs/BENCHMARK_VALIDATION_PLAN.md")
SUPPORTING_DOCS = (
    Path("README.en.md"),
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("docs/RELEASE_CHECKLIST.md"),
    Path("docs/operator-manual.html"),
    Path("docs/onboarding.html"),
)
AGENT_SECTION_MARKER = "## Benchmark harness contract"


def test_canonical_benchmark_contract_names_four_layers_and_thirteen_cases():
    text = CANONICAL.read_text(encoding="utf-8")

    for layer in (
        "Committed fixture inventory",
        "Discovery guard",
        "Source-backed execution",
        "Strict-local preflight",
    ):
        assert layer in text
    assert "thirteen unique cases" in text
    assert "5-8" not in text
    assert "5–8" not in text
    assert "11 case" not in text


def test_canonical_distinguishes_skip_from_pass_and_documents_case_addition():
    text = CANONICAL.read_text(encoding="utf-8")

    assert "A skip is not a pass" in text
    assert "REQUIRED_BENCHMARK_CASES" in text
    assert "test_required_benchmark_cases_match_committed_cases" in text
    assert "Never substitute a newer document" in text


def test_supporting_docs_link_to_canonical_benchmark_contract():
    for path in SUPPORTING_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "BENCHMARK_VALIDATION_PLAN.md" in text, path


def test_release_checklist_distinguishes_unique_cases_from_pytest_items():
    text = Path("docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

    assert "unique fixture directories" in text
    assert "pytest test items" in text


def test_benchmark_html_navigation_targets_exist():
    expected = {
        Path("docs/operator-manual.html"): "benchmark-quality-gate",
        Path("docs/onboarding.html"): "benchmark-harness",
    }

    for path, anchor in expected.items():
        text = path.read_text(encoding="utf-8")
        assert f'href="#{anchor}"' in text, path
        assert f'id="{anchor}"' in text, path


def _agent_benchmark_section(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8")
    assert text.count(AGENT_SECTION_MARKER) == 1
    return text.split(AGENT_SECTION_MARKER, 1)[1].strip()


def test_agent_benchmark_contract_sections_are_identical():
    agents = _agent_benchmark_section("AGENTS.md")
    claude = _agent_benchmark_section("CLAUDE.md")

    assert agents == claude
    assert "REQUIRED_BENCHMARK_CASES" in agents
    assert "A skipped case has not passed" in agents
    assert "--strict-local" in agents
