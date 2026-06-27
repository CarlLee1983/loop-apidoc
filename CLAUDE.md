# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`loop-apidoc` is a **source-grounded API documentation pipeline**: it turns heterogeneous API integration docs (PDF/MD/HTML/OpenAPI JSON/public URLs) into standardized, traceable artifacts — OpenAPI 3.1 YAML, a Traditional-Chinese Markdown guide (`api-guide.zh-TW.md`), `provenance.json`, and a `validation/report.{json,md}`.

It ships as **both** a Python CLI and a Claude Code plugin (this repo's root is the plugin; see `.claude-plugin/` and `skills/loop-apidoc/SKILL.md`).

**Core invariant (non-negotiable):** the source documents are the *only* source of truth. Anything a source does not state is left `null` and recorded in `missing` — never inferred, never filled with REST/OAuth conventions. Validation fails loudly on missing required info rather than guessing.

## Commands

```bash
uv sync                                    # install deps
uv run loop-apidoc --help                  # CLI entry (pyproject [project.scripts])
uv run pytest                              # run tests
uv run pytest --cov=loop_apidoc            # with coverage
uv run pytest tests/test_cli_assemble.py   # single test file
uv run pytest -k assemble                  # single test by name
uv run ruff check .                        # lint
```

Real-NotebookLM smoke tests are gated behind the `smoke` marker and only run with `LOOP_APIDOC_SMOKE=1`.

When invoked from inside the installed plugin, the CLI is called as
`uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc <command>`.

## Three execution modes (key architecture)

The back half of the pipeline (**plan → generate → validate → correct**) is one shared deterministic pipeline. The modes differ *only* in **who acts as the extraction engine**:

| Mode | Entry command | Extraction engine | Code |
| --- | --- | --- | --- |
| NotebookLM | `run` | NotebookLM multi-round queries (local browser automation) | `run/`, `extraction/`, `notebooklm/` |
| coding-agent CLI | `run-agent` | subprocess `claude -p` (or other agent CLI) | `agentcli/` |
| agent-native plugin | `assemble` (called by the skill) | the current Claude agent reads sources itself | `agentcli/`, `skills/` |

Both agent modes converge extraction into `inventory.json` + `endpoints/*.json`, then hand off to the shared plan→generate→validate. `assemble` does **not** extract — it only assembles agent-written JSON and reports results via `--json` so the agent can drive the correction loop.

## Package boundaries

| Package | Responsibility |
| --- | --- |
| `loop_apidoc/manifest/` | scan local sources + build `manifest.json` |
| `loop_apidoc/notebooklm/` | NotebookLM skill adapter (wraps `auth_status` + `ask`), retry, error classification |
| `loop_apidoc/agentcli/` | coding-agent CLI extraction (`run-agent`) + `assemble`, PDF→markdown preprocessing |
| `loop_apidoc/doctor/` | read-only environment checks |
| `loop_apidoc/extraction/` | multi-round queries, answer persistence, JSON-block parsing |
| `loop_apidoc/plan/` | normalization plan + source-match classification |
| `loop_apidoc/generate/` | OpenAPI / Markdown / provenance generation |
| `loop_apidoc/validate/` | structure / completeness / consistency / no-speculation checks + report |
| `loop_apidoc/run/` | run-id, correction loop, full pipeline orchestration |

**Single file-I/O exit:** only `generate/` (`generate_outputs`) and `run/` (which owns the run-dir) write files. Every other module is pure functions — keep it that way; it's what makes them unit-testable.

## Correction loop & fail-closed classification

Validation issues are classified, not blindly retried (max 3 rounds):

- `OPENAPI_INVALID` / `OUTPUT_MISMATCH` → auto-fix (regenerate)
- `REQUIRED_INFO_MISSING` → re-query (only the affected stage)
- `SOURCE_UNVERIFIED` / `SOURCE_CONFLICT` / `UNSUPPORTED_ASSERTION` → **unfixable, fail-closed** — the loop stops early and reports remaining gaps/conflicts rather than fabricating content.

After 3 rounds still failing, the pipeline exits non-zero with the gap/conflict report.

## Provenance ↔ validation alignment

`provenance.json` `target` strings align **one-to-one** with OpenAPI locations (`paths.{path}.{method}`, `components.schemas.{name}`, `components.securitySchemes.{name}`). The no-speculation check cross-references these targets: anything entering the output must trace back to a source-grounded plan item, or it's a violation.

## Conventions

- Python `>=3.11`, managed with `uv` (no `pip`). Deps: typer, pydantic v2, httpx, pyyaml, openapi-spec-validator, jsonschema, pymupdf.
- Prefer immutable patterns (return new values; pure functions outside the I/O modules above).
- The skill file `skills/loop-apidoc/SKILL.md` is written in **English** (token economy); generated *product* output remains `zh-TW`.

## Further docs

- Architecture + data flow (with diagrams): `docs/ARCHITECTURE.md`
- Design spec: `docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md`
- Stage implementation plans: `docs/superpowers/plans/`
- Contributing: `CONTRIBUTING.md`
