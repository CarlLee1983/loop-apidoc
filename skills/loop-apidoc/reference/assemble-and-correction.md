# Assemble output & correction loop (loop-apidoc)

On-demand reference for driving `<APIDOC> assemble` and correcting a validation FAIL.
Load this once you've run assemble (SKILL.md step 6). The `assemble` command line and the
happy-path summary live in SKILL.md.

## `verify-extraction`

Runs `assemble`'s input boundary standalone: builds a manifest, checks the agent-written
extraction JSON, writes nothing, creates no run directory.

- `exit 0` clean; `exit 2` with every violation at once. Never `1` (that means validate FAIL).
- `--json` prints a JSON array of violation strings (`[]` when clean).
- `--sources` is required because `source` citations are checked against `manifest.json`.

Before the cross-file invariants, `verify-extraction` also enforces three input-boundary
schema contracts a subagent can only satisfy if we state them (`source_guard.py`):
`endpoints[].path` must start with `/` (the host belongs in `environments[].base_url`,
never in `path`); every `source` citation must name a manifest source; and a null-path
(webhook/callback) endpoint must carry a non-blank `summary`. Violating any of these
aborts before a run directory is created.

Cross-file invariants (all `error`, all also enforced by `assemble`):

1. `len(endpoints/*.json) == len(inventory.endpoints)`
2. the identity multiset of endpoint files equals inventory's — identity is `(method, path)`
   when `path` is a string, or `(method, summary)` for a null-path (webhook/callback)
   endpoint (whitespace-normalized)
3. no identity appears in two endpoint files
4. every `schema_ref` resolves to an `inventory.schemas[].name`
5. every `security[]` entry resolves to an `inventory.security_schemes[].name`
6. every `endpoints[].server` resolves to an `environments[].name`

Null-path endpoints are **not** exempt from invariants 2–3: `summary` is their identity,
and `source_guard`'s boundary check above guarantees every null-path entry has one before
these invariants run. An endpoint whose `summary` resolves to `None` (neither a string
`path` nor a usable `summary`) is excluded from the multiset/duplicate check itself — but
that state cannot survive the boundary check, so it should never be observed here.

Hard schema errors (malformed JSON, wrong types) abort on the first one — the remaining
checks would be meaningless.

## The `--json` payload

`assemble … --json` prints one object on stdout with **6 top-level keys**:

```json
{"run_id": "str", "run_dir": "str", "review_html": "<run_dir>/review.html",
 "ok": true, "status": "passed|failed", "report": {"issues": [ ... ]}}
```

- `ok` is the gate (see below); `status` is the same thing as a string (`passed`/`failed`).
- `report.issues` is the list of `Issue` objects.

## The `Issue` object (9 fields)

```json
{"code": "OPENAPI_INVALID|OUTPUT_MISMATCH|REQUIRED_INFO_MISSING|SOURCE_UNVERIFIED|SOURCE_CONFLICT|UNSUPPORTED_ASSERTION",
 "severity": "error|warning",
 "location": "str (free text)",
 "evidence": "str",
 "suggested_fix": "str",
 "auto_fixable": false,
 "target_file": "inventory.json|endpoints/|integration.json|null",
 "field_path": "str|null",
 "requery_scope": "str|null"}
```

The three structured-routing fields are emitted as `null` when the validator can't map the
issue precisely; `auto_fixable` is always present (default `false`).

### `root_causes` — fix once, not N times

`validation/report.json` carries an additive `root_causes[]` alongside `issues[]`.
Each entry groups issues sharing `(code, severity, target_file)` when there are two
or more of them:

```json
{"code": "SOURCE_UNVERIFIED", "severity": "error",
 "target_file": "integration.json",
 "fix_once": "統一改寫該檔所有 source 為 '<relative_path> p.<N>' …",
 "affected_locations": ["integration.crypto.0", "integration.crypto.1", "…"]}
```

