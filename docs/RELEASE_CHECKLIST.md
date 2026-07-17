# Release Checklist

Run before tagging a release or merging a significant pipeline change. CI
(`.github/workflows/ci.yml`) covers the deterministic checks automatically; the
items marked **(local sources)** can only run on a machine that has the
operator-provided, gitignored `benchmarks/<case>/sources/` present.

## Automated in CI

- [ ] `npm run tag:check` passes after fetching remote tags; every tag matches
  the committed SemVer `v{version}` policy and no ordering anomaly exists.
- [ ] `uv sync --dev` resolves cleanly.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run pytest --cov=loop_apidoc` passes with total coverage at or above 95% — unit + integration + the benchmark discovery guard.
  - CI fails on any test failure.
  - CI fails if benchmark case discovery becomes empty or loses a required case
    (`test_benchmark_harness_discovers_cases` asserts the 10 required cases are
    still discovered).
- [ ] `uv run python scripts/quality_gate.py` passes in CI-safe mode.

## Deep local benchmark revalidation (when source snapshots are available)

The benchmark *case* assertions in `tests/test_benchmarks.py`
(`test_benchmark_case`) **SKIP** when `benchmarks/<case>/sources/` is absent, so
CI does not exercise them. Run these checks where the original, dated source
snapshots are available:

- [ ] `uv run pytest tests/test_benchmarks.py` with sources present — every
  committed case runs (no skips) and matches its `expected/` declaration.
- [ ] Confirm no case is silently skipped: the run reports 10 benchmark cases
  executed, not skipped.
- [ ] `uv run python scripts/quality_gate.py --strict-local` passes — no
  benchmark source directory is missing and no benchmark case is skipped.

These checks strengthen a release but do **not** block a patch release when a
historical upstream source cannot be lawfully or reproducibly retrieved. Never
substitute a newer document or an error page just to satisfy the gate. Record
the unavailable source snapshot and perform the deterministic CI checks plus a
targeted, source-backed spot-check for the changed behavior instead.

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

## Creating the release tag

Prepare the release version before validation. The command requires a clean
worktree, takes the version once, synchronizes every release metadata location,
refreshes `uv.lock`, and creates a non-overwritable release-note skeleton:

```bash
npm run release:prepare -- --version 0.11.0 --summary "Describe the release"
```

Complete the notes, run the checks above, and commit the release metadata. Then
use the package's committed version instead of manually choosing or checking a tag:

```bash
# Fetches origin tags first, pushes HEAD to origin/main, validates strict semver
# ordering and uniqueness, then creates an annotated tag for pyproject.toml's version.
npm run release:tag -- --message "loop-apidoc 0.11.0"
```

`release:tag --dry-run` previews without writing. It pushes only after Tagsmith
accepts the local-and-fetched-remote tag history; a concurrent remote tag still
makes `git push` fail safely, so fetch and retry instead of forcing a tag.
