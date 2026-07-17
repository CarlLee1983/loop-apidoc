# Freshness scheduling gate

A cheap gate so a scheduled re-check can skip extraction when sources are unchanged.
Fingerprinting and comparison cost a hash and a conditional HTTP GET, not a model call —
pay for extraction only when something actually moved.

## Baseline: record a fingerprint after adoption

Run once, right after a run is generated and adopted (approved, or otherwise treated
as the current baseline):

```bash
<APIDOC> record-fingerprint --run-dir "<run>" --output "<run>/source-fingerprint.json"
```

This hashes the run's local sources and, for URL sources, records the observable
version signal (e.g. an `ETag`/`Last-Modified` or the OpenAPI `info.version`/body
hash). The file is the baseline the scheduled checks compare against.

## Scheduled check

Run on a schedule (cron, headless agent, CI):

```bash
<APIDOC> check-freshness --fingerprint "<path>" [--sources "<dir>"] --json
```

## Exit-code contract

- **`0` unchanged** → stop. No extraction, no cost.
- **`1` changed** → re-run the extraction pipeline (the skill's normal steps 2–8),
  then refresh the baseline:

  ```bash
  <APIDOC> record-fingerprint --run-dir "<run>" --output "<run>/source-fingerprint.json" --force
  ```

- **`2` inconclusive** → alert a human. Source unreachable, auth required, or moved —
  do not guess and do not treat this as either "unchanged" or "changed."

## Headless scheduled loop (pseudocode)

```
on schedule:
  result = run(<APIDOC> check-freshness --fingerprint <path> --json)
  if result.exit == 0:
    stop                                   # no cost
  elif result.exit == 1:
    run extraction pipeline (steps 2-8)    # pays for extraction only here
    run(<APIDOC> record-fingerprint --run-dir <run> --output <path> --force)
  elif result.exit == 2:
    alert human                            # source unreachable / auth / moved
```

A ready-to-run implementation of this loop lives at
`examples/freshness-scheduling/check-and-refresh.sh` (+ its `README.md`): a cron/CI-mountable
wrapper that branches on the exit code, runs a caller-supplied `REPARSE_CMD` on `changed`,
and then refreshes the baseline with `record-fingerprint --force`. Point `REPARSE_CMD` at
your own re-extraction step (the skill's steps 2–8).

## Batch scan (many docsets)

`check-freshness` above checks one docset per invocation. Once you're scheduling
several docsets, `check-freshness-batch` collapses one scheduled pass over all of
them into a single aggregated report instead of one cron line per docset.

Point it at a watchlist file (default name `freshness-watchlist.json`):

```json
{
  "schema_version": 1,
  "items": [
    {
      "label": "newebpay-mpg",
      "fingerprint": "runs/newebpay/source-fingerprint.json",
      "sources": "sources/newebpay",
      "run_dir": "runs/newebpay/latest"
    }
  ]
}
```

`label` and `fingerprint` are required; `sources` and `run_dir` are optional (mirroring
`check-freshness`'s own `--sources`/`--run-dir` inputs). Relative paths in `fingerprint`,
`sources`, and `run_dir` resolve against the watchlist file's own directory, not the
current working directory.

```bash
<APIDOC> check-freshness-batch --watchlist "<path>" [--json] [--report-dir "<dir>"]
```

`--report-dir` writes `freshness-scan.{json,md}` — one file summarizing every item's
result, instead of reading N separate `check-freshness` outputs.

### Aggregate exit-code contract

- **`0` all unchanged** → stop. Nothing to re-run.
- **`1` any changed** → re-run extraction for the changed items (same as a single
  `check-freshness` returning `1`).
- **`2` any inconclusive/error** → alert a human for those items.

A per-item failure (source unreachable, fingerprint unreadable, etc.) does **not**
abort the batch — it is recorded as that item's `error` status and the scan continues
through the rest of the watchlist. A malformed watchlist file itself, however, fails
loud (exit `2`) before any item is scanned.

## v1 limits

- HTML sources are fingerprinted by raw-body hash; there is no content normalization
  yet, so incidental markup changes (whitespace, ads, unrelated widgets) can register
  as `changed`.
- No added/removed-source detection: the fingerprint only tracks sources already in
  the baseline. A brand-new page that isn't reflected by an OpenAPI `info.version`
  bump is not caught by `check-freshness` — it is only picked up at the next
  `record-fingerprint` (i.e. the next full re-extraction and adoption).
