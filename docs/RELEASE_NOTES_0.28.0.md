# loop-apidoc 0.28.0 release notes

Release date: 2026-07-29

## Summary

Add provenance-verified browser-rendered URL snapshots for source-grounded API documentation.

## Changed

- Added `import-rendered-url` for importing browser-saved HTML or Markdown when
  interactive access succeeds but direct HTTP acquisition is blocked. The command
  preserves the original bytes and records the canonical URL, capture timestamp and
  method, local path, and SHA-256 in a versioned provenance sidecar.
- Added `fetched_rendered` URL coverage verification across `manifest` and
  `assemble`. A matching local snapshot is accepted without contacting the origin;
  URL, path, capture-method, provenance, or digest mismatches fail closed.
- Added optional `required_source_refs` to blocker-level source observations. A
  rejected source-quality report now emits their ordered, de-duplicated union as a
  bounded next-capture seed list without crawling or fetching it automatically.
- Kept existing direct OpenAPI snapshots, static URL caching, extraction inputs, and
  coverage ledgers compatible. Browser-rendered provenance fields are required only
  for the new `fetched_rendered` path.
- Updated the agent skill, URL-acquisition references, architecture documentation,
  operator manuals, onboarding material, landing pages, and English/Traditional-
  Chinese READMEs for the new workflow.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
