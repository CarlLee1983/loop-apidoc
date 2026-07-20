# Benchmark Harness Documentation Design

**Date:** 2026-07-20
**Status:** Approved for implementation planning

## Context

The 0.16.0 release-blocker work corrected `REQUIRED_BENCHMARK_CASES` so the
strict-local preflight covers all thirteen committed benchmark fixtures. The code and
release notes describe that fix, but the teaching and operator documentation does not
yet present one consistent mental model for the harness.

The current documentation mixes four different guarantees:

1. a benchmark fixture is committed;
2. the harness discovers the fixture;
3. source-backed assertions execute for the fixture;
4. strict-local release validation completes without skips.

Those guarantees are related but not interchangeable. In particular, source-backed
benchmark tests skip when their operator-provided, gitignored source snapshot is absent.
A discovered or skipped case has not passed source-backed revalidation.

## Decision

### Canonical documentation

`docs/BENCHMARK_VALIDATION_PLAN.md` will become the canonical description of the
benchmark harness. It will be English-primary with a Traditional-Chinese supporting
summary, matching the repository documentation policy.

The canonical document will define the four layers of the harness:

1. **Committed fixture inventory** — a directory under `benchmarks/` is a harness case
   when it contains both `extraction/inventory.json` and
   `expected/validation.expect.json`.
2. **Discovery guard** — deterministic tests confirm that committed fixtures remain
   discoverable even when their source snapshots are absent, so the benchmark suite
   cannot silently become empty.
3. **Source-backed execution** — assemble and artifact assertions execute only when the
   original, dated `benchmarks/<case>/sources/` snapshot is present. Absence produces a
   skip, not a pass.
4. **Strict-local preflight** — `scripts/quality_gate.py --strict-local` requires exact
   parity between the required inventory and committed fixtures, requires a non-empty
   source directory for every required case, and rejects any benchmark run that reports
   skips.

The document will replace the historical five-to-eight-case target with the current
thirteen-case inventory and explain the intentional workflow for adding a case.

### Supporting documents

Supporting documents will contain only the detail needed by their audience and link
back to the canonical document:

- `README.en.md` and `README.md` will qualify the benchmark evidence claim with the
  difference between CI-safe discovery/parity and source-backed strict-local execution.
- `CONTRIBUTING.md` will explain that adding a committed fixture requires an intentional
  required-inventory update and that CI skips do not constitute a benchmark pass.
- `docs/RELEASE_CHECKLIST.md` will map commands to the four harness layers and clarify
  that thirteen is the unique case count, not the number of pytest test items.
- `docs/operator-manual.html` will document CI-safe and strict-local quality-gate
  operation, prerequisites, and expected failure behavior.
- `docs/onboarding.html` will explain the harness architecture and the gitignored source
  snapshot model for new engineers.
- `AGENTS.md` and `CLAUDE.md` will receive identical agent-facing harness-contract
  sections.

`docs/index.html`, `docs/introduction.html`, and `docs/architecture-manual.html` do not
currently make operational harness claims, so they will remain unchanged. Historical
release notes and the published `v0.16.0` tag will also remain unchanged.

## Terminology and failure semantics

All updated documents will use these meanings consistently:

- **Committed** means the fixture identity files exist in the repository.
- **Discovered** means the harness enumerated the fixture.
- **Skipped** means source-backed assertions did not execute because the required source
  snapshot was unavailable.
- **Passed** means the applicable assertions executed and passed.
- **Strict-local passed** means every required case had sources, all source-backed
  benchmark checks ran, and no skip was reported.

Missing historical sources do not authorize substituting a newer document, an error
page, or a synthetic fixture. The documented fallback remains deterministic CI checks
plus a targeted source-backed spot-check, with the unavailable snapshot recorded.

## Adding a benchmark case

The canonical workflow will require:

1. add the case's committed extraction and expected declarations;
2. confirm the directory satisfies the fixture identity rule;
3. update the explicit required inventory intentionally;
4. run the exact-parity test;
5. run source-backed assertions with the original source snapshot when available;
6. run strict-local only on a machine that holds all required snapshots.

The exact-parity regression ensures that adding a committed fixture without updating
the required inventory fails CI instead of silently widening only one side of the
contract.

## Verification

The documentation change will be verified with:

- `uv run pytest tests/docs -q`;
- `uv run pytest tests/test_quality_gate.py -q`;
- `uv run ruff check .`;
- `git diff --check`;
- a comparison confirming the new `AGENTS.md` and `CLAUDE.md` harness sections are
  identical;
- repository searches confirming the canonical document no longer contains the stale
  five-to-eight-case target or language that equates CI skips with benchmark success;
- inspection of the edited HTML headings, anchors, and internal links.

## Release boundary

This is a docs-only correction on `main`. It will not move or recreate `v0.16.0`, change
package version metadata, or publish `0.16.1`.

## Non-goals

- Changing benchmark discovery, execution, skip handling, or strict-local code.
- Adding, removing, or regenerating benchmark fixtures or source snapshots.
- Changing CI configuration or release commands.
- Rewriting unrelated teaching, landing, or architecture content.
