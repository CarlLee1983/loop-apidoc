# loop-apidoc 0.9.1 release notes

Release date: 2026-07-16

## Summary

This patch release completes the OpenAPI fidelity fixes identified while
validating the RSG transfer-wallet documentation.

## Fixed

- A documented response envelope without a provider-published HTTP status now
  emits an OpenAPI `default` response instead of inventing `200`.
- Extracted error codes now produce a reusable `components.schemas.ErrorCode`
  mapping with their documented meanings and HTTP statuses.
- Conventional `ErrorCode` fields reference that shared component, and source
  citations are retained in `provenance.json` for both the mapping and each
  error code.
- When a provider explicitly scopes an error code to an operation, extraction
  records `applicable_to` and OpenAPI emits the corresponding
  `x-loop-error-codes` operation extension.

## Compatibility

- Existing response entries with explicit HTTP status codes are unchanged.
- `applicable_to` is optional and defaults to an empty list; no operation-level
  error-code assertion is emitted unless the source documents it.

## Validation

- `uv sync --dev`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc` (782 passed, 74 skipped; 95.30% coverage)
- `uv run python scripts/quality_gate.py`
- Public RSG URL smoke test: 99 catalog nodes, 97 anchor sections, and 2
  cached documents.
