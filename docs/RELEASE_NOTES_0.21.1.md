# loop-apidoc 0.21.1 release notes

Release date: 2026-07-23

## Summary

Add deterministic evidence-relationship evaluation coverage and codify the project's
test-driven development workflow.

## Changed

- Evaluation replay now covers `explicit_support`, `derived_support`,
  `contradicts`, and `insufficient` outcomes through fixed, versioned cases.
- Evaluation reports add typed evidence-relationship classification accuracy, which
  penalizes incorrect promotion or downgrading of a relationship.
- Agent guidance now requires small Red → Green → Verify slices for behavior-changing
  work, while preserving the source-backed benchmark evidence contract.

## Validation

- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
