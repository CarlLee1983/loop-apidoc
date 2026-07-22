# SPA-shell OpenAPI probe and CLI warning

## Goal

Extend URL corpus caching so that an un-rendered SPA shell can lead to a
bounded, fail-closed search for an explicitly identifiable OpenAPI or Swagger
JSON document.  Surface SPA-shell detection to the operator at command time.

## Scope

When a fetched HTML document meets `is_spa_shell()`, the cache flow will probe
these fixed paths at that document's origin:

- `/swagger.json`
- `/openapi.json`
- `/v3/api-docs`
- `/api-doc/v3/sections`

A response is accepted only when it is within the existing byte cap, parses as
JSON, and has a top-level `openapi` or `swagger` field.  HTTP failures,
oversized bodies, decode or JSON failures, and JSON without either field are
ignored without creating an output record.

## Design

### Corpus representation

Successful probes are represented as separate `CorpusPage` values rather than
being merged with the SPA-shell page.  The new source kind distinguishes a
normal documentation page from an `openapi_spec`; a discovered specification
also records its originating shell URL.  Its raw JSON and hash use the same
content-addressed corpus storage as other evidence.

Candidate URLs are deduplicated so the same origin/path is fetched no more than
once in one cache operation.  A source remains distinct even when it was
discovered from a shell, preserving the evidence boundary required by the
pipeline.

### CLI signal

After caching, `cache-url-pages` and `cache-url-entry` calculate their shell
count from documentation pages only, excluding any discovered specification
sources.  If nonzero, each command writes this diagnostic to stderr:

`N/M pages look like un-rendered SPA shells`

The successful command result and corpus JSON remain otherwise compatible.

### Failure handling and boundaries

The probe performs no endpoint guessing beyond the four issue-specified fixed
paths.  It neither creates a `fetch_failed` page nor records an attempted URL
when a candidate is not an identifiable API specification.  Network access and
file writes stay in the existing `url_corpus` I/O boundary; format recognition
and URL candidate construction are deterministic helpers.

## Verification

Tests will cover accepted OpenAPI and Swagger documents, non-spec JSON and
failed probes leaving no record, candidate deduplication, source separation,
and stderr warning behavior.  Focused corpus and CLI tests, then lint and the
relevant test suite, verify the change.

## Out of scope

Headless browser rendering, probing arbitrary paths, treating generic JSON as a
specification, and altering extraction or validation inputs are out of scope.
