# Source Freshness Fingerprint Gate — Design

**Date:** 2026-07-18
**Status:** Approved (design)
**Topic:** A cheap pre-extraction gate that answers "did the source change since we last analyzed it?" so scheduled jobs skip the expensive parse/extraction when the version is unchanged.

## Problem

A completed run produces `openapi.yaml` carrying `info.version`. When sources are
re-checked on a schedule (e.g. daily cron / CI), re-running the full agent-native
extraction pipeline every time is wasteful: most checks find **no change**. We want a
cheap, deterministic gate that inspects the sources, compares a lightweight signal
against a stored baseline, and only greenlights a re-parse when something actually
changed. For machine-readable OpenAPI sources the decisive signal is `info.version`:
**same version ⇒ skip, no cost.**

## Core requirement (non-negotiable, inherits the repo invariant)

- The gate **never fabricates** and never guesses. A source it cannot fetch or read is
  reported as **inconclusive**, not silently treated as "unchanged."
- The gate does **no extraction** and does **no LLM work**. It only computes cheap
  signals (HTTP validators, `info.version`, sha256) and compares.
- Pure functions outside the two designated I/O write exits, matching the existing
  package conventions.

## Scope

Covers all four source shapes the pipeline already accepts:

- **Machine-readable OpenAPI URL** — decisive signal is `info.version`.
- **Web page URL (HTML)** — no clean version field; use HTTP conditional request
  (`ETag` / `Last-Modified`) then raw-body `sha256`.
- **Local file (PDF/MD/…)** — `sha256` (deterministic; `mtime` is not reliable).
- **Mixed sources** — a run may combine the above; the run-level verdict aggregates.

Out of scope for v1 (documented as follow-ups): normalized-HTML signal (hashing the
readable main text via `html_snapshot.html_to_markdown` instead of raw body) to reduce
false "changed" from dynamic page noise; auto-triggering the re-parse from inside the
CLI (kept as a scheduler/skill concern).

## Approach (chosen: A)

New self-contained package `loop_apidoc/freshness/` + two flat CLI commands
(`record-fingerprint`, `check-freshness`) + a dedicated `source-fingerprint.json`
sidecar as the single baseline of truth + a skill reference for headless scheduling.

Rejected alternatives:
- **B (extend `diff`/foundry):** requires two full run-dirs and foundry coupling —
  overkill for a cheap pre-check.
- **C (script + skill only):** loses the repo's pure-function unit-testability and
  determinism.

## Architecture

New package `loop_apidoc/freshness/`:

| Module | Responsibility | I/O |
| --- | --- | --- |
| `models.py` | `SourceKind`, `SourceSignal`, `FingerprintEntry`, `SourceFingerprint`, `SourceStatus`, `FreshnessVerdict`, `FreshnessReport`, `FreshnessInputError` | pure |
| `signals.py` | Compute the cheap signal for one source (URL via bounded `httpx` conditional GET; file via `sha256`) + pure comparison helpers (`compare_entry`) | network read, **writes nothing** (mirrors `url_catalog.fetch_catalog`) |
| `record.py` | Build a baseline `SourceFingerprint` from a completed run-dir (reuse `manifest` scanner for local sources + `preparation/coverage.py` `load_coverage` for URL sources + read `openapi.yaml` `info.version`); write the sidecar | **write exit** |
| `check.py` | Recompute signals for each fingerprint entry, compare against the baseline → `FreshnessReport` | pure orchestration, **writes nothing** |
| `report.py` | Optional render/write of `freshness-report.{json,md}` | **write exit** |

CLI (`loop_apidoc/cli.py`) gains two flat commands, matching the existing style of
`snapshot-openapi-url` et al.:

- `record-fingerprint --run-dir <dir> --output source-fingerprint.json`
  Reads the run-dir, captures each source's current cheap signal + the generated
  `info.version`, writes the sidecar. Fails loudly (does **not** overwrite) if the
  output already exists, matching `snapshot-openapi-url`'s immutable-evidence stance —
  re-recording is an explicit `--force`.
- `check-freshness --fingerprint source-fingerprint.json [--json] [--report-dir <dir>]`
  Recomputes signals, compares, prints a human summary or `--json`, exits with the
  verdict code. `--report-dir` optionally persists `freshness-report.{json,md}`.

## Data model — `source-fingerprint.json`

```json
{
  "schema_version": 1,
  "openapi_version": "2.3.0",
  "recorded_from": "runs/<run-id>",
  "sources": [
    { "id": "https://api.example.com/openapi.json", "kind": "openapi_url",
      "signal": { "version": "2.3.0", "etag": "W/\"abc\"", "last_modified": null, "sha256": "…" } },
    { "id": "https://docs.example.com/webhooks", "kind": "web_url",
      "signal": { "version": null, "etag": null, "last_modified": "Tue, 01 Jul 2026 …", "sha256": "…" } },
    { "id": "sources/spec.pdf", "kind": "local_file",
      "signal": { "version": null, "etag": null, "last_modified": null, "sha256": "…" } }
  ]
}
```

