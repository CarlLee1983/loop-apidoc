# loop-apidoc 0.9.0 release notes

Release date: 2026-07-16

## Summary

This minor release makes static single-page provider documentation a first-class
URL source, including the RSG transfer-wallet documentation pattern.

## Added

- `catalog-url` now recognizes static table-of-contents lists and records
  entry-page anchors as selectable `anchor` sections.
- `cache-url-pages` caches a one-page document once while preserving its anchor
  sections in the corpus. `cache-url-entry` provides an explicit direct-entry
  cache path for an empty catalog or intentionally single-page documentation.
- `normalize-html-snapshot` converts an already downloaded HTML page into a
  Markdown source and writes a URL/SHA-256 provenance sidecar.
- HTML is a supported manifest source format.

## Changed

- Source-quality guidance now specifies the observations JSON schema and a
  valid non-empty example.
- Response validation and extraction guidance now explain that a provider which
  documents an envelope but no HTTP status should be represented with OpenAPI
  `default`, rather than requiring an invented status code.

## Compatibility

- Existing commands, catalog records without anchors, and corpus consumers keep
  their existing fields and behavior; `anchor` and `sections` are additive.
- No command, output contract, or supported Python version was removed.

## Validation

- `uv run ruff check loop_apidoc tests`
- `uv run pytest` (778 passed, 74 skipped)
- Direct smoke tests against the public RSG entry page confirmed anchor cataloging
  and direct-entry caching.
