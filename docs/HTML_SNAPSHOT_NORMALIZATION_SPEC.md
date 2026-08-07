# HTML Snapshot Normalization Specification

**Status:** Accepted
**Owner:** `loop_apidoc/html_snapshot.py`
**Decision date:** 2026-08-07

## Problem

`normalize-html-snapshot` turns a user-acquired static HTML page into Markdown that
an agent can read after the normal manifest and source-risk gates.  Its current
converter preserves headings, tables, and `pre` blocks, but it only chooses a
`main` element (or the complete document) and flattens inline structure.  A page
whose documentation is in an `article`, or whose meaningful links and nested lists
are structural, can consequently lose readable structure before review.

[SparkFetch](https://github.com/Sparkfetch/sparkfetch) was evaluated as an upstream
design reference.  Its separation of selected body, Markdown, text, links, and
metadata is useful, but its regex-based HTML extraction and unconstrained crawling
are not suitable for this source-bound pipeline.  It will not be a runtime dependency
or an acquisition adapter.

## Outcome

Improve static HTML-to-Markdown normalization so the result retains the readable
structure needed for human and agent review, while the acquired raw HTML remains
the sole authoritative evidence.

The public conversion seam remains:

```python
html_to_markdown(html: str) -> str
```

`normalize_html_snapshot(input_file, url, output)` remains the sole file-writing
adapter: it writes the converted Markdown and a sidecar that binds it to the exact
raw-file SHA-256.  No CLI flags, run artifact format, manifest schema, or source-risk
policy changes in this work.

## Required behavior

1. Select exactly one document root, in this order: the first `main`, otherwise the
   first `article`, otherwise the first `body`, otherwise the parsed document root.
   Do not concatenate candidate roots.
2. Exclude `aside`, `footer`, `nav`, `script`, `style`, and `template` together with
   their descendants.  Do not add heuristic content scoring or site-specific rules.
3. Preserve the existing output for headings, paragraphs, table cells (including
   escaped pipes), and `pre`/`code` block line breaks.
4. Render nested unordered and ordered lists as Markdown list items with deterministic
   indentation.  Preserve each item's readable text once; group/empty wrapper nodes
   must not produce duplicate lines.  Identical sibling items remain distinct: source
   repetition must not be globally deduplicated.
5. Render an anchor with non-empty readable label as `[label](href)`.  Keep its
   document-provided `href` unchanged; an empty-label anchor contributes no synthetic
   label, URL, or text.
6. Preserve inline text in a deterministic order.  Formatting-only tags may be
   unwrapped; the feature must never invent emphasis, code language, URL resolution,
   titles, metadata, API facts, or missing text.
7. Given identical HTML input, conversion produces byte-identical Markdown.  It must
   not fetch URLs, execute JavaScript, resolve links, read files, or mutate input.

## Explicit non-goals

- Crawling, URL discovery, rendering JavaScript, bypassing authentication/challenges,
  robots-policy handling, or changing URL acquisition.
- Replacing the raw HTML evidence with normalized Markdown, or treating the Markdown
  as support for a claim without a source fragment.
- Full browser-grade HTML/CSS layout fidelity, a general-purpose HTML-to-Markdown
  library, or a new production dependency.
- Changing the established UTF-8 replacement decoding or wall-clock
  `normalized_at` sidecar field.  Those provenance-contract questions are independent
  of structure preservation and require their own fail-closed proposal.
- Altering `url_corpus` routing cards; those remain metadata only and are not agent
  source input until materialized, manifested, and risk-scanned.

## Constraints and invariants

- The existing raw SHA-256 provenance sidecar remains mandatory and continues to
  identify the raw input file and URL.
- The exact raw HTML remains available for citation and manual comparison.  Cleaning
  only makes it easier to read; it does not filter what counts as supplier evidence.
- The implementation stays in `loop_apidoc/html_snapshot.py`; the pure converter is
  the test seam and the write adapter remains small.
- Existing user work under `work/` is unrelated and must not be changed.

## Acceptance criteria

The implementation is accepted when focused public-seam tests demonstrate:

1. `article` is selected when `main` is absent, and `body` is selected when both are
   absent; unrelated chrome is absent from the result.
2. A nested mixed list retains item order and indentation without duplicated text.
   Repeated source items are retained as repeated Markdown items.
3. Labelled relative and absolute links are rendered using their unchanged `href`;
   empty anchors do not yield fabricated output.
4. Existing table, pipe-escaping, and multiline-code behavior remains green.
5. The command still writes the Markdown plus the raw-file hash provenance sidecar.
6. The focused test module, full test suite, Ruff, and Markdown docs check pass.

## Delivery plan

1. Add one failing public-seam test per acceptance behavior.
2. Make the smallest pure converter change that passes each test; retain the current
   standard-library parser and add no dependency.
3. Run focused tests, then the full verification set.
4. Review the final diff for source-authority, provenance, and scope regressions.

## Rollback

The change is isolated to normalization output.  Reverting the converter and its
tests restores the former output without migrating stored data, changing raw
evidence, or invalidating existing provenance sidecars.

## 繁體中文摘要

這項功能只改善已取得之**靜態** HTML 快照的可讀 Markdown 結構：依序選取
`main`、`article`、`body`，並保留巢狀清單與有文字的連結。原始 HTML 仍是唯一
可核對的證據；不新增爬取、JavaScript 渲染、URL 解析或任何推論。轉換器持續為
純函式，檔案與 provenance sidecar 仍只由既有寫入 adapter 處理。
