# Benchmark Harness Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give maintainers, contributors, operators, and agents one accurate mental model for the thirteen-case benchmark harness.

**Architecture:** Make `docs/BENCHMARK_VALIDATION_PLAN.md` the English-primary canonical contract with a zh-TW summary. Keep supporting documents audience-specific and link them to the canonical document; enforce the key cross-document claims with a focused documentation test.

**Tech Stack:** Markdown, static HTML, pytest, Python `pathlib`, Ruff.

## Global Constraints

- This is a docs-only correction on `main`; do not change benchmark discovery, execution, skip handling, strict-local code, fixtures, source snapshots, CI, release commands, version metadata, or the published `v0.16.0` tag.
- `Committed`, `discovered`, `skipped`, `passed`, and `strict-local passed` must retain the exact distinct meanings approved in the design.
- The committed fixture inventory contains exactly thirteen unique cases.
- Missing historical sources never authorize newer, synthetic, or error-page substitutes.
- `AGENTS.md` and `CLAUDE.md` must contain byte-identical benchmark-contract sections.

---

### Task 1: Lock the documentation contract

**Files:**
- Create: `tests/docs/test_benchmark_harness_documentation.py`

**Interfaces:**
- Consumes: repository documentation as UTF-8 text.
- Produces: pytest assertions for canonical terminology, audience-document links, HTML anchors, and identical agent-guide sections.

- [ ] **Step 1: Write the failing documentation tests**

```python
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


def test_canonical_benchmark_contract_names_four_layers_and_thirteen_cases():
    text = CANONICAL.read_text(encoding="utf-8")
    assert "Committed fixture inventory" in text
    assert "Discovery guard" in text
    assert "Source-backed execution" in text
    assert "Strict-local preflight" in text
    assert "thirteen" in text.lower()
    assert "5-8" not in text
    assert "5–8" not in text


def test_supporting_docs_link_to_canonical_benchmark_contract():
    for path in SUPPORTING_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "BENCHMARK_VALIDATION_PLAN.md" in text


def test_agent_benchmark_contract_sections_are_identical():
    marker = "## Benchmark harness contract"
    agents = Path("AGENTS.md").read_text(encoding="utf-8").split(marker, 1)[1]
    claude = Path("CLAUDE.md").read_text(encoding="utf-8").split(marker, 1)[1]
    assert agents == claude
```

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest tests/docs/test_benchmark_harness_documentation.py -q`

Expected: FAIL because the canonical four-layer headings, links, HTML anchors, and agent sections are absent.

- [ ] **Step 3: Commit boundary**

Do not commit yet; the user requested direct implementation in the current checkout, so preserve the final diff for review.

### Task 2: Rewrite the canonical benchmark contract

**Files:**
- Modify: `docs/BENCHMARK_VALIDATION_PLAN.md`

**Interfaces:**
- Consumes: fixture identity in `tests/test_benchmarks.py` and required inventory in `scripts/quality_gate.py`.
- Produces: the authoritative English-primary harness contract and zh-TW summary.

- [ ] **Step 1: Replace historical planning language**

Write sections for purpose, the four harness layers, all thirteen case IDs, terminology, commands, adding a case, unavailable-source fallback, and a zh-TW summary. State explicitly:

```markdown
A skipped case has been discovered, but its source-backed assertions have not passed.
```

- [ ] **Step 2: Verify stale targets are gone**

Run: `rg -n "5-8|5–8|11 case|11 cases" docs/BENCHMARK_VALIDATION_PLAN.md`

Expected: no matches.

### Task 3: Align contributor and release-facing Markdown

**Files:**
- Modify: `README.en.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/RELEASE_CHECKLIST.md`

**Interfaces:**
- Consumes: canonical terminology and four-layer command mapping.
- Produces: qualified evidence claims, intentional inventory-update workflow, and release checks that distinguish unique cases from pytest items.

- [ ] **Step 1: Qualify README evidence claims**

Add concise English and zh-TW notes explaining that CI proves discovery/parity while source-backed pass evidence requires original snapshots and strict-local execution.

- [ ] **Step 2: Document contributor workflow**

Document the fixture identity rule, intentional update of `REQUIRED_BENCHMARK_CASES`, exact-parity test, and the rule that CI skips are not passes.

- [ ] **Step 3: Map release checks to layers**

Use a four-row command/guarantee table and say that thirteen counts unique fixture directories, not parametrized pytest items.

### Task 4: Align operator, onboarding, and agent guidance

**Files:**
- Modify: `docs/operator-manual.html`
- Modify: `docs/onboarding.html`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: canonical contract and existing HTML navigation structures.
- Produces: audience-specific operational guidance, valid anchors, and identical agent rules.

- [ ] **Step 1: Add operator quality-gate section**

Add `id="benchmark-quality-gate"` to the manual, link it from navigation, and document CI-safe versus strict-local commands, prerequisites, failure behavior, and unavailable-source fallback.

- [ ] **Step 2: Add onboarding architecture section**

Add `id="benchmark-harness"` to the onboarding page, link it from navigation, and explain the four-layer model plus gitignored source snapshots.

- [ ] **Step 3: Add identical agent contract sections**

Append the same `## Benchmark harness contract` block to `AGENTS.md` and `CLAUDE.md`, including fixture identity, exact parity, skip semantics, strict-local semantics, and the canonical link.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `uv run pytest tests/docs/test_benchmark_harness_documentation.py -q`

Expected: all tests pass.

### Task 5: Verify the complete documentation correction

**Files:**
- Review: all files changed by Tasks 1–4.

**Interfaces:**
- Consumes: completed documentation diff.
- Produces: fresh evidence that docs, quality gate behavior, lint, whitespace, links, and agent-guide alignment satisfy the approved design.

- [ ] **Step 1: Run required automated checks**

```bash
uv run pytest tests/docs -q
uv run pytest tests/test_quality_gate.py -q
uv run ruff check .
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 2: Run repository consistency searches**

```bash
rg -n "5-8|5–8|11 case|11 cases" docs/BENCHMARK_VALIDATION_PLAN.md
rg -n "BENCHMARK_VALIDATION_PLAN.md" README.en.md README.md CONTRIBUTING.md docs/RELEASE_CHECKLIST.md docs/operator-manual.html docs/onboarding.html AGENTS.md CLAUDE.md
```

Expected: the stale search returns no matches; every required supporting document contains the canonical link.

- [ ] **Step 3: Inspect HTML anchors and links**

Confirm `href="#benchmark-quality-gate"` matches `id="benchmark-quality-gate"` and `href="#benchmark-harness"` matches `id="benchmark-harness"`.

- [ ] **Step 4: Review the final diff against every design requirement**

Confirm no excluded document, fixture, source snapshot, code path, CI file, version file, or historical release artifact changed.
