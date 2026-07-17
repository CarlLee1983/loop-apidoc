# loop-apidoc 0.10.0 release notes

Release date: 2026-07-17

## Summary

This minor release adds a safe, repeatable source-acquisition lane for URLs
that directly return Swagger 2.0 or OpenAPI 3.x JSON/YAML.

## Added

- `snapshot-openapi-url` downloads one public machine-readable specification,
  validates its Swagger/OpenAPI declaration, and writes the original bytes as
  an immutable local source snapshot.
- The command emits the source SHA-256 and creates a one-entry URL coverage
  ledger with `method: "direct"`. Existing snapshots and ledgers are never
  overwritten.
- The loop-apidoc skill now routes direct OpenAPI URLs through this command,
  then requires extraction to read the local snapshot rather than an HTML
  navigation workflow.

## Documentation

- README files, the operator manual, and onboarding/introduction pages now
  document the direct OpenAPI route and the sixteen-command CLI surface.

## Compatibility

Existing command behavior and run-directory formats are unchanged. This adds a
new optional command and a more explicit skill route for machine-readable URL
sources.

## Validation

- `uv sync --dev`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc` (804 passed, 74 skipped; 95.26% coverage)
- `uv run python scripts/quality_gate.py`

## Historical benchmark-source note

The full strict-local benchmark pass still requires the operator-provided,
dated source snapshots. The direct OpenAPI route was additionally tested
against the public FunkyGames Transfer Operator specification: OpenAPI 3.0.4
with 27 paths was snapshotted successfully, and a duplicate output was refused.
