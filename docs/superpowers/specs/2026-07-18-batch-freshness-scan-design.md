# Batch Freshness Scan — Design

**Date:** 2026-07-18
**Status:** Approved (design)
**Topic:** A batch inspection command that runs the freshness gate over many docsets from a watchlist file and produces one aggregated "which docsets need re-parsing" report.

## Problem

`check-freshness` (shipped in 0.12.0) gates one fingerprint at a time. A team managing
many API docsets wants a single scheduled pass that inspects all of them and produces one
report: which are unchanged, which changed (need re-extraction), which are inconclusive or
errored. Running one cron line per docset does not scale and produces no consolidated view.

## Core requirement (inherits the repo invariant)

- Never fabricate. An item that cannot be checked is `error`/`inconclusive`, never silently
  `unchanged`.
- The batch does **no extraction** and no LLM work — it only fans `check_freshness` over the
  watchlist and aggregates.
- Pure functions outside the existing designated write exits. `batch.py` writes nothing;
  the report writer stays in `report.py`.

## Scope

Extends the existing `loop_apidoc/freshness/` package (no new package). Adds one CLI command
`check-freshness-batch`. Reuses `check_freshness` per item unchanged.

Out of scope (follow-ups): Foundry-driven auto-enumeration of watchlist items; per-item
auto-rerun (kept a scheduler/skill concern); parallel fan-out (v1 is sequential with a
shared HTTP client).

## Watchlist file — `freshness-watchlist.json`

```json
{
  "schema_version": 1,
  "items": [
    { "label": "newebpay-mpg",
      "fingerprint": "watch/newebpay/source-fingerprint.json",
      "sources": "watch/newebpay/sources",
      "run_dir": "output/newebpay-run" },
    { "label": "stripe", "fingerprint": "watch/stripe/source-fingerprint.json" }
  ]
}
```

- `label` (required): human identifier for the report and error messages.
- `fingerprint` (required): path to that docset's baseline `source-fingerprint.json`.
- `sources` (optional): local sources root; required only when that fingerprint contains
  `local_file` entries.
- `run_dir` (optional): informational — where a re-record would target; surfaced in the report.
- **Path resolution:** every relative path is resolved against the **watchlist file's own
  directory**, so a watchlist is portable across machines/checkouts.

## Architecture (extends `loop_apidoc/freshness/`)

| Module | Addition | I/O |
| --- | --- | --- |
| `models.py` | `WatchlistItem`, `Watchlist`, `BatchItemStatus` (`unchanged`/`changed`/`inconclusive`/`error`), `BatchItemResult`, `BatchReport`; reuse `FreshnessVerdict` + `EXIT_CODES` | pure |
| `batch.py` (new) | `load_watchlist(path) -> Watchlist` (fail-loud boundary load); `scan_watchlist(watchlist, *, base_dir, client=None) -> BatchReport` (per-item `check_freshness`, shared HTTP client, per-item error captured) | network read via reused `check_freshness`; **writes nothing** |
| `report.py` | `render_batch_markdown(report) -> str`; `write_batch_reports(report, report_dir) -> tuple[Path, Path]` → `freshness-scan.{json,md}` | **write exit** |

CLI: `check-freshness-batch --watchlist <path> [--json] [--report-dir <dir>]`.

## Error handling (two layers)

- **Watchlist file** unreadable / invalid JSON / schema violation → `load_watchlist` raises
  `FreshnessInputError` (fail-loud, CLI exits 2) — you cannot even obtain the list. Matches
  the repo's boundary-validation convention (`load_coverage`, `load_score_inputs`).
- **Per item**: any failure obtaining that item's verdict (missing/unreadable fingerprint,
  malformed fingerprint, a `check_freshness` input error) is caught and recorded as a
  `BatchItemResult` with status `error` and a reason; the scan continues to the next item.

## Aggregation & exit codes (deterministic)

Per item, `check_freshness`'s `FreshnessVerdict` maps to `BatchItemStatus`
(`unchanged`/`changed`/`inconclusive`); a per-item failure is `error`.

Aggregate verdict → exit code:

| Condition | Aggregate | Exit |
| --- | --- | --- |
| any item `changed` | `changed` | `1` |
| else any item `inconclusive` or `error` | `inconclusive` | `2` |
| else (all `unchanged`) | `unchanged` | `0` |

`changed` dominates: a docset that genuinely moved needs re-parsing regardless of another
docset being temporarily unreachable. Reuses the existing `EXIT_CODES` map.

## Report content

- **Headline:** totals — N items; changed X; inconclusive/error Y; unchanged Z; plus the
  aggregate verdict.
- **Table (zh-TW):** `| label | 判定 | OpenAPI 版本 | 摘要/原因 |`, one row per item, changed/
  inconclusive/error rows carrying the reason (e.g. `version 1.0.0 -> 2.0.0`, `fingerprint
  not found`).
- **JSON:** the full `BatchReport` (machine-readable; can feed a dashboard or another step).

## Reuse & boundaries

- `scan_watchlist` calls the existing `check_freshness(fingerprint, sources_root=..., client=...)`
  per item, passing one shared `httpx.Client` (created/closed by `scan_watchlist` only when
  it owns it, and only if any item needs network). No duplication of signal/compare logic.
- **New write exit:** `report.py`'s `write_batch_reports`. `batch.py` writes nothing.
  CLAUDE.md's File-I/O-exits paragraph is updated accordingly.

## Testing (TDD)

- `load_watchlist`: fail-loud on missing file, invalid JSON, schema violation.
- `scan_watchlist`: all-unchanged→0; one-changed→1; one-inconclusive→2; one item with a
  missing fingerprint→`error`→2; changed+error together→`changed`/1 (precedence); relative
  path resolved against the watchlist dir.
- `report.py`: `render_batch_markdown` mentions verdict + a per-item reason; `write_batch_reports`
  writes both files.
- CLI: exit codes 0/1/2, `--json` shape, `--report-dir` writes `freshness-scan.{json,md}`,
  malformed watchlist → exit 2.
- URL paths use an injected `httpx.MockTransport` client; no real network.

## Release doc sync (per repo policy)

New command ⇒ update in the same release: `CLAUDE.md` (freshness package row + File-I/O exits +
command group), `AGENTS.md` (aligned), `README.md`/`README.en.md` command lists,
`docs/operator-manual.html`, and the skill `reference/freshness-scheduling.md` (batch section);
cross-check `docs/RELEASE_CHECKLIST.md`. Version bump via `scripts/release.py prepare`.
