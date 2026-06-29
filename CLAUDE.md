# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`loop-apidoc` is a **source-grounded API documentation pipeline**: it turns heterogeneous API integration docs (PDF/MD/HTML/OpenAPI JSON/public URLs) into standardized, traceable artifacts — OpenAPI 3.1 YAML, a Traditional-Chinese Markdown guide (`api-guide.zh-TW.md`), `provenance.json`, and a `validation/report.{json,md}`.

It ships as **both** a Python CLI and an agent-native skill. The repo root is a Claude Code plugin (see `.claude-plugin/` and `skills/loop-apidoc/SKILL.md`); the same `SKILL.md` is portable and also loads under the OpenAI Codex CLI — it abstracts the CLI call behind an `<APIDOC>` placeholder (`$CLAUDE_PLUGIN_ROOT` set → bundled `uv run --project`; otherwise → globally-installed `loop-apidoc`).

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

## Execution model: agent-native (key architecture)

There is **one** extraction path: the current coding agent (Claude Code or Codex) is the extraction engine. Driven by `skills/loop-apidoc/SKILL.md`, it reads the sources via a **read-only subagent fan-out** (each subagent only reads/searches and returns JSON — never writes), the orchestrating agent writes the returned JSON to `inventory.json` + `endpoints/*.json`, then calls the deterministic CLI `assemble` for the shared **plan → generate → validate** back half.

`assemble` does **not** extract — it only assembles agent-written JSON (`manifest → plan → generate → validate`) and reports results via `--json` so the agent can drive the correction loop itself (re-reading sources and overwriting the JSON, then re-running `assemble`).

The four CLI commands are `preprocess` (PDF→markdown), `manifest` (scan), `assemble` (assemble + validate), and `validate` (validate an existing run-dir).

> A former `run-agent` CLI mode (subprocess `claude -p`) and a NotebookLM extraction backend were both retired in 2026-06; agent-native is now the only path.

## Package boundaries

| Package | Responsibility |
| --- | --- |
| `loop_apidoc/manifest/` | scan local sources + build `manifest.json` |
| `loop_apidoc/agentcli/` | `assemble.py` (assemble agent-written JSON → plan→generate→validate, `AssembleInputError` / `RunDirectoryCollisionError`), `input_schema.py` (typed pydantic guards that validate agent-written extraction JSON at the assemble boundary, before any run dir is created), `extraction.py` (convert `inventory.json` into plan stage answers), `preprocess.py` (PDF→markdown via pymupdf4llm) |
| `loop_apidoc/extraction/` | shared models + utilities (models, stages, questions, store, jsonblock) used by the agent extraction |
| `loop_apidoc/plan/` | normalization plan + source-match classification |
| `loop_apidoc/generate/` | OpenAPI / Markdown / provenance generation |
| `loop_apidoc/validate/` | structure / completeness / consistency / no-speculation checks + report |
| `loop_apidoc/run/` | run-id generation, result/status models, and persisting the plan into the run dir |

**Single file-I/O exit:** only `generate/` (`generate_outputs`) and `run/` (which owns the run-dir) write files. Every other module is pure functions — keep it that way; it's what makes them unit-testable.

## Correction & fail-closed classification

Validation issues are classified, not blindly retried. There is **no deterministic in-code correction loop** — `assemble` reports the classified results via `--json` and the agent drives correction itself (re-reading sources and overwriting the extraction JSON), then re-running `assemble`.

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
