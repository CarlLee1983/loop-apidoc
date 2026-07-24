# loop-apidoc 0.26.0 release notes

Release date: 2026-07-24

## Summary

Add source-grounded GraphQL and AsyncAPI domain projection foundations.

## Changed

- Added a protocol-neutral `Interaction` model with typed HTTP, GraphQL, and
  AsyncAPI transport bindings in the canonical Domain contract.
- Added deterministic GraphQL SDL and AsyncAPI 3.0 projection compilers for
  minimal source-backed slices, with fail-closed unsupported-transport and
  unresolved-schema handling.
- Added stable GraphQL and AsyncAPI provenance targets for exact evidence,
  alongside official-source research, snapshot coverage, and regression tests.
- Kept the existing HTTP/OpenAPI `assemble` workflow unchanged; full CLI/run
  artifact integration remains a later phase.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
