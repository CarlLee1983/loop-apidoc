---
name: loop-apidoc
description: Use when the user wants to convert messy API integration sources (PDF, Markdown, Word, OpenAPI JSON/YAML, or public URLs) into source-grounded OpenAPI 3.1, Traditional-Chinese Markdown docs, provenance, examples, review HTML, and validation reports.
---

# loop-apidoc: source-grounded API doc generation

You turn the user's API documentation sources into standardized, traceable artifacts.
**The source is the only ground truth**: anything a source does not state is `null` and
recorded in `missing`. **Never speculate; never apply REST/OAuth conventions.** Validation
fails loudly on missing required info rather than guessing.

Two reference files hold the heavy detail — load each when you reach that phase:

- **`reference/extraction-schemas.md`** — the exact JSON schemas + field conventions
  (load while extracting, steps 2–4).
- **`reference/assemble-and-correction.md`** — the `assemble --json` contract, the issue
  model, and the correction strategy (load when handling assemble results, steps 5–7).
- **`reference/url-fetching.md`** — the coverage-checked URL fetching SOP + `coverage.json`
  schema (load when any source is a public URL, before fetching).

## CLI invocation (`<APIDOC>`)

This skill runs on both the Claude Code plugin and the Codex CLI. Every command below writes
the CLI as `<APIDOC>`; resolve it once per shell call:

- **`$CLAUDE_PLUGIN_ROOT` is set** (Claude Code plugin) → the CLI lives in the bundled
  package: `uv run --project "$CLAUDE_PLUGIN_ROOT" loop-apidoc`.
- **otherwise** (Codex / standalone) → call the globally installed command `loop-apidoc`
  directly (`uv tool install`; see README).

For a deterministic, shell-portable (bash *and* zsh) prefix, prepend this to any CLI line —
it builds an argv array that is safe with spaces:

```bash
RUN=(loop-apidoc); [ -n "$CLAUDE_PLUGIN_ROOT" ] && RUN=(uv run --project "$CLAUDE_PLUGIN_ROOT" loop-apidoc)
"${RUN[@]}" <command> ...
```

(Do **not** use `${CLAUDE_PLUGIN_ROOT:+uv run --project "$CLAUDE_PLUGIN_ROOT"}` inline: bash
word-splits it but zsh does not, so it breaks under zsh.)

## Flow

`manifest` (preflight) → read sources via a read-only subagent fan-out → **you** write
`inventory.json` + `endpoints/ep<N>.json` (+ optional `integration.json`) → `assemble`
(deterministic plan→generate→validate) → correct on FAIL.

### 1. Collect & prepare sources

Create a dedicated `<WORK>` dir outside `<SOURCES>` and `<OUT>`. Treat `<SOURCES>` as
immutable evidence; write all derived text/JSON under `<WORK>`.

```bash
<APIDOC> manifest --sources "<SOURCES>" [--url "<URL>" ...] --output "<WORK>/manifest.preflight.json"
```

Read the manifest: no usable local source **and** no successful URL → stop and report. Skip
`unreadable`; convert/replace `unsupported` before extraction or report the gap; for
`duplicate`, extract the first only.

Then choose the read location `<EXTRACT_SOURCES>` by source type:

- **Markdown / small simple PDF** → `<EXTRACT_SOURCES>=<SOURCES>` (subagents read directly).
- **Large or table-heavy PDF** (40+ pages, parameter/error tables, or raw text loses
  columns) → `<APIDOC> preprocess --sources "<SOURCES>" --out "<WORK>/sources_md"`, set
  `<EXTRACT_SOURCES>=<WORK>/sources_md`. Cite the original filename + the inserted
  `<!-- page N -->` marker.
- **Word** → extract readable text/markdown into `<WORK>/sources_text` if the runtime can't
  read it directly; preserve the original filename + headings so citations point back.
- **OpenAPI JSON/YAML** → read as a source for endpoints/schemas/security/servers/examples;
  still go through `inventory.json` / `endpoints/*.json` (do not bypass).
- **Public URLs** → follow **`reference/url-fetching.md`** (discover → confirm → fetch →
  report). Save readable text/HTML/Markdown under `<WORK>/url_sources/`, point subagents
  there (no re-fetching), and write `<WORK>/url_sources/coverage.json`. Pass the original
  URLs to `manifest`/`assemble` via `--url` and the coverage file via
  `--url-coverage "<WORK>/url_sources/coverage.json"`. Cite the original URL + anchor.

## Subagent contract (extraction)

You orchestrate; **read-only subagents extract**. For each extraction below, dispatch a
read-only subagent (file read + search only — **no web, no write**; for URLs the
`<WORK>/url_sources/` cache is the evidence). Give it: the source location
(`<EXTRACT_SOURCES>` + URL cache), the relevant manifest source ids, the endpoint/section
scope, the exact schema (from `reference/extraction-schemas.md`), and the grounding rule. The
subagent **returns the JSON only** — no prose, no file writes. **You (the orchestrator) are
the only writer.**

