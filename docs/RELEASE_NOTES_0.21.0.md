# loop-apidoc 0.21.0 release notes

Release date: 2026-07-23

## Summary

Add verified v1 exact-evidence references to the agent extraction contract.

## Changed

- The agent extraction contract now accepts optional v1 `evidence[]` references
  with exact manifest source identity, a typed locator, a normalized-fragment
  SHA-256, and a material claim path.
- `verify-extraction` and `assemble` re-materialize each supplied fragment,
  verify its digest, and resolve its claim path before any run directory is
  created. Stale, ambiguous, unsupported, and unmatched references fail
  closed.
- Shadow uses a verified v1 reference for its declared material path instead
  of falling back to a legacy locator for that same path. Deterministic Core
  verification remains responsible for the final relationship.
- Legacy `source` citations remain supported. Runs record extraction contract
  version `2`; migration to v1 exact evidence is optional.
- English and Traditional-Chinese reference, operator, onboarding, and
  architecture documentation now explain the exact-evidence boundary.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
