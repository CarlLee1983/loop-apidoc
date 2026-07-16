# loop-apidoc

> Loop Engineering's **source-grounded API documentation pipeline**

*繁體中文版見 [README.md](README.md)。*

`loop-apidoc` is a repeatable CLI that turns API integration documents of varying formats and completeness into consistent, traceable standardized artifacts:

- **OpenAPI 3.1 YAML** (`openapi.yaml`)
- **Traditional Chinese Markdown integration guide** (`api-guide.zh-TW.md`)
- **Offline manual review page** (`review.html`)
- **Source provenance** (`provenance.json`)
- **Validation & gap report** (`validation/report.{json,md}`)

Core principle: **source documents are the only source of truth**. Anything the sources do not provide is never guessed; when required information is missing, validation fails and lists the gaps explicitly rather than filling them in by convention.

---

## Why loop-apidoc

### The reality of integration docs

Third-party API documentation (payments, gaming, logistics…) comes in wildly different shapes: scanned PDFs, marketing-site HTML, Word attachments, half-finished OpenAPI files. A single spec is often scattered across several documents with unsynchronized versions. Manual consolidation is slow and lossy — and the result cannot answer "which page of which document says this field exists?", so integration bugs cannot be audited and doc revisions cannot be compared.

loop-apidoc consolidates these heterogeneous sources into one canonical form: OpenAPI 3.1 + a zh-TW guide + provenance (every statement points back to its source location) + a validation report. Whatever is missing or contradictory is stated explicitly; the artifacts can be `diff`ed, promoted into governed assets via `foundry`, and rebuilt at any time.

### Why it matters for vibe coding

Vibe coding hands implementation to a coding agent — and the agent's output quality is bounded by the quality of the spec you feed it:

- **Raw documents breed hallucinations.** Feed a PDF or web page directly to an agent and it fills every gap with "common conventions": assuming OAuth, RESTful defaults, standard error envelopes. When the target is a payment API, these plausible-looking guesses are the most expensive bugs you can ship. loop-apidoc's fail-closed principle turns "the source doesn't say" into an explicitly listed gap instead of creative freedom for the agent.
- **Agents need machine-readable ground truth.** `openapi.yaml`, `integration-contract.json`, and `examples/` are specs an agent can consume directly — cheaper in tokens than re-reading dozens of PDF pages every session, reproducible, and every agent in every project reads the **same facts**.
- **Humans must be able to audit what the agent relied on.** Provenance points every statement back to its source, and `review.html` supports offline manual review — vibe coding is not hands-off; it moves the human role from "writing every line" to "reviewing the spec and the artifacts", which requires traceability.
- **A spec is an asset, not a one-off prompt.** `foundry` promotes a completed run into a versioned asset (the `current` pointer under `.foundry/api/`), and `diff` classifies doc revisions by downstream impact — every vibe-coding iteration stands on the same governed spec instead of re-deriving it from scratch.

### How is this different from just asking an AI agent to organize the PDF/URL?

The extraction engine here **is also a model** (agent-native: the current coding agent does the reading). The difference is not "AI or no AI" — it is the ring of **deterministic engineering** around the model:

| | Asking an agent directly | loop-apidoc |
| --- | --- | --- |
| Output correctness | Self-asserted by the model, unchecked | The model's output is only *input*; it must pass deterministic gates: `verify-extraction` cross-file invariants → structure/completeness/consistency/**no-speculation** checks, or the run FAILs |
| Hallucination | Gaps get filled with REST/OAuth conventions that *look* right | Fail-closed is machine-enforced: anything entering the OpenAPI must trace back to a source-grounded plan item, or `UNSUPPORTED_ASSERTION`/`SOURCE_UNVERIFIED` blocks it |
| Auditability | Prose; you cannot ask "which page says this?" | `provenance.json` aligns one-to-one with OpenAPI locations; `review.html` supports manual review |
| Reproducibility | Different every session | The back half is a deterministic CLI: the same extraction JSON always produces the same artifacts |
| Omission detection | Long documents get read as far as they get read; silent gaps | URL coverage ledger (expected vs fetched), preparation readiness, endpoint count/identity cross-checks — omissions get named |
| Correction | "Try again", with no guarantee of convergence | Typed issues (severity gate + `target_file`/`field_path`/`requery_scope` routing) drive a correction loop with converged/plateau verdicts |
| Revisions & governance | Ask again; nothing to compare against | `diff` classifies by downstream impact, `score` quantifies quality, `foundry` versions the asset |
| Evidence | None | A regression harness of real-provider benchmarks; early runs caught 6 defects on the first validation pass — exactly the errors direct summarization ships silently |