Grounding rule (include in every subagent prompt): *"Fill strictly from the sources. Anything
the sources do not state → null and add a short label to `missing`. Never infer; never apply
REST/OAuth conventions. Return only the JSON object."*

After writing any extraction file, parse it as JSON before continuing. Use the **English
keys** exactly as the schemas show — localized machine keys are rejected at assemble (exit 2).

### 2–4. Extract → write the JSON

Open **`reference/extraction-schemas.md`** for the exact schemas and conventions, then:

2. **inventory** — one subagent reads every source and returns one object; **you** write
   `<WORK>/inventory.json`. Include every endpoint and every error code.
3. **endpoints** — one subagent per `inventory.endpoints` entry, **in parallel** (≤6
   concurrent, then batch); **you** write `<WORK>/endpoints/ep<N>.json` (zero-padded,
   inventory order). Then verify `len(endpoints/*.json) == len(inventory.endpoints)` and that
   each file's `method`/`path`/`source` matches its inventory entry.
4. **integration** (optional) — one subagent over the encryption/signing/callback/
   field-condition sections; **you** write `<WORK>/integration.json`. Omit the file entirely
   only when the sources describe no integration mechanics.

### 5. Assemble + validate

```bash
<APIDOC> assemble \
  --sources "<SOURCES>" --extraction "<WORK>" --output "<OUT>" [--url "<URL>" ...] --json
```

To iterate toward a **quality bar** (not just "no errors"), add the score-gated flags:

```bash
<APIDOC> assemble --sources "<SOURCES>" --extraction "<WORK>" --output "<OUT>" \
  --score --target-score 85 --round-index 1 --max-rounds 6 --json
```

The payload then carries a `loop` block; drive correction off `loop.verdict` (see
`reference/assemble-and-correction.md`). Without `--score`, the loop below is the
baseline validation-gated flow.

Parse the JSON on stdout: `ok`, `run_dir`, `review_html`, `status`, `report.issues` (full key
list + the 9-field issue shape are in `reference/assemble-and-correction.md`). Exit `2` is an
input-contract error **or** a run-dir collision, **not** a validation round — fix the named
JSON file/field (or choose a fresh `--output`) and re-run.

### 6. On the result

- **`ok == true`** → done. Confirm the product artifacts (step 7) and point the user at
  `review.html` for an offline, at-a-glance review of scope / sources / gaps.
- **`ok == false`** → open **`reference/assemble-and-correction.md`** and drive correction.
  The gate is **severity** (only `error` issues fail; surface `warning`s as known gaps).
  Each issue carries `code`, `severity`, `location`, `evidence`, `suggested_fix`, and
  structured-routing fields (`target_file`/`field_path`/`requery_scope`). Use `location` and
  `suggested_fix` to understand which field is missing or incorrect, then re-read just that
  scope with a targeted read-only subagent, overwrite the named JSON, and re-run assemble.
  **Max 3 rounds** for the baseline flow. When you ran with `--score`, drive the
  loop off `loop.verdict` instead (`continue` → correct `loop.actionable` and
  re-assemble with an incremented `--round-index` and `--prev-score`; `converged`
  → done; `plateau`/`exhausted` → stop). Conflicts / unsupported assertions that
  survive re-verification, and anything in `loop.irreducible`, → present the gaps
  to the user; **never fabricate.**

### 7. Final evidence check

Confirm `run_dir` holds the product artifacts: `openapi.yaml`, `api-guide.zh-TW.md`,
`review.html`, `provenance.json`, `integration-contract.json` (always present — empty = no
mechanics), `examples/` (always present when ≥1 endpoint — `<placeholder>` when the source
gives no value), `handoff/` (`integration-tasks.md`, `postman_collection.json`,
`sdk-hints.json`), `validation/report.{json,md}`, and `preparation-report.{json,md}`. For
PASS/FAIL detail read `validation/report.md` — the `review.html` page links to it but does
**not** embed a validation summary.

## Other commands (outside the generate loop)

- `<APIDOC> validate --output "<run_dir>"` — re-validate an existing run dir (exit 0/1).
- `<APIDOC> diff --base "<run_dir_a>" --head "<run_dir_b>"` — classify changes between two
  completed runs (breaking / additive / changed / source_only); writes
  `<run_dir_b>/diff/report.{json,md}`.

## Important

- Use a dedicated `<WORK>` dir (may live in a scratch area outside `<OUT>`). Keep derived
  readable sources (`sources_md`, `sources_text`, `url_sources`) out of the original
  `<SOURCES>` unless the user wants a normalized source package.
- Each correction round overwrites the same extraction JSON, then re-runs assemble.
- Exit codes: `0`=PASS, `1`=validation FAIL, `2`=extraction input file error **or** run-dir
  collision.
