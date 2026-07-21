# URL fetching SOP (coverage-checked)

Use this when any source is a public URL. The goal is not "how to fetch" but
**"how to know you fetched everything"**: make omissions visible as checkable
findings, matching the pipeline's fail-closed spirit. Write the result to
`<WORK>/url_sources/coverage.json` and pass it to assemble via `--url-coverage`.

## Direct machine-readable OpenAPI URL

When the entry URL itself returns OpenAPI JSON or YAML, it is a single immutable document,
not a navigation entry point. Do **not** call `catalog-url`, `cache-url-pages`,
`related-url-pages`, or `select-url` against it.

1. Run:

   ```bash
   <APIDOC> snapshot-openapi-url --url "<ENTRY_URL>" --sources "<SOURCES>" \
     --coverage "<WORK>/url_sources/coverage.json" [--filename "<stable-name>.json"] \
     [--confirmed-by-user]
   ```

   The command downloads one response, verifies that it declares `swagger: "2.0"` or
   `openapi: "3.x"`, writes the original bytes, prints their SHA-256, and creates the one-entry
   ledger with `status: "fetched"` and `method: "direct"`. It fails rather than overwriting a
   snapshot or coverage file.
2. Read the local snapshot as the source of endpoints, components, servers, security, and
   examples; do not copy it directly to the final output or assume omitted integration details.
   Cite the local filename plus JSON Pointer during extraction.

The local snapshot is the only evidence subagents read. Re-fetch only when intentionally
creating a new source-set version.

## GitBook LLMS Markdown corpus

When a GitBook-style entry point publishes `llms.txt`, prefer the deterministic Markdown
lane over rendering its JavaScript shell:

```bash
<APIDOC> cache-gitbook-llms --url "<ENTRY_URL>" --sources "<SOURCES>" \
  --coverage "<WORK>/url_sources/coverage.json"
<APIDOC> manifest --sources "<SOURCES>" --url "<ENTRY_URL>" \
  --output "<WORK>/manifest.preflight.json"
<APIDOC> extract-markdown-drafts --sources "<SOURCES>" \
  --manifest "<WORK>/manifest.preflight.json" \
  --output "<WORK>/markdown-api-facts.json"
```

`cache-gitbook-llms` fetches `llms.txt` once, then caches every first-seen `.md` URL that
is same-origin and below the entry-path prefix. It preserves that relative URL hierarchy
under `<SOURCES>`, writes a `<document>.source.json` sidecar (original URL, SHA-256, fetch
timestamp), and fails before writing pages if the index is invalid, no URL is eligible, or
an immutable destination/coverage output already exists. A page-level fetch error does not
abort the batch: it is recorded as `fetch_failed` in coverage and must remain visible during
review. It never crawls URLs absent from the index.

`extract-markdown-drafts` reads only usable Markdown files named in the manifest. Its output
is a non-authoritative, line-cited aid: explicit endpoint headings, explicitly labelled
Header/Query/Request/Response tables, and fenced examples. It does not produce extraction
JSON, infer missing details, or replace source reading, endpoint-agent extraction,
`verify-extraction`, or `assemble`.

## 1. Catalog the navigation; do not crawl it

Run `catalog-url` against the entry page:

```bash
<APIDOC> catalog-url --url "<ENTRY_URL>" --output "<WORK>/url_sources/catalog.json"
```

It downloads **only** `<ENTRY_URL>` and writes every deduplicated same-origin sidebar
node with its title, parent, and breadcrumb. Static one-page anchors are retained as
nodes with an `anchor` field: they are selectable sections of the entry document, not
separate fetches. The navigation tree is the authoritative
**coverage universe**, not an automatic fetch list. If the raw entry page is a JS SPA
shell (see §5), do not infer child URLs from it; obtain rendered entry-page evidence
before selecting a scope.

Optionally cross-check an entry-path sitemap subtree against this catalog. Do not chase
ordinary body links, and do not fetch navigation children during cataloging.

## 2. Cache the catalog with tools, not a model

When the site is public and bounded by the catalog, cache every catalog node locally:

```bash
<APIDOC> cache-url-pages --catalog "<WORK>/url_sources/catalog.json" \
  --output "<WORK>/url_corpus"
```

The command stores raw HTML under `raw/` and navigation-free body text under `body/`.
Its `corpus.json` stores only compact cards: title, breadcrumb, headings, internal links,
Action/error-code entities, hashes, sizes, and paths to the local evidence. It never
passes page bodies to a model. `--max-pages` and `--max-bytes-per-page` bound the work.

