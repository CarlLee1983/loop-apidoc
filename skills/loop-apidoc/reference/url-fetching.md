# URL fetching SOP (coverage-checked)

Use this when any source is a public URL. The goal is not "how to fetch" but
**"how to know you fetched everything"**: make omissions visible as checkable
findings, matching the pipeline's fail-closed spirit. Write the result to
`<WORK>/url_sources/coverage.json` and pass it to assemble via `--url-coverage`.

## 1. Discovery

1. Fetch the entry page. If it is a JS SPA shell (see §5), render it with the
   Playwright MCP first, then parse.
2. Treat the **navigation tree (sidebar / menu) as the authoritative "should-fetch"
   list** — every page it lists should be fetched; do not chase links outside it
   (avoids unbounded crawl).
3. If the site exposes `sitemap.xml`, cross-check the entry-path subtree against the
   nav tree to catch gaps. If there is none, do not force it.

## 2. Confirm (human in the loop)

Before fetching, show the should-fetch list (page title + URL + level) to the user
to add/remove. Pages the user removes are recorded as `skipped_by_user`. In
non-interactive contexts (e.g. CI), skip confirmation, use the discovered list as-is,
and set `confirmed_by_user: false` in coverage.json.

## 3. Fetch

- Fetch each page with defuddle-cli first (saves tokens). On an empty-shell hit or
  suspiciously short body → upgrade to Playwright rendering and re-fetch.
- Save each page under `<WORK>/url_sources/` and record the method (`defuddle` /
  `playwright`) and result status.
- If it is still a shell after re-fetch → keep the `empty_suspect` status. **Never**
  fill it with inferred content.

## 4. Report (coverage)

After fetching, write `<WORK>/url_sources/coverage.json` (schema in §7). Then run
assemble with `--url-coverage "<WORK>/url_sources/coverage.json"`. The preparation
stage compares expected vs. results and emits `warning`-level findings for gaps
(fetch failures, empty shells, unfetched expected pages, auth-required pages without
a local alternative, an unconfirmed list, or a missing coverage.json).

## 5. Empty-shell heuristics

Any one hit → treat as a suspected shell and re-fetch with rendering:

- Main-body word count (after stripping nav/footer) below threshold.
- Page is only a loading/skeleton marker or an empty `<div id="root">`-style container.
- Body length is wildly out of proportion to the `<title>` / nav-menu scale.

## 6. Login-gated resources

Security red line: **the pipeline and the agent never handle or record credentials.**

- **Interactive session**: open a real browser with the Playwright MCP and have the
  **user log in by hand** (including 2FA); then, in the same session, fetch the
  confirmed list page by page.
- **Non-interactive, or login too complex** (enterprise SSO, device binding): mark the
  page `auth_required`; the user logs in themselves and saves the page (HTML/PDF) into
  the local sources, which the pipeline treats as an ordinary local file. Reference
  that saved file in `results[].file` so the coverage check counts it as covered.
- No credential automation (env token / cookie injection) — YAGNI.

## 7. coverage.json schema

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
- `results[].method`: `defuddle` | `playwright`
  (`auth_required` / `fetch_failed` / `skipped_by_user` may omit `file` / `method`).

A malformed coverage.json (missing key, unknown status) fails assemble loudly (exit 2).
