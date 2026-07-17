---
name: loop-apidoc
description: Use when the user wants to convert messy API integration sources (PDF, Markdown, Word, HTML, OpenAPI JSON/YAML, or public URLs) into source-grounded OpenAPI 3.1, Traditional-Chinese Markdown docs, provenance, examples, review HTML, and validation reports.
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
  model, and the correction strategy (load when handling assemble results, steps 6–8).
- **`reference/url-fetching.md`** — the coverage-checked URL fetching SOP + `coverage.json`
  schema (load when any source is a public URL, before fetching).
- **`reference/model-orchestration.md`** — model-neutral role, artifact, escalation, and
  runtime-mapping contract (load when splitting work across models or Codex/Claude agents).

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

## Output-level checkpoint

Before reading sources, dispatching subagents, or running `<APIDOC> manifest`, tell the user
that the pipeline keeps its normal deterministic validation, then ask which **delivery level**
they want for this run. Record the answer as `<OUTPUT_LEVEL>` and repeat it in the final
summary. Use **minimal (default)** if the user explicitly asks to proceed without an answer or
the host is non-interactive.

| `<OUTPUT_LEVEL>` | Deliver and discuss | Do not load into agent context unless needed to fix validation |
| --- | --- | --- |
| `minimal (default)` | `openapi.yaml`, `provenance.json`, `validation/report.json`, and `integration-contract.json` when the source defines integration mechanics | Markdown guide, `review.html`, `examples/`, `handoff/`, preparation/source-quality/score/diff reports |
| `review` | `minimal` plus `api-guide.zh-TW.md` and `review.html` | `examples/`, `handoff/`, and optional analysis reports |
| `handoff` | `minimal` plus `examples/` and `handoff/` | Markdown guide, `review.html`, and optional analysis reports |
| `full` | Every generated product and optional report that the user requested | Nothing selected by this table |

Explain that this is a **delivery and agent-context policy**, not a reduction in source
grounding or validation: the current CLI still builds the compatible run directory required by
its validators. For every level, the agent must still parse `assemble --json`, inspect
validation failures, and correct the extraction when necessary. To save tokens, for artifacts
outside `<OUTPUT_LEVEL>` **do not open, summarize, or pass** their content between agents;
refer only to their paths if a validation issue makes one relevant. `score`, `diff`, and
source-quality reports remain opt-in commands/features, not an implication of `full`.

## Model-neutral orchestration

The skill does **not** select a vendor or model. Let the host map the logical roles in
`reference/model-orchestration.md` to its available fast, standard, and high-reasoning
models. Tools and validation remain the factual authority; models only route, extract, or
review grounded local evidence. Never send a complete URL corpus or raw HTML merely because a
larger-context model is available.

## Flow

`manifest` (preflight) → read sources via a read-only subagent fan-out → **you** write
`inventory.json` (+ optional `integration.json`); each endpoint subagent writes its own
`endpoints/ep<N>.json` → `verify-extraction` → `assemble` (deterministic
plan→generate→validate) → correct on FAIL.

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
- **HTML snapshot** (a saved static page; `.html`/`.htm` is a supported manifest format) →
  `<APIDOC> normalize-html-snapshot --input page.html --url "<ORIGINAL_URL>" --output
  "<WORK>/sources_md/page.md"` — writes Markdown plus a URL/hash provenance sidecar; cite
  the original URL + anchor.
- **OpenAPI JSON/YAML** → read as a source for endpoints/schemas/security/servers/examples;
  still go through `inventory.json` / `endpoints/*.json` (do not bypass).
- **Public URLs** → follow **`reference/url-fetching.md`**. For an HTML documentation
  entry point, use catalog → cache → relate → targeted model reading → report. For a direct
  OpenAPI JSON/YAML URL, use its direct-snapshot lane instead:

  ```bash
  <APIDOC> snapshot-openapi-url --url "<URL>" --sources "<SOURCES>" \
    --coverage "<WORK>/url_sources/coverage.json" --confirmed-by-user
  ```

  It downloads once, validates Swagger 2.0/OpenAPI 3.x, writes an immutable local snapshot,
  records its SHA-256, and writes the one-entry ledger with `method: "direct"`. It refuses to
  overwrite either artifact. Read only that local file thereafter; do not run HTML navigation
  cataloguing against machine-readable JSON/YAML. In both cases, pass the original URLs to
  `manifest`/`assemble` via `--url` and the coverage file via
  `--url-coverage "<WORK>/url_sources/coverage.json"`. Cite the local filename plus JSON
  Pointer (for example `openapi.json#/paths/~1payments/post`), not an inferred HTML anchor.

## Subagent contract (extraction)

