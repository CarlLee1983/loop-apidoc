# loop-apidoc 0.40.0 release notes

Release date: 2026-08-24

## Summary

Harden governed lifecycle persistence and immutable artifact publication.

## Changed

- Governed feedback and Effective artifact publication now rejects namespace replacement,
  symlink traversal, and partial-publish states before they can become current assets.
- Assembly-run and candidate-import publication now uses atomic no-replace behavior with
  rollback-safe predecessor handling.
- Core lifecycle persistence now enforces its unit-of-work and approval ordering invariants,
  so governed artifacts are not visible before approval completes.

## Strategy impact

- [x] None — This is a reliability and security hardening release; it does not change product direction, priority, or subsystem scope.
- [ ] Updated — <list each strategy document changed>

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