**Both approaches have their place — honestly:**

- **Asking an agent directly**: zero setup, instant results. For **quickly understanding** what a document says, or one-off low-stakes exploration, it is entirely sufficient — using loop-apidoc there is overkill.
- **loop-apidoc**: you run a full pipeline (extraction JSON → validation → correction loop), so the upfront cost and token spend are higher. In exchange you get verifiable, auditable, reproducible, governable output. Worth it for **integrations that ship to production** (especially payment-grade, where a wrong guess is expensive), specs shared across projects/agents, and documents that keep revising and need impact tracking.

Rule of thumb: **if the result will be written into production code, gate it; if you just need to understand the document, just ask.**

In one sentence: **vibe coding made "writing code" fast, so "getting the spec right" became the new bottleneck — loop-apidoc is built to remove exactly that bottleneck. It uses the model without trusting it: the model reads; whether it is *right* is decided by deterministic code that cannot hallucinate.**

---

## How it works

The extraction engine is **the current coding agent itself**: inside a Claude Code plugin or OpenAI Codex CLI session, the agent follows the `loop-apidoc` skill to read sources via a **subagent fan-out that is read-only toward sources** — the main agent writes `inventory.json` (plus an optional `integration.json`) while each endpoint subagent writes its own `endpoints/ep<N>.json` — checks the extraction contract with `verify-extraction`, then calls the deterministic CLI `assemble` for the back half (plan → generate → validate).

### Full flow

```
preprocess (optional) → extraction (agent read-only subagent fan-out) → verify-extraction (contract check) → manifest → normalization plan → generate (OpenAPI + Markdown) → validate
```

Validation emits a classified issue report. Correction is **agent-driven**: `assemble` reports results via `--json`, the agent re-reads the affected sources, overwrites the extraction JSON, and re-runs `assemble` — until it passes or an issue is deemed an unfixable gap/conflict.

---

## Run as a Claude Code plugin (agent-native)

Besides the CLI, this project is also a Claude Code plugin: invoke the `loop-apidoc` skill inside a Claude session, give it one or more sources (local files or public URLs), and the agent extracts them itself, calls `loop-apidoc assemble` to assemble and validate, and drives its own correction loop when validation fails — re-reading sources and re-filling missing fields.

The current agent is the extraction engine (the only extraction path). After installing the plugin it is available in Claude Code; the bundled CLI is invoked via `uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc assemble`.

### Use it in the OpenAI Codex CLI

The same skill also runs under Codex. Codex does not set `${CLAUDE_PLUGIN_ROOT}`, so install the CLI globally and mount the skill into Codex's skills directory:

```bash
# 1. Install the CLI as a global loop-apidoc command (replaces the plugin's bundled uv run --project)
uv tool install --from /path/to/loop-apidoc loop-apidoc

# 2. Mount the skill into Codex (a symlink is enough; edits sync automatically)
ln -s /path/to/loop-apidoc/skills/loop-apidoc ~/.codex/skills/loop-apidoc
```

`SKILL.md` resolves the environment via the `<APIDOC>` placeholder: with `$CLAUDE_PLUGIN_ROOT` it uses the bundled CLI, otherwise it falls back to the global `loop-apidoc`. The rest of the flow (extract → `assemble` → validate → correct) is identical on both.

### Agent delivery levels

Before reading sources, the skill explains and asks for `minimal` (the default), `review`,
`handoff`, or `full`. `minimal` only has the agent deliver and pass along OpenAPI,
provenance, validation results, and an integration contract when needed; unselected derived
artifacts stay out of agent context and agent handoffs to reduce token use. This is an agent
delivery policy and does not change CLI source grounding, validation, or the compatible run
directory structure.

Release notes: [`0.9.3`](docs/RELEASE_NOTES_0.9.3.md).

---

## Install

