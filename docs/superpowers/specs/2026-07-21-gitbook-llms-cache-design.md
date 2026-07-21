# GitBook LLMS Markdown Cache Design

## Goal

Add a dedicated `cache-gitbook-llms` CLI command that turns a public GitBook
entry URL into an immutable, source-ready Markdown package. It must fetch the
entry's `llms.txt` once, cache every listed same-origin Markdown page, preserve
their readable URL paths below a local source root, and emit a complete URL
coverage ledger for downstream extraction.

## Scope

The command supports public HTTP(S) GitBook documentation sites that expose an
`llms.txt` index. It does not crawl HTML navigation, render JavaScript, follow
links inside downloaded Markdown, fetch credentials, or attempt to normalize
non-Markdown formats.

## CLI Contract

```bash
loop-apidoc cache-gitbook-llms \
  --url https://example.gitbook.io/docs \
  --sources ./sources \
  --coverage ./work/url_sources/coverage.json
```

`--url` is the public GitBook entry URL. `--sources` is the destination for
source-ready Markdown and provenance sidecars. `--coverage` is the destination
for the agent-consumable `coverage.json` ledger.

The command normalizes the entry URL, derives its `llms.txt` URL, and fetches
that index exactly once. It parses absolute URLs in index order, retaining only
unique URLs that:

- use HTTP or HTTPS;
- have the same scheme, host, and effective entry-path prefix as the entry;
- end in `.md` after removing a fragment; and
- map to a safe relative local path.

The command preserves retained URLs' first-seen order. It never follows a link
found in an individual Markdown page.

## Output Layout and Provenance

For a retained Markdown URL, the file is stored beneath `--sources` using the
URL path below the entry path. For example:

```text
https://example.gitbook.io/docs/guides/payments.md
  -> sources/guides/payments.md
```

Each downloaded Markdown file is written unchanged. Its sibling
`<name>.md.source.json` sidecar records the original URL, content SHA-256, and
fetch timestamp using the existing URL/hash provenance convention. This makes
the source package directly consumable by `manifest`, `assess-sources`,
`verify-extraction`, and the source-facts gate.

The coverage ledger has `entry_url` set to the supplied entry URL and contains
every retained index URL in `expected` with `source: "sitemap"`. Every expected
page has one result: successful downloads use `status: "fetched"`, a source-root
relative `file`, and `method: "direct"`; recoverable per-page failures use
`status: "fetch_failed"` and carry no file or method. `confirmed_by_user` is
false because the index is machine-discovered. The command reports the count of
successful and failed page fetches.

## Failure and Immutability Rules

Invalid entry URLs, an inaccessible or non-successful `llms.txt`, an empty
eligible URL set, unsafe URL-to-path mapping, an existing coverage file, or any
pre-existing target Markdown file or sidecar are command errors. In each of
these cases the command must fail before writing a partial source package.

Once the output targets have passed the preflight collision checks, a fetch or
size-limit failure for an individual indexed page is not a command failure. It
is represented in coverage and the remaining pages continue to download.

The command applies an explicit bounded per-page response size, uses the
existing bounded HTTP-client pattern, and never sends credentials, cookies, or
authorization headers.

## Architecture

Create a focused GitBook cache module separate from `url_catalog.py` and
`url_corpus.py`:

- Pure functions parse `llms.txt`, normalize eligible URLs, and map a URL to a
  safe source-relative Markdown path.
- One orchestration function performs the bounded HTTP reads, preflight checks,
  Markdown/sidecar writes, and coverage construction.
- The CLI command is the user-facing I/O adapter and prints a concise result.

The module reuses existing coverage models and URL/hash utilities where their
contracts fit. It does not weaken the catalog flow; users still choose
`catalog-url` for sites whose navigation is the authoritative coverage universe.

## Tests

Unit tests cover index parsing, first-seen deduplication, scheme/host/prefix
filtering, fragment removal, rejection of traversal-like paths, and deterministic
path mapping.

CLI integration tests use a mocked HTTP client to cover:

1. successful download of multiple Markdown sources with preserved contents,
   sidecars, and a complete ordered coverage ledger;
2. duplicate, external, and non-Markdown index links being absent from the
   package and ledger;
3. one indexed-page failure being retained as `fetch_failed` while sibling pages
   are written; and
4. index failure, empty eligible index, and every collision category failing
   without creating partial output.

## Documentation

Update the URL-fetching skill reference with a GitBook LLMS lane and add the
new command to README.md, README.en.md, operator manuals, architecture manuals,
onboarding manuals, and AGENTS.md/CLAUDE.md. Canonical teaching copy remains
English-primary with Traditional-Chinese support where the existing document
pairing requires it.
