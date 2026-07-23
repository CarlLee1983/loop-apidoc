# loop-apidoc 0.22.0 release notes

Release date: 2026-07-24

## Summary

Add deterministic exact-evidence verification and source-backed Core parity benchmarks.

## Changed

- Added fail-closed `CLAIM_BOUND_EXACT_REFERENCE` verification for prose evidence
  that has no parsed scalar. Support now requires the exact manifest source, typed
  locator, normalized-fragment digest, and one resolved material claim path; legacy
  filename-only citations remain insufficient.
- Added versioned, allowlisted OpenAPI structural derivations for operation paths and
  methods, response statuses, request/response schema references, request-body
  properties, and schema field name/type/required facts. Core recomputes every result
  from exact JSON Pointer fragments and verifies all required one- or two-hop local
  reference context and digest chains.
- Added a committed `expected/core-parity.json` graduation contract to all 13 benchmark
  cases. The source-backed FunkyGames and RSG replays now reach legacy PASS / Core
  accept with every material claim supported; five additional restored cases retain
  immutable acquisition metadata while awaiting claim-complete exact-evidence parity.
- Updated the extraction schema reference, architecture/design records, benchmark plan,
  roadmap, READMEs, and English/Traditional-Chinese teaching and operator pages for the
  new evidence semantics and current benchmark state.

## Known limitations

- Six historical benchmark source snapshots remain unavailable locally. Their
  source-backed checks correctly skip in CI-safe runs; this release does not claim a
  strict-local zero-skip benchmark pass or a production-Core cutover.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
- Source-backed Core shadow replay for FunkyGames and RSG
