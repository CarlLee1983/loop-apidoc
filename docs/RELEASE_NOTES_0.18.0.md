# loop-apidoc 0.18.0 release notes

Release date: 2026-07-21

## Summary

Adds Markdown extraction draft scaffolding, providing a review-only bridge from cited Markdown facts to extraction-shaped inventory and endpoint JSON.

## Changed

- Added `extract-markdown-drafts` to collect line-cited endpoint, table, and example facts from manifest-named Markdown sources.
- Added `scaffold-extraction` to project those review-only facts into extraction-shaped inventory and endpoint JSON for agent review.
- The scaffold is deliberately non-authoritative: agents must copy, re-read, and complete it before `verify-extraction` or `assemble` accepts the extraction input.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