**Consume `root_causes` first.** One rewrite of `target_file` clears every location in
`affected_locations` — do not spawn one requery subagent per location. Then handle the
`issues[]` entries that no root cause covers (those with `target_file: null`, and
single-occurrence issues).

`root_causes` never affects pass/fail: the gate remains "any `error`-severity issue in
`issues[]`". A report can have root causes and still PASS if they are all warnings.

## The gate: severity, not code

**A run FAILs iff it has any `error`-severity issue.** `warning`s never fail the run — but
surface them to the user as known gaps. Do **not** infer pass/fail from the issue code: the
same code can be `error` or `warning` depending on context, and the old "fixable vs
fail-closed by code" taxonomy is narrative, not how the gate works. `auto_fixable=True` only
marks the three integration-reference cases below; you still fix every `error` by correcting
your extraction JSON and re-running.

## Issue codes → what it means → how to respond

| code | typical severity | meaning | response |
|---|---|---|---|
| `OPENAPI_INVALID` | error | assembled OpenAPI is structurally invalid, or a `$ref` doesn't resolve, or YAML won't parse | fix the upstream JSON that produced it (usually a `schema_ref`/`one_of` name not in `inventory.schemas`, or a malformed security scheme), re-assemble |
| `OUTPUT_MISMATCH` | error | Markdown ↔ OpenAPI disagree, **or** an integration `payload_ref`/`operation_ref`/signature wiring doesn't resolve (these three are `auto_fixable`) | for integration refs: point them at an existing schema/operation name. For md↔openapi: re-assemble after the upstream JSON is corrected |
| `REQUIRED_INFO_MISSING` | error **or** warning | a required piece is absent. ERROR: endpoint has no `method`, a real path has no `responses`, an endpoint has no `security` and no "no-auth" marker, a crypto signal with no detail, a missing `verify.field`. WARNING: missing `summary`/`examples`/`operational` | re-read the affected source scope and fill the JSON. A response entry does **not** require a provider-published HTTP status: use `status: "default"` with the cited universal envelope when HTTP status is silent. WARNING ones are reported gaps when the source is genuinely silent |
| `SOURCE_UNVERIFIED` | error (warning for an unsupported source) | a target can't be traced to a cited source | usually a missing/incorrect `source` on the entry — add/correct it. If the assertion truly has no source, fail-closed (remove / report). An *unsupported* source surfaces here as a non-blocking warning |
| `SOURCE_CONFLICT` | error | two sources disagree about the same target | re-read both; **report the conflict** — do not silently pick one |
| `UNSUPPORTED_ASSERTION` | error | the output asserts something no source states (speculation leaked in) | remove the unsupported content; fail-closed |

## Driving a correction round (default max 3 rounds; `--score` uses `--max-rounds`, default 6)

