# loop-apidoc 0.9.2 release notes

Release date: 2026-07-16

## Summary

This patch closes the remaining RSG transfer-wallet OpenAPI error-code fidelity
gap.

## Fixed

- `components.schemas.ErrorCode` now emits `x-loop-error-code-map`, preserving
  every documented code's message/description, HTTP-status metadata, source
  citations, and source-stated `applicable_to` operations.
- Existing `x-loop-error-codes` and the enum remain unchanged for compatibility.
- Added the RSG transfer-wallet regression benchmark, including 15 documented
  error codes and their per-operation applicability.

## Compatibility

This is additive: clients that use the existing enum or
`x-loop-error-codes` continue to work unchanged. Application error codes remain
distinct from HTTP response statuses.

## Validation

- `uv sync --dev`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc` (791 passed, 74 skipped; 95.54% coverage)
- `uv run python scripts/quality_gate.py`
- RSG source-backed assemble and spot-check of the code map, provenance, and
  operation applicability.

## Historical benchmark-source note

The full `--strict-local` revalidation requires dated, operator-provided source
snapshots for every benchmark. Ten historical snapshots are unavailable in this
worktree; one (NewebPay NDNF-1.2.2) is no longer downloadable from the official
site. They were not replaced with newer documents or error pages. See the
release checklist for the resulting patch-release policy.
