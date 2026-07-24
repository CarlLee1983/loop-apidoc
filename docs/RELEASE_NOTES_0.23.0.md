# loop-apidoc 0.23.0 release notes

Release date: 2026-07-24

## Summary

Surface verified Core evidence in the local review workbench

## Changed

- The local `review` workbench now exposes Core evidence directly beside matching
  validation findings: relationship type, claim path, exact fragment locator and
  digest, and retained source excerpt.
- `contradicts` and `insufficient` relationships are explicitly labelled and are
  never rendered as supporting evidence.
- An operation-level HTTP diff is linked to Core evidence only when its method and
  path resolve to one exact Core target; field-level or ambiguous diffs remain
  unlinked rather than guessed.
- Core review artifacts are included in the review binding, so a saved decision is
  rejected as stale if the evidence changes.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
