# Continuous Correction Quality Gate — Design

**Date:** 2026-06-29
**Status:** Approved for planning
**Topic:** Repo-local mechanism for continuous correction, regression capture, and
quality-gated improvement of the source-grounded API documentation pipeline.

## Motivation

`loop-apidoc` now has a mature deterministic tail: CLI commands work, the full
test suite passes, benchmark cases exercise real payment/API documentation shapes,
and malformed extraction inputs fail closed before producing mixed output. That is
enough for delivery, but long-term reliability needs a repeatable correction loop:
when a new failure appears, the project should capture it as an executable
regression, fix it once, and prevent the same class of issue from returning.

The current repository already has the main ingredients:

- CI runs `uv sync --dev`, `uv run ruff check .`, and `uv run pytest`.
- `tests/test_benchmarks.py` protects the committed benchmark set and runs full
  case assertions wherever gitignored local sources are present.
- `docs/RELEASE_CHECKLIST.md` documents manual local-source and artifact review
  gates.
- `docs/PIPELINE_FOLLOWUPS.md` records prior pipeline risks and completed fixes.

The missing piece is a single, executable quality gate plus a written correction
protocol that turns every discovered defect into durable evidence.

## Goals

1. Add a repo-local command that runs the checks a maintainer should run before
   claiming a pipeline change is ready.
2. Make benchmark-source availability explicit: fail in strict local mode when
   benchmark cases are skipped; tolerate skips in CI where copyrighted/operator
   sources are intentionally absent.
3. Include adversarial CLI smoke checks that exercise fail-loudly and fail-closed
   behavior outside normal unit tests.
4. Document the correction loop: failure record, regression fixture, fix,
   quality gate, and follow-up capture.
5. Keep the mechanism small, dependency-free, and compatible with the current
   Python/uv workflow.

## Non-Goals

- No external dashboard, database, scheduled service, or new dependency.
- No LLM/subagent extraction automation inside the quality gate.
- No attempt to make gitignored benchmark source files available in CI.
- No replacement for the release checklist; the gate complements it and links
  to the local artifact review steps.

## Proposed Shape

Add a script at `scripts/quality_gate.py` and document it in
`docs/CORRECTION_LOOP.md`.

The command supports two modes:

```bash
uv run python scripts/quality_gate.py
uv run python scripts/quality_gate.py --strict-local
```

Default mode is CI-safe. It runs deterministic checks and accepts benchmark skips
caused by missing local sources.

Strict local mode is maintainer/release mode. It requires the benchmark sources
to be present and fails if benchmark case tests skip instead of executing. This
is the mode to run before release, before large pipeline changes, or after adding
or changing benchmark fixtures.

## Quality Gate Steps

The script runs these commands in order and stops on the first failure:

1. `uv run ruff check .`
2. `uv run pytest`
3. `uv run pytest tests/test_benchmarks.py -q`
4. Adversarial CLI smoke harness:
   - minimal valid `assemble --json` fixture returns parseable JSON and creates a
     run directory;
   - malformed `inventory.json` exits `2` before creating output;
   - localized schema field keys are rejected at the extraction boundary;
   - non-object `integration.json` exits `2`;
   - incomplete run directory fails `validate` with an `OUTPUT_MISMATCH` report;
   - symlink escaping the source root is recorded as unreadable without hashing
     the external target.
5. Cleanup check: temporary harness directories are removed.

Strict local mode adds:

- parse benchmark test output and fail if any benchmark case is skipped;
- confirm all required benchmark cases have `sources/` with at least one file.

The gate intentionally does not inspect production credentials, make network
calls, or mutate tracked files.

## Correction Loop Protocol

Every non-trivial defect follows this loop:

1. Record the failure in the most local durable place:
   - a new regression test for code-level defects;
   - a benchmark fixture update for document-shape defects;
   - `docs/PIPELINE_FOLLOWUPS.md` for broader improvement items.
2. Reproduce the failure with a focused command and capture the expected failing
   signal.
3. Fix the smallest responsible boundary.
4. Run the focused test, then `uv run python scripts/quality_gate.py`.
5. If the fix depends on local benchmark sources or release judgment, also run
   `uv run python scripts/quality_gate.py --strict-local`.
6. Update notes, benchmark expectation files, or follow-up documentation so the
   reason for the fix is visible to future maintainers.

The invariant is: no correction is considered complete without an executable
regression or an explicit documented reason that it cannot be made executable.

## CLI UX

Output should be terse and evidence-oriented:

```text
[quality-gate] ruff: uv run ruff check .
[quality-gate] PASS ruff
[quality-gate] pytest: uv run pytest
[quality-gate] PASS pytest
[quality-gate] benchmarks: uv run pytest tests/test_benchmarks.py -q
[quality-gate] PASS benchmarks
[quality-gate] adversarial CLI smoke
[quality-gate] PASS adversarial CLI smoke (6 scenarios)
[quality-gate] COMPLETE
```

On failure, print the failing command, exit code, and captured stdout/stderr
excerpt. The script exits non-zero immediately.

## File Responsibilities

- `scripts/quality_gate.py`: executable gate orchestration and temporary
  adversarial harness. It owns command execution, strict-local benchmark skip
  checks, and cleanup.
- `docs/CORRECTION_LOOP.md`: human workflow for turning failures into permanent
  regression coverage and follow-up records.
- `docs/RELEASE_CHECKLIST.md`: link to the new strict-local command in the
  existing release flow.
- `.github/workflows/ci.yml`: optional small update to run the quality gate in
  CI-safe default mode instead of manually listing ruff/pytest, if this proves
  cleaner after implementation.

## Testing Strategy

Implementation should be TDD:

- Add unit tests for quality-gate helper functions using a fake command runner.
- Add tests for benchmark skip detection in strict-local mode.
- Add tests for adversarial smoke scenario result classification without running
  the full expensive command set.
- Keep one integration-level test or direct manual verification that the script
  runs successfully in the current repository.

The script itself can invoke the expensive full suite, but helper functions
should be testable without recursively running pytest from pytest.

## Risks and Mitigations

- **Recursive test execution in tests.** Avoid testing the full script by running
  pytest from pytest. Unit-test helpers with fake runners and reserve real script
  execution for manual verification or CI.
- **Benchmark skips in CI.** Default mode permits skips; strict-local mode fails
  on skips. This preserves CI practicality while making release confidence
  explicit.
- **Harness debris.** Use `tempfile.TemporaryDirectory` and a final cleanup check.
- **Slow local runs.** The script is a quality gate, not an inner-loop command.
  Developers can still run focused tests while iterating.

## Acceptance

- `uv run python scripts/quality_gate.py` passes in the normal repository state.
- `uv run python scripts/quality_gate.py --strict-local` passes on a machine with
  all benchmark sources present and fails clearly if a required source directory
  is missing.
- Adversarial smoke scenarios cover the existing fail-loudly and fail-closed
  behavior observed during the June 29 QA pass.
- `docs/CORRECTION_LOOP.md` gives maintainers a concise rule for capturing new
  defects as regression evidence.
- No product pipeline behavior changes are required by this design.
