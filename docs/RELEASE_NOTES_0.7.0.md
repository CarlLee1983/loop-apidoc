# loop-apidoc 0.7.0 release notes

Release date: 2026-07-15

## Summary

This release adds a tool-first URL-document retrieval path for documentation sites whose
navigation is broad but whose relevant content is narrow. It preserves complete local evidence
while keeping unrelated page bodies out of model context.

## Added

- `catalog-url` indexes same-origin sidebar navigation from one entry page without fetching child
  pages. The resulting `catalog.json` is the visible coverage universe.
- `select-url` records an explicit review seed by branch, term, or URL; it cannot silently select
  the entire navigation tree.
- `cache-url-pages` fetches a bounded catalog into local `raw/` HTML and navigation-free `body/`
  evidence. `corpus.json` contains compact metadata, hashes, and file paths rather than page
  bodies.
- `related-url-pages` produces compact candidate cards using main-body links, shared Action/error
  code entities, and navigation branch signals.
- A model-neutral orchestration contract for Codex and Claude Code documents logical router,
  extractor, integrator, and verifier roles. The host maps those roles to its own models; the
  plugin does not hard-code a model vendor or name.

## Workflow

```text
catalog-url -> cache-url-pages -> related-url-pages
  -> model selects local body_file evidence -> extract -> verify-extraction -> assemble
```

Models receive candidate cards first, then only the selected local page bodies. The deterministic
CLI remains the authority for fetching, parsing, provenance, coverage, schema validation, and
release artifacts.

## Compatibility and migration

- No existing command or output contract was removed.
- The new URL commands are optional and require no migration for local files, PDFs, Word files,
  or existing OpenAPI inputs.
- Claude Code continues to use the bundled CLI through `$CLAUDE_PLUGIN_ROOT`; Codex continues to
  use the globally installed `loop-apidoc` command. Both use the same skill and artifacts.

## Retrieval smoke benchmark

Against the public JDB transfer documentation entry page on 2026-07-15:

- 122 catalog pages were cached successfully.
- The cache held 46,254,688 bytes of raw HTML and 543,325 characters of extracted page bodies.
- Candidate ranking completed in 0.42 seconds after a 97.54-second cache pass.
- For Action 19 review, the router saw 20,001 characters of candidate cards; the entry page plus
  three selected related pages added 10,508 characters. The 30,509-character model-reading
  boundary was about 17.8× smaller than reading every extracted page body.

This is a retrieval/context-boundary measurement, not a cross-model quality or pricing claim.
Network performance and document contents will vary by site and time.

## Validation

Before publishing or tagging, run the repository
[release checklist](RELEASE_CHECKLIST.md). This release additionally verifies version agreement
between `pyproject.toml`, `uv.lock`, `loop_apidoc.__version__`, and the Claude plugin manifest.