Requires Python `>=3.11` and [`uv`](https://docs.astral.sh/uv/).

```bash
# install dependencies
uv sync

# confirm the CLI runs
uv run loop-apidoc --help
```

---

## Supported source formats

PDF, Markdown, Microsoft Word, OpenAPI JSON/YAML, static HTML snapshots, public URLs.

---

## Usage

### `manifest` — build source manifest

```bash
uv run loop-apidoc manifest --sources ./sources [--url <URL> ...] [--output manifest.json]
```

Scans local sources recording relative path, format, size, SHA-256, scan time, support status, duplicate detection, and processing status; public URLs also record fetch time, HTTP status, and content hash. Without `--output`, prints to stdout.

### `catalog-url` / `select-url` — index navigation before fetching pages

```bash
# Downloads the entry page once; it never follows sidebar links.
uv run loop-apidoc catalog-url \
  --url "https://docs.example.com/api/introduction" \
  --output ./work/url_sources/catalog.json

# Select a document branch and topic. This also does not download page bodies.
uv run loop-apidoc select-url \
  --catalog ./work/url_sources/catalog.json \
  --branch "Transfer wallet" --term "cash" \
  --output ./work/url_sources/selection.json
```

`catalog.json` is the complete navigation **coverage universe**. `selection.json` can
be a human-specified starting point for model review; it does not have to limit the
tool-side cache.

When page retrieval is cheap but model context is expensive, cache the catalog and
give the model only candidate cards:

```bash
uv run loop-apidoc cache-url-pages \
  --catalog ./work/url_sources/catalog.json \
  --output ./work/url_corpus

uv run loop-apidoc related-url-pages \
  --corpus ./work/url_corpus/corpus.json \
  --url "https://docs.example.com/api/action19" \
  --output ./work/action19-candidates.json
```

`cache-url-pages` stores raw HTML and navigation-free body text while producing
headings, internal-link, and entity metadata without calling a model. `corpus.json`
does not embed bodies; `related-url-pages` returns compact cards with breadcrumb,
score, and evidence reason. Load a candidate `body_file` only when the model needs it.

For static single-page docs, sidebar anchors are kept as catalog-node `anchor`s and
listed as `sections` on the corpus's single entry-page card (the same HTML is downloaded
once). When the catalog is empty or there is no sidebar, use
`cache-url-entry --url ... --output ...` to cache the entry page directly. Already-downloaded
HTML can be converted into supported Markdown with
`normalize-html-snapshot --input page.html --url ... --output sources/page.md`; the command
writes a `.source.json` provenance sidecar carrying the original URL and SHA-256. HTML
itself is also listed as a supported format in the manifest.

### Model division in Codex and Claude Code

The skill is model-neutral: the host maps a fast model to candidate routing, a standard
model to bounded single-page extraction, and a high-reasoning model to cross-page review.
The CLI remains responsible for fetching, parsing, provenance, coverage, and validation.
Pass artifact paths and compact summaries between roles; never use a larger model context as a
reason to send the whole corpus. See
[`model-orchestration.md`](skills/loop-apidoc/reference/model-orchestration.md) for the role
matrix, hand-off contract, and Codex/Claude mapping.

### `assess-sources` — pre-extraction source-quality assessment

```bash
uv run loop-apidoc assess-sources \
  --sources ./sources --manifest ./work/manifest.json \
  --observations ./work/source-observations.json \
  --source-set "<source set name>" \
  --output ./work/source-quality [--base-manifest <old manifest>]
```

Before extraction, grades the manifest plus the agent-recorded source observations into a source-quality report (`source-quality-report.{json,zh-TW.md}`) and a source-version diff (`source-diff.{json,md}`, compared against an old manifest when `--base-manifest` is given). The verdict is `pass` or `reject`; exit codes: `0` = pass, `1` = reject, `2` = bad input file. The output directory can be passed to `assemble --source-quality`: a `reject` verdict stops before a run-dir is created, while a `pass` report is preserved with the run-dir for audit.

### `validate` — validate an existing run directory

```bash
uv run loop-apidoc validate --output ./output/<run-id>
```

Runs structure / completeness / consistency / no-speculation validation over the run directory and writes reports to `<run-dir>/validation/`. Exits `0` on pass, `1` when there are ERROR-level issues.

### `score` — evaluate document quality of an existing run directory

```bash
uv run loop-apidoc score --output ./output/<run-id> [--profile ci|review] [--min-score 85] [--json]
```

Reads the existing run directory's `validation/report.json`, `openapi.yaml`, `provenance.json`, `manifest.json`, and optional `plan/normalization-plan.json`, and outputs `score/score.json` and `score/score.md`. The `ci` profile defaults to a threshold of `85`, and `review` defaults to `70`. Exit codes: `0` = pass, `1` = needs_attention / fail, `2` = run-dir input error.

### `diff` — compare two runs for a version delta

```bash
uv run loop-apidoc diff --base ./output/<old-run> --head ./output/<new-run>
```

Compares two completed run directories and emits a diff report classified by downstream impact. Writes to `<new-run>/diff/report.{json,md}` by default; pass `--output` to choose another directory. Changes are classified as `breaking`, `additive`, `changed`, or `source_only`, and the comparison spans `openapi.yaml`, `integration-contract.json`, `provenance.json`, `validation/report.json`, and `manifest.json`. The first version does not diff the Markdown guide or generated examples. Exits `0` on completion, `2` when an input run-dir is missing files or malformed.

