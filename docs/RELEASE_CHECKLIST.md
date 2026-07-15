# Release Checklist

Run before tagging a release or merging a significant pipeline change. CI
(`.github/workflows/ci.yml`) covers the deterministic checks automatically; the
items marked **(local sources)** can only run on a machine that has the
operator-provided, gitignored `benchmarks/<case>/sources/` present.

## Automated in CI

- [ ] `uv sync --dev` resolves cleanly.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run pytest --cov=loop_apidoc` passes with total coverage at or above 95% — unit + integration + the benchmark discovery guard.
  - CI fails on any test failure.
  - CI fails if benchmark case discovery becomes empty or loses a required case
    (`test_benchmark_harness_discovers_cases` asserts the 10 required cases are
    still discovered).
- [ ] `uv run python scripts/quality_gate.py` passes in CI-safe mode.

## Requires local benchmark sources (local sources)

The benchmark *case* assertions in `tests/test_benchmarks.py`
(`test_benchmark_case`) **SKIP** when `benchmarks/<case>/sources/` is absent, so
CI does not exercise them. Run them where the sources exist:

- [ ] `uv run pytest tests/test_benchmarks.py` with sources present — every
  committed case runs (no skips) and matches its `expected/` declaration.
- [ ] Confirm no case is silently skipped: the run reports 10 benchmark cases
  executed, not skipped.
- [ ] `uv run python scripts/quality_gate.py --strict-local` passes — no
  benchmark source directory is missing and no benchmark case is skipped.

## Manual spot-check (local sources)

Generate one representative run and eyeball the products (validation PASS does
**not** guarantee good output — read the artifacts):

- [ ] `openapi.yaml` — OpenAPI 3.1, paths/webhooks/schemas/securitySchemes as expected.
- [ ] `api-guide.zh-TW.md` — readable, complete, no placeholder leakage.
- [ ] `review.html` — open it in a browser; metrics, endpoint/schema tables, and gap list reflect the run.
- [ ] `provenance.json` — targets align 1:1 with OpenAPI locations.
- [ ] `examples/` — the three-language request examples render and wire signatures correctly.
- [ ] `integration-contract.json` — crypto/callbacks/field_conditions/test_cases match the source.
- [ ] `handoff/` — `integration-tasks.md` order/blockers read sensibly, `postman_collection.json` imports, `sdk-hints.json` covers the endpoints (derived; no schema duplicated).

## Invariant re-check

- [ ] No fabricated content: anything a source does not state stays `null` and is
  recorded in `missing`; fail-closed gaps are reported, never guessed.
- [ ] Any defect fixed in this release has a regression test, benchmark fixture,
  quality-gate scenario, or documented follow-up in `docs/PIPELINE_FOLLOWUPS.md`.
