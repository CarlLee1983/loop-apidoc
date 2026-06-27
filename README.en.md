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

Extraction queries NotebookLM through the [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill). That skill drives NotebookLM via local browser automation; each question is an independent session with no conversational context, so every query carries full context (notebook identity, known summary, open items, expected output format).

The pipeline does **not** create the notebook, upload sources, or log into private sites — those are manual prerequisites (below).

### Full flow

```
manifest → extraction (multi-round NotebookLM) → normalization plan → generate (OpenAPI + Markdown) → validate → correction (max 3 rounds)
```

When validation fails, the pipeline classifies issues from the report, attempts fixes, and re-validates — up to 3 rounds. After 3 rounds it emits a gap/conflict report and exits non-zero.

---

## Run as a Claude Code plugin (agent-native)

Besides the CLI, this project is also a Claude Code plugin: invoke the
`loop-apidoc` skill inside a Claude session, give it one or more sources (local
files or public URLs), and the agent extracts them itself, calls
`loop-apidoc assemble` to assemble and validate, and re-fills missing fields
automatically when validation fails (up to 3 rounds).

This mode uses neither NotebookLM nor a nested `claude -p`; the current agent is
the extraction engine. The bundled CLI is invoked via
`uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc assemble`.

---

## Install

Requires Python `>=3.11` and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
uv run loop-apidoc --help
```

Extraction also needs a local checkout of the NotebookLM skill (default dir `notebooklm-skill`; override with `--skill-root` or `LOOP_APIDOC_SKILL_ROOT`). Run `doctor` first to check readiness.

---

## Manual prerequisites

These steps are **not** part of the CLI:

1. Create a NotebookLM notebook.
2. Add all source documents and public URLs to the notebook.
3. Get the notebook's share link.
4. Keep a local source directory mirroring the notebook contents.

The notebook must be reachable by the Google account logged into the local browser; insufficient sharing or permissions cause the CLI to fail at the NotebookLM preflight.

### Supported source formats (v1)

PDF, Markdown, Microsoft Word, OpenAPI JSON/YAML, public URLs.

---

## Usage

### `run` — full pipeline

```bash
uv run loop-apidoc run \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --sources ./sources \
  --output ./output
```

| Option | Description |
| --- | --- |
| `--notebook-url` | NotebookLM share link (required) |
| `--sources` | Local source directory (required) |
| `--output` | Output root; a `<run-id>` subdir is created under it (required) |
| `--url` | Public source URL, repeatable |
| `--skill-root` | notebooklm-skill checkout dir (default `notebooklm-skill`) |

Defaults: output language `zh-TW`, OpenAPI 3.1, max 3 correction rounds, no-speculation enabled.

Exit code: `0` only when validation passes (`PASSED`); other statuses (`failed` / `early-stopped` / `blocked`) exit non-zero.

### `doctor` — environment check

```bash
uv run loop-apidoc doctor
```

Checks Python, the NotebookLM skill, skill dependencies, Chrome, browser auth status, and required validation tools. **Read-only** — never modifies the notebook or outputs. Exits `0` when ready, `1` otherwise.

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

---

## Output layout

Each execution uses an isolated run directory:

```text
output/
└── <run-id>/                    # run-id format: %Y%m%dT%H%M%SZ
    ├── manifest.json            # source manifest
    ├── extraction/
    │   ├── queries.jsonl        # per-round query log
    │   └── answers/             # raw extraction artifacts (kept per round, never overwritten)
    ├── plan/
    │   └── normalization-plan.json   # machine-readable normalization plan
    ├── openapi.yaml             # OpenAPI 3.1
    ├── api-guide.zh-TW.md       # Traditional Chinese integration guide
    ├── provenance.json          # per-output source traceability
    └── validation/
        ├── report.json
        └── report.md
```

Only content that is both present in the plan and source-grounded reaches the OpenAPI and Markdown outputs. OpenAPI fields that are required but missing from sources are filled with a minimal legal placeholder, marked `x-loop-status: missing-source` plus a provenance gap record; if the gap affects integrability, completeness validation still fails.

---

## Validation rules at a glance

| Category | What it checks |
| --- | --- |
| **Structure** | OpenAPI 3.1 validity; every endpoint must have a method, path, and at least one response |
| **Completeness** | `unverified` sources, missing required fields, and manifest coverage gaps (e.g. unreadable sources) fail validation |
| **Consistency** | The endpoint set and security names must agree across OpenAPI, Markdown, and provenance |
| **No speculation** | Every output item must map to a provenance source; unsupported content is a violation |

The correction loop classifies issues: `OPENAPI_INVALID` / `OUTPUT_MISMATCH` → auto-fix; `REQUIRED_INFO_MISSING` → re-query (only the relevant stages); `SOURCE_UNVERIFIED` / `SOURCE_CONFLICT` / `UNSUPPORTED_ASSERTION` → not auto-fixable (fail-closed, loop stops early).

---

## Development

```bash
uv run pytest                    # full suite (248 passed + 1 skipped)
uv run pytest --cov=loop_apidoc  # with coverage
uv run ruff check .              # lint
```

Real-NotebookLM smoke tests are marked `smoke` and run only with `LOOP_APIDOC_SMOKE=1`.

### Package layout

| Package | Responsibility |
| --- | --- |
| `loop_apidoc/manifest/` | Source scanning and manifest building |
| `loop_apidoc/notebooklm/` | NotebookLM skill adapter (wraps only `auth_status` + `ask`), retry, error classification |
| `loop_apidoc/doctor/` | Read-only environment checks |
| `loop_apidoc/extraction/` | Multi-round querying, answer persistence, JSON-block parsing |
| `loop_apidoc/plan/` | Normalization plan building and source-matching classification |
| `loop_apidoc/generate/` | OpenAPI / Markdown / provenance generation (sole file-I/O exit) |
| `loop_apidoc/validate/` | Structure / completeness / consistency / no-speculation validation and reports |
| `loop_apidoc/run/` | run-id, correction loop, full pipeline orchestration |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for diagrams and data flow.

---

## Design docs

Full design and per-phase implementation plans live under `docs/superpowers/`:

- System design: [`specs/2026-06-25-loop-api-documentation-pipeline-design.md`](docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md)
- Implementation plans: `docs/superpowers/plans/`
