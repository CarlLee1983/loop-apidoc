# loop-apidoc 0.17.0 release notes

Release date: 2026-07-21

## Summary

Adds deterministic GitBook llms.txt Markdown caching and local line-cited Markdown API draft extraction before bounded agent review.

## Changed

- Added `cache-gitbook-llms` to fetch a GitBook `llms.txt` index once and cache every safe,
  same-origin Markdown page below its entry path, with provenance sidecars and coverage results.
- Added `extract-markdown-drafts` to generate non-authoritative, line-cited endpoint, labelled
  table, and fenced-example facts from manifest-named Markdown before bounded agent review.
- GitBook page fetch failures are retained as coverage evidence; unsafe URLs, immutable output
  collisions, and invalid indexes fail before a partial corpus is written.
- `CLAUDE.md` now refers to `AGENTS.md` as the canonical repository guidance, removing duplicated
  maintenance instructions.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