1. **Prefer the structured-routing fields.** `target_file` names where to edit
   (`inventory.json`, `integration.json`, or `endpoints/` — the *directory*; match the exact
   `ep<N>.json` by `requery_scope`'s `path.method`). `field_path` is the field inside it.
   `requery_scope` is the bounded source area to re-read. Fall back to parsing free-text
   `location` only when these are `null`.
2. **Dispatch a targeted read-only subagent** to re-read **only** that scope and return the
   corrected JSON (same subagent contract + grounding rule as extraction).
3. **You overwrite** the named file, then re-run `assemble`.
4. Each round overwrites the same `inventory.json` / `endpoints/*.json` / `integration.json`.

## Score-gated loop (`--score`)

Pass `--score --target-score <T> [--prev-score <P>] --round-index <R> --max-rounds <M>`
to make quality — not just "no errors" — the acceptance bar. The `--json` payload then
carries a `loop` block:

```json
{"loop": {"verdict": "continue", "target": 85, "prev_score": 72, "curr_score": 80,
  "round_index": 2, "max_rounds": 6,
  "actionable": [ {"code": "...", "location": "...", "suggested_fix": "...",
                   "score_impact": 12} ],
  "irreducible": [ {"code": "SOURCE_CONFLICT", "evidence": "...", "score_impact": 50} ]}}
```

`actionable`/`irreducible` items are `ScoreFinding` objects
(`code`/`location`/`evidence`/`suggested_fix`/`category`/`score_impact`) — they do **not**
carry the structured-routing fields. To route a re-read, match each `actionable` to its
`report.issues` entry by `code`+`location` and use that entry's
`requery_scope`/`target_file`/`field_path` (see "Driving a correction round" above).

Drive off `loop.verdict`:

| verdict | meaning | do |
|---|---|---|
| `continue` | below target, improved, rounds left, fixable work remains | for each `loop.actionable`, look up its `report.issues` entry (by `code`+`location`) to get `requery_scope`/`target_file`, re-read only `requery_scope` with a read-only subagent, overwrite `target_file`; re-run assemble with `--prev-score <curr_score>` and `--round-index <R+1>` |
| `converged` | `curr_score >= target` | stop — the run met the quality bar |
| `plateau` | below target but no improvement / nothing fixable left | stop — the deficit is irreducible from these sources; present `loop.irreducible` |
| `exhausted` | round cap hit without converging | stop — present `loop.irreducible` and any leftover `loop.actionable` |

**Never** re-read or edit an `irreducible` finding to raise the score — that is the
fail-closed boundary. `curr_score` from this round becomes the next `--prev-score`.
The score and its verdict never change assemble's exit code: a validation `error`
still exits 1 and still needs fixing regardless of verdict.

## Fail-closed

`SOURCE_CONFLICT`, `UNSUPPORTED_ASSERTION`, and `SOURCE_UNVERIFIED` (at `error`) that survive
genuine re-verification are **not** something to patch over. After re-reading the source and
confirming it truly doesn't support / conflicts, **present the remaining gaps/conflicts to the
user**. Never hard-code fill-ins; never fabricate to make validation pass.

## run_dir artifacts (full map)

**Product artifacts — confirm these exist after PASS:**

- `openapi.yaml`, `api-guide.zh-TW.md`, `review.html`, `provenance.json`
- `integration-contract.json` — **always** written. Empty `crypto`/`callbacks`/
  `field_conditions`/`test_cases` = "sources stated no integration mechanics"; its
  **emptiness, not its absence**, is the signal.
- `examples/<operationId>/request.{sh,ts,py}` + `examples/README.md` — **always** written when
  there is ≥1 endpoint. Values render as `<placeholder>` when the source states no example.
- `validation/report.json` + `validation/report.md`
- `preparation-report.json` + `preparation-report.md` — pre-generation readiness evidence.

**Scaffolding (present but not product):** `manifest.json`, `plan/normalization-plan.json`
(also linked from review.html), `extraction/queries.jsonl`, `extraction/answers/*.txt`.

## review.html sections

In order: scope-metric header (來源 / Endpoint / Webhook / Schema / Auth / 範例 / 核對風險
counts) · 產物入口 (artifact links) · 人工核對重點 (gaps: missing + conflicts + unverified) ·
Endpoint/Webhook table · Schema table · 環境與驗證 (environments + security schemes) ·
整合契約 (integration summary) · 來源清單 (source list).

**No validation summary is rendered inside the page** — it links to `validation/report.md`.
For PASS/FAIL and the issue list, read `validation/report.md` (or `report.json`), not
review.html.

## Exit codes

`0` = PASS · `1` = validation FAIL · `2` = either an **extraction input file error**
(`inventory.json`/`endpoints/*.json`/`integration.json` malformed or schema-invalid — fix the
named file/field; this includes an unrooted `endpoints[].path` and a file whose `source`
citations name no manifest source, both listed in one message) **or** a **run-dir collision** (the target `--output/<run_id>` already
exists — assemble refuses to overwrite; choose a fresh output root). Exit 2 is **not** a
validation round.
