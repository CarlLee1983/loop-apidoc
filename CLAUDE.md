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

When invoked from inside the installed plugin, the CLI is called as
`uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc <command>`.

## Two execution modes (key architecture)

The back half of the pipeline (**plan → generate → validate**) is one shared deterministic pipeline. The modes differ *only* in **who acts as the extraction engine**:

| Mode | Entry command | Extraction engine | Code |
| --- | --- | --- | --- |
| coding-agent CLI | `run-agent` | subprocess `claude -p` (or other agent CLI via `--executable`) | `agentcli/` |
| agent-native plugin | `assemble` (called by the skill) | the current Claude agent reads sources itself | `agentcli/`, `skills/` |

Both modes converge extraction into `inventory.json` + `endpoints/*.json`, then hand off to the shared plan→generate→validate. `assemble` does **not** extract — it only assembles agent-written JSON and reports results via `--json` so the agent can drive the correction loop itself (re-reading sources and overwriting the JSON).

## Package boundaries

| Package | Responsibility |
| --- | --- |
| `loop_apidoc/manifest/` | scan local sources + build `manifest.json` |
| `loop_apidoc/agentcli/` | coding-agent CLI extraction (`run-agent`) + `assemble`, subprocess runner / error types / `AskResult` / answer-quality detection, PDF→markdown preprocessing (pymupdf4llm) |
| `loop_apidoc/extraction/` | shared models + utilities (models, stages, questions, store, jsonblock) used by the agent extraction modes |
| `loop_apidoc/plan/` | normalization plan + source-match classification |
| `loop_apidoc/generate/` | OpenAPI / Markdown / provenance generation |
| `loop_apidoc/validate/` | structure / completeness / consistency / no-speculation checks + report |
| `loop_apidoc/run/` | run-id generation, result/status models, and persisting the plan into the run dir |

**Single file-I/O exit:** only `generate/` (`generate_outputs`) and `run/` (which owns the run-dir) write files. Every other module is pure functions — keep it that way; it's what makes them unit-testable.

## Correction & fail-closed classification

Validation issues are classified, not blindly retried. In the agent modes there is **no deterministic in-code correction loop** — `assemble` reports the classified results via `--json` and the agent drives correction itself (re-reading sources and overwriting the extraction JSON), then re-running `assemble`.

- `OPENAPI_INVALID` / `OUTPUT_MISMATCH` → fixable (regenerate after the agent corrects the JSON)
- `REQUIRED_INFO_MISSING` → the agent re-reads the affected sources and fills the gap
- `SOURCE_UNVERIFIED` / `SOURCE_CONFLICT` / `UNSUPPORTED_ASSERTION` → **unfixable, fail-closed** — reported as remaining gaps/conflicts rather than fabricating content.

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
