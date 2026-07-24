# loop-apidoc 0.22.4 release notes

Release date: 2026-07-24

## Summary

Add bounded governance scan triggers for source changes

## Changed

- Added `governance-scan`, which turns an existing freshness watchlist batch into
  `governance-trigger.{json,md}` for bounded human follow-up.
- A changed source produces `review_required`; unreadable or inconclusive sources
  produce `attention_required`. The command never re-extracts, generates, imports,
  or approves a contract.
- Updated the roadmap, READMEs, and operator/architecture manuals with the new
  governance-trigger workflow and its non-mutating boundary.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest -q --ignore=tests/test_benchmarks.py`
- `uv run pytest tests/test_benchmarks.py -q` (CI-safe benchmark execution; historical
  source snapshots remain intentionally skipped when unavailable)
- `uv run python scripts/quality_gate.py`
