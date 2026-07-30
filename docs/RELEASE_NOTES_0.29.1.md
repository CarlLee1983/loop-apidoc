# loop-apidoc 0.29.1 release notes

Release date: 2026-07-30

## Summary

Synchronize English GitHub Pages documentation and release-version footers.

## Changed

- Added the missing English benchmark-harness section to the GitHub Pages
  onboarding tour, including the four assurance layers and the separate
  sanitized-fixture lane.
- Added matching CI-safe, sanitized-fixture, and strict-local operating guidance
  to the English operator manual.
- Corrected the stale English introduction footer and updated `release:prepare`
  so future releases synchronize both English and Traditional-Chinese Pages
  version footers, with a regression test at the release-script boundary.

## Strategy impact

- [x] None — documentation parity and release-metadata synchronization only; no product direction, priority, or subsystem scope changed
- [ ] Updated — <list each strategy document changed>

## Validation

- `npm run tag:check`
- `npm run docs:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
