# loop-apidoc 0.31.1 release notes

Release date: 2026-08-02

## Summary

Restore CI coverage when benchmark snapshots are unavailable.

## Changed

- Added focused conformance and governed-Foundry boundary tests so the CI coverage
  gate remains above 92.5% when gitignored benchmark snapshots are unavailable on
  the runner.
- No production behavior or public CLI contract changed; this patch restores the
  verification signal for the 0.31.0 release.

## Strategy impact

- [x] None — the patch only adds regression coverage and release verification; it
  does not change product direction, source-grounding policy, or workflow strategy.
- [ ] Updated — <list each strategy document changed>

## Validation

- `uv run pytest --cov=loop_apidoc --ignore=tests/test_benchmarks.py` (1,653
  passed; 92.58%, matching CI's no-snapshot condition)
- `uv run pytest --cov=loop_apidoc` (1,782 passed; 93.67%)
- `uv run ruff check tests/core/test_conformance.py tests/foundry/test_feedback.py`
- `uv run pytest tests/core/test_conformance.py tests/foundry/test_feedback.py -q`
- `uv run python scripts/quality_gate.py` (complete: ruff, pytest, 6 adversarial
  CLI scenarios)
- `uv run python scripts/quality_gate.py --sanitized-fixtures` (complete:
  sanitized benchmark fixtures and 6 adversarial CLI scenarios)
- `npm run docs:check`
- `npm run tag:check`
