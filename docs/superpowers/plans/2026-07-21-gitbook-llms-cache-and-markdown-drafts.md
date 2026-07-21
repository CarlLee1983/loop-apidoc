# GitBook LLMS Cache and Markdown Drafts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic GitBook `llms.txt` cache command and a local Markdown API-facts draft command, so structured documentation is acquired and pre-indexed mechanically before bounded agent review.

**Architecture:** Keep acquisition and draft extraction separate from the existing `source_facts` validation gate. A `gitbook_llms` module fetches one index, filters safe same-origin Markdown URLs, then writes source Markdown, provenance sidecars, and URL coverage. A `markdown_drafts` package scans local Markdown into non-authoritative facts with exact source locations; an agent remains responsible for final extraction JSON and `verify-extraction` remains the enforcement boundary.

**Tech Stack:** Python 3.11, Typer, Pydantic v2, httpx, pytest, ruff, existing `UrlCoverage` data model.

## Global Constraints

- Treat source content as the sole truth. Never invent paths, fields, schemas, authentication, or endpoint semantics.
- `markdown-api-facts.json` is an aid, never valid input to `assemble` and never a replacement for `inventory.json` or `endpoints/ep<N>.json`.
- `loop_apidoc/source_facts/` stays an independent semantic-completeness gate; do not import its private parser helpers or alter its behavior to produce drafts.
- The command accepts HTTP(S) GitBook-style entry URLs only. It discovers `llms.txt` at the normalized entry location, fetches it once, and does not crawl arbitrary navigation.
- Eligible URLs must be same-origin, under the normalized entry path prefix, use the `.md` suffix, and pass path-safety checks. Preserve their relative URL hierarchy under `--sources`.
- Parse and preflight the complete index before any page write. Existing immutable destination files or sidecars are a fail-loud collision, not an overwrite.
- An index failure, malformed/no-eligible index, invalid output layout, or preflight collision must leave no half-created corpus. Individual eligible page failures are recorded as `fetch_failed` and do not abort remaining pages.
- Update every user-facing command/process document required by `AGENTS.md`, including `AGENTS.md` and `CLAUDE.md` in lockstep.

## Task 1: Model and Parse a Safe GitBook LLMS Index

**Files:**
- Create: `loop_apidoc/gitbook_llms.py`
- Create: `tests/test_gitbook_llms.py`

- [ ] Write failing pure-parser tests for a normalized entry URL and derived `llms.txt` URL, including roots and nested entry paths.
- [ ] Write failing tests that retain first-seen same-origin, in-prefix `.md` URLs and reject duplicates, fragments, non-HTTP URLs, different hosts, parent-prefix escapes, non-Markdown assets, and encoded/unsafe destination paths.
- [ ] Implement immutable models such as `GitBookLlmsError`, `GitBookPage`, and `GitBookIndex` plus pure helpers for URL normalization, index parsing, eligibility filtering, de-duplication, and relative destination calculation.
- [ ] Ensure parser output preserves the original Markdown URL for provenance and reports rejected entries deterministically for diagnostics/tests.
- [ ] Run `uv run pytest tests/test_gitbook_llms.py` and confirm all parser tests pass.

## Task 2: Cache Eligible Markdown Pages with Provenance and Coverage

**Files:**
- Modify: `loop_apidoc/gitbook_llms.py`
- Modify: `loop_apidoc/preparation/coverage.py` only if its typed schema needs a backward-compatible extension for this command
- Modify: `tests/test_gitbook_llms.py`

- [ ] Add failing tests using `httpx.MockTransport`: fetch `llms.txt` exactly once, fetch each eligible page once, preserve nested paths below `sources/`, and write `<document>.source.json` with original URL, content SHA-256, and fetched timestamp.
- [ ] Add failing tests that assert all candidate destinations are collision-checked before page requests/writes, and that an index/preflight failure creates neither page files nor coverage output.
- [ ] Add failing tests for page-level HTTP/transport failure: continue with remaining pages; record the failed source as `fetch_failed`; write coverage for all expected pages.
- [ ] Implement bounded HTTP reads with `trust_env=False`, redirects enabled, a documented timeout, and a source-size cap. Validate response success and Markdown bytes before persisting a successful page.
- [ ] Construct the coverage ledger using `UrlCoverage`: `expected` records all accepted index pages; `results` records `fetched` or `fetch_failed`, original URL, local destination when available, and any safe error detail. Use a command-specific expectation source/method only if existing enum/validators need extension.
- [ ] Write files only after index parse and complete preflight pass. Avoid replacing pre-existing page or sidecar files.
- [ ] Run `uv run pytest tests/test_gitbook_llms.py` and `uv run ruff check loop_apidoc/gitbook_llms.py tests/test_gitbook_llms.py`.

## Task 3: Expose `cache-gitbook-llms` through the CLI

**Files:**
- Modify: `loop_apidoc/cli.py`
- Modify: `tests/test_cli_url_corpus.py` or create `tests/test_cli_gitbook_llms.py`

