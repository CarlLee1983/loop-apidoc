# loop-apidoc

> Loop Engineering's **source-grounded API documentation pipeline**

*繁體中文版見 [README.md](README.md)。*

`loop-apidoc` is a repeatable CLI that turns API integration documents of varying formats and completeness into consistent, traceable standardized artifacts:

- **OpenAPI 3.1 YAML** (`openapi.yaml`)
- **Traditional Chinese Markdown integration guide** (`api-guide.zh-TW.md`)
- **Source provenance** (`provenance.json`)
- **Validation & gap report** (`validation/report.{json,md}`)

Core principle: **source documents are the only source of truth**. Anything the sources do not provide is never guessed; when required information is missing, validation fails and lists the gaps explicitly rather than filling them in by convention.

---

## How it works

The extraction engine is **the current coding agent itself**: inside a Claude Code plugin or OpenAI Codex CLI session, the agent follows the `loop-apidoc` skill to read sources via a **read-only subagent fan-out**, writes the results to `inventory.json` + `endpoints/*.json`, then calls the deterministic CLI `assemble` for the back half (plan → generate → validate).

### Full flow

```
preprocess (optional) → extraction (agent read-only subagent fan-out) → manifest → normalization plan → generate (OpenAPI + Markdown) → validate
```

Validation emits a classified issue report. Correction is **agent-driven**: `assemble` reports results via `--json`, the agent re-reads the affected sources, overwrites the extraction JSON, and re-runs `assemble` — until it passes or an issue is deemed an unfixable gap/conflict.

---

## Run as a Claude Code plugin (agent-native)

Besides the CLI, this project is also a Claude Code plugin: invoke the `loop-apidoc` skill inside a Claude session, give it one or more sources (local files or public URLs), and the agent extracts them itself, calls `loop-apidoc assemble` to assemble and validate, and re-fills missing fields automatically when validation fails (up to 3 rounds).

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

PDF, Markdown, Microsoft Word, OpenAPI JSON/YAML, public URLs.

---

## Usage

### `preprocess` — convert PDFs to high-fidelity markdown (optional)

```bash
uv run loop-apidoc preprocess --sources ./sources --out ./work/sources_md
```

Uses pymupdf4llm to convert every PDF under `--sources` into markdown that preserves tables and heading structure (non-PDF text sources are copied verbatim). Convert table-heavy or large PDFs before extraction to avoid table distortion from raw PDF reads, then point extraction subagents at `--out`.

### `manifest` — build source manifest

```bash
uv run loop-apidoc manifest --sources ./sources [--url <URL> ...] [--output manifest.json]
```

Scans local sources recording relative path, format, size, SHA-256, scan time, support status, duplicate detection, and processing status; public URLs also record fetch time, HTTP status, and content hash. Without `--output`, prints to stdout.

### `validate` — validate an existing run directory

```bash
uv run loop-apidoc validate --output ./output/<run-id>
```

Runs structure / completeness / consistency / no-speculation validation over the run directory and writes reports to `<run-dir>/validation/`. Exits `0` on pass, `1` when there are ERROR-level issues.

### `assemble` — assemble from agent-produced extraction JSON (invoked by the skill)

```bash
uv run loop-apidoc assemble \
  --sources ./sources \
  --extraction ./work \
  --output ./output \
  [--url <URL> ...] [--json]
```

Does **not** extract; it assembles outputs from an extraction directory the agent already produced (`inventory.json` + `endpoints/*.json`, plus an optional `integration.json` signing/crypto contract): manifest → plan → generate → validate. `--json` prints `run_id`, `run_dir`, `ok`, `status`, and `report` to stdout for the agent to parse and drive the correction loop. Exit codes: `0` = validation PASS, `1` = validation FAIL, `2` = bad extraction input file. This is the command the [agent-native plugin](#run-as-a-claude-code-plugin-agent-native) mode invokes.

---

## Output layout

Each execution uses an isolated run directory:

```text
output/
└── <run-id>/                       # run-id format: %Y%m%dT%H%M%SZ
    ├── manifest.json               # source manifest
    ├── extraction/                 # extraction audit trail (not re-runnable input)
    │   ├── queries.jsonl           # per-round query records
    │   └── answers/                # per-query responses <query_id>.txt
    ├── plan/
    │   └── normalization-plan.json      # machine-readable normalization plan
    ├── openapi.yaml                # OpenAPI 3.1
    ├── api-guide.zh-TW.md          # Traditional Chinese integration guide
    ├── provenance.json             # per-output source traceability
    ├── integration-contract.json   # signing/crypto integration contract (when sources provide one)
    ├── examples/                   # per-endpoint curl / TypeScript / Python request examples (when produced)
    └── validation/
        ├── report.json
        └── report.md
```

> Note: the agent-produced extraction input (`inventory.json` + `endpoints/*.json` + optional `integration.json`) lives in the working directory passed to `--extraction`, **not** in the run-dir. The run-dir `extraction/` only holds the audit trail (`queries.jsonl` + `answers/`).

Only content that is both present in the plan and source-grounded reaches the OpenAPI and Markdown outputs. OpenAPI fields that are required but missing from sources are filled with a minimal legal placeholder, marked `x-loop-status: missing-source` plus a provenance gap record; if the gap affects integrability, completeness validation still fails.

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
| `loop_apidoc/agentcli/` | `assemble.py` (assemble agent-written extraction JSON → plan→generate→validate), `extraction.py` (convert `inventory.json` into plan stage answers), `preprocess.py` (PDF→markdown via pymupdf4llm) |
| `loop_apidoc/extraction/` | Shared models and utilities for agent extraction (models, stages, questions, store, jsonblock) |
| `loop_apidoc/plan/` | Normalization plan building and source-matching classification |
| `loop_apidoc/generate/` | OpenAPI / Markdown / provenance generation (sole file-I/O exit) |
| `loop_apidoc/validate/` | Structure / completeness / consistency / no-speculation validation and reports |
| `loop_apidoc/run/` | run-id generation, result/status models, and persisting the plan into the run dir |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for diagrams and data flow.

---

## Design docs

Full design and per-phase implementation plans live under `docs/superpowers/`:

- System design: [`specs/2026-06-25-loop-api-documentation-pipeline-design.md`](docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md)
- Implementation plans: `docs/superpowers/plans/`