### `foundry` — local asset governance for API projects

```bash
uv run loop-apidoc foundry [init|import|approve|list|current] --help
```

Subcommands to manage docsets, import a run directory as a candidate, and approve an asset to update the `current` pointer. Ideal for scenarios requiring manual review and release management of API documentation versions.

### `preprocess` — convert PDFs to high-fidelity markdown (optional)

```bash
uv run loop-apidoc preprocess --sources ./sources --out ./work/sources_md
```

Uses pymupdf4llm to convert every PDF under `--sources` into markdown that preserves tables and heading structure (non-PDF text sources are copied verbatim). Convert table-heavy or large PDFs before extraction to avoid table distortion from raw PDF reads, then point extraction subagents at `--out`.

### `verify-extraction` — check the extraction JSON against the contract

```bash
uv run loop-apidoc verify-extraction \
  --sources ./sources --extraction ./work [--url <URL> ...] [--json]
```

Before calling `assemble`, checks the agent-produced extraction directory (`inventory.json` + `endpoints/*.json`, optional `integration.json`) with the same input gate `assemble` applies: schema, source citations, and cross-file invariants. **Writes nothing and creates no run directory.** Exit codes: `0` = clean, `2` = violations or hard schema errors (never `1` — `1` is reserved for validate FAIL). `--json` prints the violations as a JSON array to stdout for the agent to parse.

### `assemble` — assemble from agent-produced extraction JSON (invoked by the skill)

```bash
uv run loop-apidoc assemble \
  --sources ./sources \
  --extraction ./work \
  --output ./output \
  [--url <URL> ...] [--url-coverage ./work/url_sources/coverage.json] \
  [--source-quality ./work/source-quality] [--json] [--score]
```

