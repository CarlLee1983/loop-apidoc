# loop-apidoc 0.33.1 release notes

Release date: 2026-08-10

## Summary

Restore CI coverage for strict Core candidate validation.

## Changed

- Added fail-closed regression coverage for strict Core candidate eligibility,
  including decision, release, claim-count, and artifact-binding checks.

## Strategy impact

- [x] None — test coverage only; user-facing behavior and product direction are unchanged.
- [ ] Updated — <list each strategy document changed>

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
