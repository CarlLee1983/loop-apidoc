# loop-apidoc 0.33.2 release notes

Release date: 2026-08-10

## Summary

Stabilize strict Core candidate coverage in CI.

## Changed

- Extended strict Core candidate regression coverage to include evidence binding
  and an unspecified run architecture, keeping the CI coverage gate stable.

## Strategy impact

- [x] None — test coverage only; user-facing behavior and product direction are unchanged.
- [ ] Updated — <list each strategy document changed>

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