If the catalog has no navigation nodes (or the documentation is intentionally one
page), use `cache-url-entry --url "<ENTRY_URL>" --output "<WORK>/url_corpus"` to cache
the entry page directly. For an already downloaded static HTML file, use
`normalize-html-snapshot --input page.html --url "<ENTRY_URL>" --output
"<WORK>/sources/page.md"`; it creates Markdown and a URL/hash provenance sidecar.

## 3. Relate pages before model reading

For a task entry page, produce candidate cards from body evidence:

```bash
<APIDOC> related-url-pages --corpus "<WORK>/url_corpus/corpus.json" \
  --url "<TASK_ENTRY_URL>" --output "<WORK>/url_sources/candidates.json"
```

Candidates are ranked by direct/reverse main-body links, shared Action/error-code
entities, and common navigation branch. These are retrieval signals, **not claims that
the pages are semantically required**. Give the model the task plus these compact cards;
only after it selects a candidate may it read that page's local `body_file` (or a
relevant section of it). Never send the complete corpus or raw HTML to the model.

## 4. Select and confirm the model-reading scope

Create an explicit scope before the model reads any page body:

```bash
<APIDOC> select-url --catalog "<WORK>/url_sources/catalog.json" \
  --branch "<DOCUMENT_BRANCH>" --term "<TOPIC>" \
  --output "<WORK>/url_sources/selection.json"
```

`--branch`, `--term`, and repeatable `--url` are optional review filters. At least one
is required, so an agent cannot accidentally treat the complete sidebar as the model
scope. The catalog remains the full inventory; `selection.json.selected` is a review
seed, not a requirement to re-fetch pages. Show that selected list (title + URL +
breadcrumb) to the user to add or remove pages. In non-interactive contexts, retain it
as selected and set `confirmed_by_user: false` in coverage.json.

For a complete corpus, derive `coverage.json.expected` from the catalog and record a
result for every cached page. Preserve `catalog.json` and `selection.json` as the
visible record of known pages and model-reading scope. Do not represent an unreviewed
body as a failed fetch or source evidence.

## 5. Fetch (when a full local corpus is not appropriate)

- Fetch each page with defuddle-cli first (saves tokens). On an empty-shell hit or
  suspiciously short body → upgrade to Playwright rendering and re-fetch.
- Save each page under `<WORK>/url_sources/` and record the method (`defuddle` /
  `playwright`) and result status.
- If it is still a shell after re-fetch → keep the `empty_suspect` status. **Never**
  fill it with inferred content.

## 6. Report (coverage)

After fetching, write `<WORK>/url_sources/coverage.json` (schema in §7). Then run
assemble with `--url-coverage "<WORK>/url_sources/coverage.json"`. The preparation
stage compares expected vs. results and emits `warning`-level findings for gaps
(fetch failures, empty shells, unfetched expected pages, auth-required pages without
a local alternative, an unconfirmed list, or a missing coverage.json).

## 7. Empty-shell heuristics

Any one hit → treat as a suspected shell and re-fetch with rendering:

- Main-body word count (after stripping nav/footer) below threshold.
- Page is only a loading/skeleton marker or an empty `<div id="root">`-style container.
- Body length is wildly out of proportion to the `<title>` / nav-menu scale.

## 8. Login-gated resources

Security red line: **the pipeline and the agent never handle or record credentials.**

- **Interactive session**: open a real browser with the Playwright MCP and have the
  **user log in by hand** (including 2FA); then, in the same session, fetch the
  confirmed list page by page.
- **Non-interactive, or login too complex** (enterprise SSO, device binding): mark the
  page `auth_required`; the user logs in themselves and saves the page (HTML/PDF) into
  the local sources, which the pipeline treats as an ordinary local file. Reference
  that saved file in `results[].file` so the coverage check counts it as covered.
- No credential automation (env token / cookie injection) — YAGNI.

## 9. coverage.json schema

```json
{
  "entry_url": "https://docs.example.com/api/",
  "confirmed_by_user": true,
  "expected": [
    { "url": "https://docs.example.com/api/auth", "title": "驗證", "source": "nav" }
  ],
  "results": [
    {
      "url": "https://docs.example.com/api/auth",
      "status": "fetched",
      "file": "url_sources/auth.md",
      "method": "defuddle"
    }
  ]
}
```

- `expected[].source`: `nav` | `sitemap` | `user`
- `results[].status`: `fetched` | `fetched_rendered` | `empty_suspect` | `fetch_failed` |
  `auth_required` | `skipped_by_user`
- `results[].method`: `defuddle` | `playwright` | `direct`; use `direct` only for a single
  machine-readable JSON/YAML response saved unchanged as the local source snapshot
  (`auth_required` / `fetch_failed` / `skipped_by_user` may omit `file` / `method`).

A malformed coverage.json (missing key, unknown status) fails assemble loudly (exit 2).
