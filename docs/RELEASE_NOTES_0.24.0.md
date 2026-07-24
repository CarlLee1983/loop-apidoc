# loop-apidoc 0.24.0 release notes

Release date: 2026-07-24

## Summary

Retain changed governance source snapshots for reproducible review.

## Changed

- Added `governance-scan --snapshot-dir <directory>` to retain the exact bytes
  classified as changed during that same freshness scan.
- Snapshots are immutable and content-addressed: the pack contains
  `governance-snapshot.json` and deduplicated `sources/<sha256>.source` files.
- Unchanged, inconclusive, and failed sources are never represented as a
  snapshot; an all-unchanged scan creates no empty evidence pack.
- The ordinary freshness and batch JSON contracts do not expose the retained
  raw bytes. Governance snapshotting remains a bounded review aid and never
  re-extracts, generates, imports to Foundry, or approves a contract.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
