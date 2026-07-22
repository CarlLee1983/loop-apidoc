# loop-apidoc 0.20.0 release notes

Release date: 2026-07-21

## Summary

Accept single-file preprocessing and prevent large-source endpoint inventory truncation.

## Changed

- `preprocess --sources` now accepts one local source file and processes only
  that file; directory behavior is unchanged.
- The agent skill now requires a pre-dispatch endpoint inventory checklist for
  preprocessed Markdown sources larger than 100KB or expected to contain 30+
  endpoints, preventing silent omissions from truncated inventory responses.
- Traditional-Chinese and English user guides document the new single-file
  preprocessing behavior.
- URL corpus caching conservatively identifies un-rendered SPA shells and, for
  each shell, probes only /swagger.json, /openapi.json, /v3/api-docs, and
  /api-doc/v3/sections at the same origin.
- Only JSON documents with a top-level openapi or swagger field are cached as
  separate, provenance-bearing sources. Failed, redirected, non-spec, and
  undecodable candidates are ignored without adding a source record.
- cache-url-pages and cache-url-entry now warn on stderr when cached documents
  appear to be un-rendered SPA shells.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