Does **not** extract; it assembles outputs from an extraction directory the agent already produced (`inventory.json` + `endpoints/*.json`, plus an optional `integration.json` signing/crypto contract): manifest → plan → generate → validate. When passed an `assess-sources` output directory through `--source-quality`, a `reject` verdict stops before a run directory is created; a `pass` report and source diff are preserved in the run directory for audit and Foundry retention. `--json` prints `run_id`, `run_dir`, `review_html`, `ok`, `status`, and `report` to stdout for the agent to parse and drive the correction loop. Exit codes: `0` = validation PASS, `1` = validation FAIL, `2` = bad extraction input file. This is the command the [agent-native plugin](#run-as-a-claude-code-plugin-agent-native) mode invokes. With `--score`, `assemble` additionally writes `score/score.json` and `score/score.md` after assembling; the exit code keeps its validation semantics. When the run has URL sources, pass the agent-recorded `url_sources/coverage.json` fetch ledger via `--url-coverage` and `assemble` performs a warning-only URL coverage check (it never affects the validation severity gate). The score self-loop flags `--target-score` / `--prev-score` / `--round-index` / `--max-rounds` let the agent use the reported loop verdict to decide whether to run another correction round.

---

## Output layout

Each execution uses an isolated run directory:

```text
output/
└── <run-id>/                       # run-id format: %Y%m%dT%H%M%S.%fZ (microseconds avoid same-second collisions)
    ├── manifest.json               # source manifest
    ├── extraction/                 # extraction audit trail (not re-runnable input)
    │   ├── queries.jsonl           # per-round query records
    │   └── answers/                # per-query responses <query_id>.txt
    ├── plan/
    │   └── normalization-plan.json      # machine-readable normalization plan
    ├── openapi.yaml                # OpenAPI 3.1
    ├── api-guide.zh-TW.md          # Traditional Chinese integration guide
    ├── review.html                 # offline HTML page for manual artifact review
    ├── provenance.json             # per-output source traceability
    ├── integration-contract.json   # signing/crypto integration contract (when sources provide one)
    ├── examples/                   # per-endpoint curl / TypeScript / Python request examples (when produced)
    ├── handoff/                    # developer handoff aids (derived artifacts, not a contract source)
    │   ├── integration-tasks.md    # implementation order / runtime config / blocker checklist
    │   ├── postman_collection.json # Postman v2.1 request-shape collection (importable)
    │   └── sdk-hints.json          # per-endpoint hints for SDK / client scaffolding
    ├── validation/
    │   ├── report.json
    │   └── report.md
    ├── source-quality/              # preserved when --source-quality is supplied
    │   ├── source-quality-report.json
    │   ├── source-quality-report.zh-TW.md
    │   ├── source-diff.json
    │   └── source-diff.md
    ├── score/                       # documentation quality score (loop-apidoc score or assemble --score)
    │   ├── score.json
    │   └── score.md
    └── diff/                       # when diffed against another run (loop-apidoc diff)
        ├── report.json
        └── report.md
```

`handoff/` holds derived engineering guidance and tooling adapters; the **contract sources remain `openapi.yaml` and `integration-contract.json`** — it never duplicates schema.

> Note: the agent-produced extraction input (`inventory.json` + `endpoints/*.json` + optional `integration.json`) lives in the working directory passed to `--extraction`, **not** in the run-dir. The run-dir `extraction/` only holds the audit trail (`queries.jsonl` + `answers/`).

Only content that is both present in the plan and source-grounded reaches the OpenAPI and Markdown outputs. OpenAPI fields that are required but missing from sources are filled with a minimal legal placeholder, marked `x-loop-status: missing-source` plus a provenance gap record; if the gap affects integrability, completeness validation still fails.

When the sources provide an error-code table, `components.schemas.ErrorCode` — in addition to the existing enum and `x-loop-error-codes` — emits `x-loop-error-code-map`, preserving each code's message/description, HTTP-status metadata, source citations, and the source-stated applicable operations (since 0.9.2; purely additive and backward compatible).

---

## Validation rules at a glance

| Category | What it checks |
| --- | --- |
| **Structure** | OpenAPI 3.1 validity; every endpoint must have a method, path, and at least one response |
| **Completeness** | `unverified` sources, missing required fields, and manifest coverage gaps (e.g. unreadable sources) fail validation |
| **Consistency** | The endpoint set and security names must agree across OpenAPI, Markdown, and provenance |
| **No speculation** | Every output item must map to a provenance source; unsupported content is a violation |

Validation classifies issues: `OPENAPI_INVALID` / `OUTPUT_MISMATCH` → fixable by regeneration; `REQUIRED_INFO_MISSING` → the agent re-reads the relevant sources to fill the gap; `SOURCE_UNVERIFIED` / `SOURCE_CONFLICT` / `UNSUPPORTED_ASSERTION` → not fixable (fail-closed, reported as gaps/conflicts). Correction is driven by the agent from the `assemble --json` report (re-reading sources and overwriting the extraction JSON, then re-running), not by an in-CLI loop.

---

## Development

```bash
# run tests
uv run pytest

# with coverage
uv run pytest --cov=loop_apidoc

# lint
uv run ruff check .
```

### Package layout

| Package | Responsibility |
| --- | --- |
| `loop_apidoc/manifest/` | Source scanning and manifest building |
| `loop_apidoc/agentcli/` | `assemble.py` (assemble agent-written extraction JSON → plan→generate→validate), `verify.py` (`verify-extraction`: check the extraction JSON with assemble's input gate, writes nothing), `extraction.py` (convert `inventory.json` into plan stage answers), `preprocess.py` (PDF→markdown via pymupdf4llm) |
| `loop_apidoc/extraction/` | Shared models and utilities for agent extraction (models, stages, questions, store, jsonblock) |
| `loop_apidoc/plan/` | Normalization plan building and source-matching classification |
| `loop_apidoc/generate/` | OpenAPI / Markdown / provenance generation (a file-I/O exit) |
| `loop_apidoc/validate/` | Structure / completeness / consistency / no-speculation validation and reports |
| `loop_apidoc/run/` | run-id generation, result/status models, and persisting the plan into the run dir |
| `loop_apidoc/diff/` | run-to-run version diff: load run artifacts, classify changes (`breaking` / `additive` / `changed` / `source_only`), render and write `diff/report.{json,md}` |
| `loop_apidoc/preparation/` | preparation readiness reporting inside assemble |
| `loop_apidoc/score/` | documentation quality scoring for completed run-dirs |
| `loop_apidoc/source_quality/` | pre-extraction source-quality assessment and source-version diffs; passing reports can be retained with a run-dir |
| `loop_apidoc/url_catalog.py` / `url_corpus.py` | bounded URL navigation cataloging, page caching, and related-page candidates for local-evidence web reading |
| `loop_apidoc/foundry/` | local asset governance, managing docsets, candidates, and approved assets |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for diagrams and data flow.

---

## Design docs

- Architecture overview and data flow (with diagrams): [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Contributing guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- System design spec: [`docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md`](docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md)
- Per-phase implementation plans: `docs/superpowers/plans/`
