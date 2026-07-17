# Freshness scheduling gate

A cheap gate so a scheduled re-check can skip extraction when sources are unchanged.
Fingerprinting and comparison cost a hash and an HTTP HEAD/GET, not a model call —
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

## v1 limits

- HTML sources are fingerprinted by raw-body hash; there is no content normalization
  yet, so incidental markup changes (whitespace, ads, unrelated widgets) can register
  as `changed`.
- No added/removed-source detection: the fingerprint only tracks sources already in
  the baseline. A brand-new page that isn't reflected by an OpenAPI `info.version`
  bump is not caught by `check-freshness` — it is only picked up at the next
  `record-fingerprint` (i.e. the next full re-extraction and adoption).