- `id`: the URL (for URL sources) or the manifest-relative source path (for local files).
- `kind`: `openapi_url` | `web_url` | `local_file`.
- `openapi_version`: the `info.version` of the run's generated `openapi.yaml`; the
  headline "same version?" answer.
- `recorded_from`: provenance of the baseline (informational).

Baseline captured **at record time** == the source state that produced the current
`openapi.yaml` (as long as `record-fingerprint` is run right after adopting a run). This
keeps the sidecar self-contained and avoids re-plumbing `coverage.json`/corpus to store
hashes.

## Signal tiers & per-source decision

Cheapest-first, per `kind`:

- **openapi_url** — decisive field is `version` (`info.version` of the fetched doc).
  1. If the baseline entry has an `etag`, send a conditional GET (`If-None-Match`); a
     `304` ⇒ **unchanged**.
  2. Else fetch (bounded, size-capped, `trust_env=False`, like `openapi_snapshot`),
     parse, read `info.version`. Fetched `version == baseline version` ⇒ **unchanged**
     (even if bytes differ — this is the "same version, don't re-parse" rule).
  3. If `version` is absent on either side, fall back to `sha256` comparison.
- **web_url** — no version field.
  1. Conditional GET (`If-None-Match` / `If-Modified-Since`); `304` ⇒ **unchanged**.
  2. Else compare raw-body `sha256`.
- **local_file** — compare `sha256` (recomputed via the manifest scanner).

## Aggregate verdict & exit codes

| Verdict | Meaning | Exit code |
| --- | --- | --- |
| `unchanged` | every source matches its baseline signal | `0` |
| `changed` | any source's version/hash changed, or a source was added/removed vs the baseline | `1` |
| `inconclusive` | at least one source could not be fetched/read (and none was proven `changed`) | `2` |

Rationale: a fetch failure must not read as "unchanged" (would silently skip a needed
re-parse) nor force a wasteful re-parse — it is its own state the scheduler/skill can
alert on. If any source is proven `changed`, that dominates an inconclusive one (the run
already needs re-parsing).

Per-source status in the report: `unchanged` | `changed` | `added` | `removed` |
`fetch_failed`.

## CLI `--json` shape

```json
{
  "verdict": "unchanged",
  "openapi_version": "2.3.0",
  "sources_total": 3,
  "unchanged_count": 3,
  "changed": [],
  "inconclusive": [],
  "fingerprint": "source-fingerprint.json"
}
```

A `changed`/`inconclusive` run lists entries like
`{ "id": "…", "kind": "openapi_url", "status": "changed", "reason": "version 2.3.0 -> 2.4.0" }`.

## Reuse & boundaries

- `record.py` reuses the existing `manifest` scanner (local sources + sha256), the
  `preparation/coverage.py` `load_coverage` loader (URL sources + their fetched files),
  and reads `openapi.yaml` `info.version` directly.
- `signals.py` does network I/O via `httpx.Client(trust_env=False, follow_redirects=True)`
  with an accept header and a byte cap, mirroring `openapi_snapshot.snapshot_openapi_url`;
  it writes nothing.
- **File-I/O write exits added:** `freshness/record.py` (`write_fingerprint`) and
  `freshness/report.py` (`write_reports`). `check.py` and `signals.py` write nothing —
  keeping the "only these modules write" invariant in CLAUDE.md accurate.

## Skill / scheduling

- New `skills/loop-apidoc/reference/freshness-scheduling.md`: the headless scheduled
  loop —
  1. After a run is generated **and adopted**, run `record-fingerprint`.
  2. Scheduled (cron / CI / headless agent): run `check-freshness`.
  3. `exit 0` → stop; no extraction cost incurred.
  4. `exit 1` → re-run the extraction pipeline (`assemble` …), then `record-fingerprint --force` to refresh the baseline.
  5. `exit 2` → alert a human (source unreachable / auth / moved).
- `skills/loop-apidoc/SKILL.md`: a short pointer + the `<APIDOC> check-freshness …`
  invocation片段, so a scheduled headless agent knows the gate exists.

## Testing (TDD)

- `signals.py` pure comparison: version match, version fallback→sha, sha match/mismatch,
  local-file sha.
- `record.py`: build a fingerprint from a fixture run-dir (mixed sources); assert schema
  + captured signals; refuse to overwrite without `--force`.
- `check.py`: `unchanged` / `changed(version)` / `changed(sha)` / added source / removed
  source / `fetch_failed`→`inconclusive`; verdict precedence (changed > inconclusive).
- CLI: exit codes `0/1/2` and `--json` shape; `record-fingerprint` immutability.
- URL network paths use an injected `httpx.Client` / transport stub (as existing tests do
  for URL commands) — no real network in tests.

## Release doc sync (per repo policy — non-negotiable)

New commands + new pipeline concept ⇒ update in the same release:
`CLAUDE.md` (package table + File-I/O exits + command groups) and `AGENTS.md`
(kept aligned), `README.md` / `README.en.md` command lists, `docs/operator-manual.html`,
and cross-check `docs/RELEASE_CHECKLIST.md`. Version bump via `scripts/release.py prepare`.