You orchestrate; **read-only subagents extract**. For each extraction below, dispatch a
read-only subagent (file read + search only — **no web, no write**; for URLs the
`<WORK>/url_sources/` cache is the evidence). Give it: the source location
(`<EXTRACT_SOURCES>` + URL cache), the relevant manifest source ids, the endpoint/section
scope, the exact schema (from `reference/extraction-schemas.md`), and the grounding rule.

Write permission is layered. An **endpoint** subagent writes exactly the one
`endpoints/ep<N>.json` path you assign it and returns **one line** of summary
(e.g. `ep05 OK 8 params 1 responses`) — never the JSON body, which would cost
2–4k tokens of pure carriage per endpoint. The **inventory** and **integration**
subagents write nothing and return their JSON object; **you** write those two files.
No subagent may write another subagent's file, `inventory.json`, or `integration.json`.

Grounding and the read-only posture toward *sources* are unchanged: a subagent only
reads sources and never fetches the web. Control is regained by verification, not by
carriage — `verify-extraction` (step 5) enforces the cross-file invariants.

Grounding rule (include in every subagent prompt): *"Fill strictly from the sources. Anything
the sources do not state → null and add a short label to `missing`. Never infer; never apply
REST/OAuth conventions. Return only the JSON object."*

After writing any extraction file, parse it as JSON before continuing. Use the **English
keys** exactly as the schemas show — localized machine keys are rejected at assemble (exit 2).

### 1.5 Source-quality gate (before extraction)

After `manifest` and any required `preprocess`, dispatch one read-only quality-review
subagent over the complete source package. It returns only JSON observations grounded in
source filename + page/section/anchor. The controller writes
`<WORK>/source-quality-observations.json`, then runs:

```bash
<APIDOC> assess-sources --sources "<SOURCES>" \
  --manifest "<WORK>/manifest.preflight.json" \
  --observations "<WORK>/source-quality-observations.json" \
  --source-set "vN" --output "<WORK>/source-quality"
```

Exit `1` means `reject`: provide the generated supplement report and stop. Do not create
`inventory.json` or endpoint extraction files. Exit `0` permits extraction; warnings remain
visible and must not be filled with assumptions. When this gate ran, pass
`--source-quality "<WORK>/source-quality"` to `assemble` (step 6) — the passing report is
retained in `<run_dir>/source-quality/`, and a `reject` verdict aborts assemble (exit 2).
See `reference/source-quality.md`.

### 2–4. Extract → write the JSON

Open **`reference/extraction-schemas.md`** for the exact schemas and conventions, then:

2. **inventory** — one subagent reads every source and returns one object; **you** write
   `<WORK>/inventory.json`. Include every endpoint and every error code.
3. **endpoints** — one subagent per `inventory.endpoints` entry, **in parallel** (≤6
   concurrent, then batch). Tell each subagent the exact path to write:
   `<WORK>/endpoints/ep<N>.json` (zero-padded, inventory order). It writes that one file
   and returns one summary line. Filename order carries no meaning — the gate matches on
   `method`/`path`, not on `<N>`. When the source section shows a response (or request)
   JSON example, include it in `examples[]` — see `reference/extraction-schemas.md`.
4. **integration** (optional) — one subagent over the encryption/signing/callback/
   field-condition sections; it returns the JSON and **you** write `<WORK>/integration.json`.
   Omit the file entirely only when the sources describe no integration mechanics.

### 5. Verify the extraction

```bash
<APIDOC> verify-extraction \
  --sources "<SOURCES>" --extraction "<WORK>" [--url "<URL>" ...] --json
```

Exit 0 → proceed. Exit 2 → the JSON array on stdout lists every violation (missing or
duplicate endpoint file, an endpoint not in inventory, an unresolvable `schema_ref` or
`security[]`, a localized key, an unrooted `path`, an uncited `source`). Fix the extraction
JSON and re-run. `assemble` runs the same checks, so skipping this step is safe but wastes
a round trip.

### 6. Assemble + validate

```bash
<APIDOC> assemble \
  --sources "<SOURCES>" --extraction "<WORK>" --output "<OUT>" [--url "<URL>" ...] \
  [--source-quality "<WORK>/source-quality"] --json
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

### 7. On the result

- **`ok == true`** → done. Confirm the product artifacts selected by `<OUTPUT_LEVEL>`
  (step 8); only point the user at `review.html` when the chosen level includes it.
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

### 8. Final evidence check

Confirm the selected artifacts in `run_dir` exist, plus `validation/report.json` for every
level. The compatible run directory also contains the normal generated artifacts
(`api-guide.zh-TW.md`, `review.html`, `examples/`, `handoff/`, and preparation reports), but
outside the selected level do not load or describe them. For PASS/FAIL detail, read
`validation/report.md` only when its JSON counterpart is insufficient to drive correction;
the `review.html` page does **not** embed a validation summary.

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
