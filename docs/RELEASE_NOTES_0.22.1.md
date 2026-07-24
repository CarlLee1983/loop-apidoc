# loop-apidoc 0.22.1 release notes

Release date: 2026-07-24

## Summary

Prevent preprocess output collisions while preserving source-relative paths.

## Changed

- `preprocess` now preserves source-relative paths for directory input, so files
  with the same basename in separate source directories remain distinct.
- Converted PDFs now retain their original suffix in the derived filename:
  `guide.pdf` becomes `guide.pdf.md`, avoiding a collision with a sibling
  `guide.md`.
- The complete preprocess output mapping is validated before content is written;
  an unresolvable derived-name collision fails clearly without a partial output.
- Updated roadmap, pipeline follow-ups, README, and operator manuals to document
  the corrected preprocessing behavior.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
