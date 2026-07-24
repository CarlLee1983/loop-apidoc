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
- [ ] `uv run pytest --cov=loop_apidoc` passes with total coverage at or above
  95% — unit + integration + the benchmark discovery guard and exact-parity
  regression.
  - CI fails on any test failure.
  - `test_benchmark_harness_discovers_cases` proves all 13 required cases are
    still discovered even when source snapshots are absent.
  - `test_required_benchmark_cases_match_committed_cases` proves the explicit
    required inventory exactly matches the committed fixture identity files.
- [ ] `uv run python scripts/quality_gate.py` passes in CI-safe mode.

## Benchmark harness layers

The harness has four distinct guarantees. The **13 benchmark cases** are 13
unique fixture directories, not the number of pytest test items; each case
feeds several parametrized tests.

| Layer | Release check | Guarantee |
| --- | --- | --- |
| Committed fixture inventory | Inspect `benchmarks/<case>/{extraction/inventory.json,expected/validation.expect.json}` | The case identity is committed. |
| Discovery guard | `uv run pytest tests/test_benchmarks.py -k test_benchmark_harness_discovers_cases -q` | Fixtures are enumerated without local sources. |
| Source-backed execution | `uv run pytest tests/test_benchmarks.py -q` with original snapshots present | Applicable assemble and artifact assertions execute and pass. |
| Strict-local preflight | `uv run python scripts/quality_gate.py --strict-local` | Required/committed parity, non-empty sources for every case, all checks executed, and zero skips. |

A committed or discovered case is not necessarily source-backed. A pytest
SKIP caused by a missing source snapshot is not a benchmark pass. The canonical
terminology and case-addition workflow live in
[`BENCHMARK_VALIDATION_PLAN.md`](BENCHMARK_VALIDATION_PLAN.md).

## Deep local benchmark revalidation (when source snapshots are available)

The benchmark *case* assertions in `tests/test_benchmarks.py`
(`test_benchmark_case`) **SKIP** when `benchmarks/<case>/sources/` is absent, so
CI does not exercise them. Run these checks where the original, dated source
snapshots are available:

- [ ] `uv run pytest tests/test_benchmarks.py` with sources present — every
  committed case runs (no skips) and matches its `expected/` declaration.
- [ ] Confirm all 13 benchmark cases executed and none was skipped. Do not use
  the pytest item count as the case count.
- [ ] `uv run python scripts/quality_gate.py --strict-local` passes — no
  required benchmark source directory is missing or empty, exact parity holds,
  and no benchmark check is skipped.

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

## Completing the release publication

Prepare the release version before validation. The command requires a clean
worktree, takes the version once, synchronizes every release metadata location,
refreshes `uv.lock`, and creates a non-overwritable release-note skeleton:

```bash
npm run release:prepare -- --version 0.11.0 --summary "Describe the release"
```

Complete the notes, review every teaching/promotion document named in `AGENTS.md`,
run the checks above, and commit the release metadata. Then use the package's
committed version instead of manually choosing a tag or creating a GitHub Release:

```bash
# Fetches origin tags first, pushes HEAD to origin/main, validates strict semver
# ordering and uniqueness, creates the annotated tag for pyproject.toml's version,
# then publishes the matching GitHub Release from docs/RELEASE_NOTES_<version>.md.
npm run release:tag -- --message "loop-apidoc 0.11.0"
```

`release:tag --dry-run` validates the release-notes precondition and previews the
tag operation without pushing or writing a GitHub Release. A real run checks the
authenticated `gh` session with release-creation permission *before* it pushes or
creates a tag. It pushes only after Tagsmith accepts the local-and-fetched-remote
tag history; a concurrent remote tag still makes `git push` fail safely, so fetch
and retry instead of forcing a tag.

If Tagsmith has already published the tag but the final GitHub-Release step fails,
do not create the release manually. Resolve the GitHub authentication or API failure,
then run the safe recovery command from a clean worktree:

```bash
npm run release:github
```

It reads the committed package version and notes, and passes `--verify-tag` to
GitHub CLI, so GitHub cannot create a tag itself. Confirm the resulting Release URL
contains the expected title, full notes, and is neither a draft nor a prerelease.

The publication is complete only after the `main` CI run triggered by the push
passes. Record the Release URL, then identify and watch that run:

```bash
gh run list --branch main --limit 1
gh run watch <run-id> --exit-status
```

If it fails, preserve the published tag and Release, fix forward, and prepare a
new version.

### Tag authority and CI responsibilities

Tagsmith is the sole tag publisher. Use `npm run release:tag` after the local
release checks and release-metadata commit; do not create a release tag or normal
GitHub Release by hand, or expect GitHub Actions to create either. The command
pushes `HEAD` to `origin/main`, asks Tagsmith to validate and push the matching
annotated `v<package-version>` tag, then uses GitHub CLI only to publish the
matching Release after the tag exists.

GitHub Actions CI is a verification trigger only: pushes and pull requests run
tag-policy validation, dependency sync, and the quality gate. The Pages
workflow may deploy documentation from `main`, but neither workflow creates a
tag or a GitHub Release. Monitor the CI run after the push and release; a CI
failure is handled as a follow-up fix and release, never by force-moving a tag.