- [ ] Add failing CLI tests for `loop-apidoc cache-gitbook-llms --url ... --sources ... --coverage ...`, successful JSON output, and exit code 2 with a concise error for invalid index/collision inputs.
- [ ] Implement the Typer command with explicit `--url`, `--sources`, and `--coverage` paths. Use the project’s existing CLI error convention and make the output machine-readable with counts, index URL, source root, and coverage path.
- [ ] Keep `cache-url-pages` behavior unchanged; this is an explicit GitBook-oriented acquisition path, not auto-detection.
- [ ] Run `uv run pytest tests/test_cli_url_corpus.py tests/test_cli_gitbook_llms.py` (or the selected test file) and `uv run loop-apidoc cache-gitbook-llms --help`.

## Task 4: Define Non-Authoritative Markdown API Draft Facts

**Files:**
- Create: `loop_apidoc/markdown_drafts/__init__.py`
- Create: `loop_apidoc/markdown_drafts/models.py`
- Create: `loop_apidoc/markdown_drafts/markdown.py`
- Create: `tests/markdown_drafts/test_markdown.py`

- [ ] Write failing pure scanner tests covering explicit endpoint headings; explicitly labelled Header/Headers, Query, Body, Request, and Response tables; Chinese label equivalents; table columns for name/type/required/description; and fenced JSON/XML/text examples.
- [ ] Include line-range assertions for endpoint candidates, field rows, and example fences. Prove that nested table decoration and group-label rows do not become fields.
- [ ] Include fail-closed tests: unlabelled tables, prose-only claims, unsupported table headers, and ambiguous section ownership must be omitted rather than interpreted.
- [ ] Implement immutable Pydantic/domain models for document facts, endpoint candidates, field facts, and examples. Preserve literal source text, source filename, start/end lines, label, and only explicitly represented columns.
- [ ] Implement a pure, fence-aware Markdown scanner. Associate facts only with explicit headings/labels, never via HTTP or API conventions. Make source ordering and output ordering deterministic.
- [ ] Run `uv run pytest tests/markdown_drafts/test_markdown.py` and `uv run ruff check loop_apidoc/markdown_drafts tests/markdown_drafts/test_markdown.py`.

## Task 5: Collect Facts from Manifest Sources and Add `extract-markdown-drafts`

**Files:**
- Create: `loop_apidoc/markdown_drafts/collect.py`
- Modify: `loop_apidoc/cli.py`
- Create: `tests/markdown_drafts/test_collect.py`
- Modify: `tests/test_cli_gitbook_llms.py` or create `tests/test_cli_markdown_drafts.py`

- [ ] Write failing collection tests that load only manifest-named usable Markdown sources, keep source-relative paths, aggregate deterministically, and surface unreadable/invalid manifest input using a dedicated input error.
- [ ] Write failing CLI tests for `loop-apidoc extract-markdown-drafts --sources ... --manifest ... --output ...`, JSON output, no-overwrite output collision behavior, and parse-safe errors.
- [ ] Implement the read-side collector and a CLI writing boundary that writes one `markdown-api-facts.json`. Its JSON must state that it is a draft/aid and include source-local facts plus omitted/unsupported counts where available.
- [ ] Do not make this command write extraction JSON, amend `inventory.json`, or call `assemble`.
- [ ] Run the focused collector/CLI tests and `uv run loop-apidoc extract-markdown-drafts --help`.

## Task 6: Document the Deterministic GitBook Workflow

**Files:**
- Modify: `skills/loop-apidoc/SKILL.md`
- Modify: relevant `skills/loop-apidoc/reference/*.md` (`url-fetching.md`, `extraction-schemas.md`, and/or `model-orchestration.md`)
- Modify: `README.md`, `README.en.md`
- Modify: `docs/index.html`, `docs/introduction.html`, `docs/onboarding.html`, `docs/onboarding.en.html`, `docs/operator-manual.html`, `docs/operator-manual.en.html`, `docs/architecture-manual.html`, `docs/architecture-manual.en.html`, `docs/ARCHITECTURE.md`
- Modify: `AGENTS.md`, `CLAUDE.md`

- [ ] Add the explicit workflow: `cache-gitbook-llms` → `manifest` → `extract-markdown-drafts` → bounded agent review/final extraction JSON → `verify-extraction` → `assemble`.
- [ ] State that all same-origin, in-prefix `.md` URLs in `llms.txt` are cached by default; page-level failures are visible in coverage and must be handled before source-grounded assembly.
- [ ] State that draft facts are deterministic, location-cited, non-authoritative aids; source content and final verification remain authoritative.
- [ ] Update command inventories, package/file-I/O architecture descriptions, and both agent instruction files consistently. Keep English-primary/zh-TW secondary policy for teaching material.
- [ ] Add/update documentation-focused tests if the repository has command-inventory assertions; otherwise verify each new command name and documented pipeline with `rg` and `git diff --check`.

## Task 7: Full Verification and Real-Source Smoke Check

**Files:**
- Modify only files identified by failures from prior tasks.

- [ ] Run `uv run pytest`.
- [ ] Run `uv run ruff check .`.
- [ ] Run the focused end-to-end command sequence against the VG GitBook URL in a fresh, explicitly named temporary/work directory (never overwrite `work/` or existing runs): cache source pages, build a manifest, extract drafts, and inspect coverage/facts JSON for source path preservation and field/example line citations.
- [ ] Do not claim final API documentation was generated by drafts alone. If executing the full pipeline, use the required agent endpoint extraction and `verify-extraction` before `assemble`.
- [ ] Run `git diff --check`, inspect `git status --short`, and report tests plus any source fetch failures separately from code-test status.
