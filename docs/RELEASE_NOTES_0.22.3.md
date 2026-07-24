# loop-apidoc 0.22.3 release notes

Release date: 2026-07-24

## Summary

Align the coverage gate with the CI baseline while preserving a no-regression floor.

## Changed

- Set the repository-wide coverage gate to 92.5%, matching the CI baseline when
  operator-provided benchmark sources are unavailable.
- Documented the threshold as a no-regression floor: it must not be lowered
  without an explicit quality-policy decision, and behavior-changing work still
  requires focused regression coverage.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
