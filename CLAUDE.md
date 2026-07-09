# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`loop-apidoc` is a **source-grounded API documentation pipeline**: it turns heterogeneous API integration docs (PDF/MD/HTML/OpenAPI JSON/public URLs) into standardized, traceable artifacts — OpenAPI 3.1 YAML, a Traditional-Chinese Markdown guide (`api-guide.zh-TW.md`), an offline manual review page (`review.html`), `provenance.json`, and a `validation/report.{json,md}`.

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

The six generation/analysis CLI commands are `preprocess` (PDF→markdown), `manifest` (scan), `assemble` (assemble + validate; optional `--score`), `validate` (validate an existing run-dir), `score` (grade a completed run-dir's documentation quality), and `diff` (compare two completed run-dirs by downstream impact). A separate `foundry` sub-app (`init` / `import` / `approve` / `list` / `current`) manages the project-local `.foundry/api/` asset layer — importing completed runs as docset candidates and promoting them to approved, versioned assets with a deterministic `current` pointer.

> A former `run-agent` CLI mode (subprocess `claude -p`) and a NotebookLM extraction backend were both retired in 2026-06; agent-native is now the only path.

## Package boundaries

| Package | Responsibility |
| --- | --- |
| `loop_apidoc/manifest/` | scan local sources + build `manifest.json` (`scanner.py` excludes non-spec furniture via `DEFAULT_EXCLUDES` + `--exclude` globs → `status: ignored`, never source evidence) |
| `loop_apidoc/agentcli/` | `assemble.py` (assemble agent-written JSON → plan→generate→validate, `AssembleInputError` / `RunDirectoryCollisionError`), `input_schema.py` (typed pydantic guards that validate agent-written extraction JSON at the assemble boundary, before any run dir is created), `extraction.py` (convert `inventory.json` into plan stage answers), `preprocess.py` (PDF→markdown via pymupdf4llm) |
| `loop_apidoc/extraction/` | shared models + utilities (models, stages, questions, store, jsonblock) used by the agent extraction |
| `loop_apidoc/plan/` | normalization plan + source-match classification |
| `loop_apidoc/generate/` | OpenAPI / Markdown / `review.html` / provenance generation (`review.py` builds the offline manual-review page; `handoff.py`'s `build_handoff` emits the derived `handoff/` pack — `integration-tasks.md` / `postman_collection.json` / `sdk-hints.json` — from OpenAPI + plan + integration, duplicating no schema) |
| `loop_apidoc/validate/` | structure / completeness / consistency / no-speculation checks + report |
| `loop_apidoc/run/` | run-id generation, result/status models, and persisting the plan into the run dir |
| `loop_apidoc/diff/` | run-to-run version diff: `loader.py` (load a completed run-dir's artifacts, `DiffInputError`), `compare.py` (classify changes across `openapi.yaml` / `integration-contract.json` / `provenance.json` / `validation/report.json` / `manifest.json` into `breaking` / `additive` / `changed` / `source_only`), `models.py` (`DiffFinding` / `DiffImpact` / `DiffReport`), `report.py` (render + write `diff/report.{json,md}`) |
| `loop_apidoc/preparation/` | pre-generation readiness assessment: `assess.py` (`assess_preparation` grades `manifest` + inventory + endpoint texts + `plan` into a `PreparationReport` of phases/findings with severity `error`/`warning` and status `blocked`/`needs_attention`/`ready`; also `_assess_url_coverage` appends a **warning-only** `url_coverage` phase — expected-vs-fetched URL omission check — but only when the run has URL sources), `coverage.py` (`load_coverage`/`UrlCoverage`/`CoverageInputError`: the sole file-reading function in this package, parses + fail-loud validates the agent-written `url_sources/coverage.json` ledger), `report.py` (`write_reports` → `preparation-report.{json,md}`). Runs *inside* `assemble` between plan and generate; also read back by `diff/` as a supporting artifact |
| `loop_apidoc/score/` | deterministic documentation-quality score for a completed run-dir: `loader.py` (`load_score_inputs`, `ScoreInputError`), `evaluate.py` (`evaluate_score` — weighted categories openapi_validity / completeness / consistency / source_grounding / reviewability → 0–100, `ci` / `review` profiles), `report.py` (`write_reports` → `score/score.{json,md}`). Surfaced via the `score` command and `assemble --score`; **never** changes validation pass/fail or exit code |
| `loop_apidoc/foundry/` | project-local asset governance under `.foundry/api/`: `models.py` (Docset/Asset/Catalog/CurrentPointer + `FoundryInputError`/`FoundryApprovalError`), `paths.py` (pure `.foundry/api/` layout), `store.py` (governance-json read/write), `register.py` (`register_docset`), `importer.py` (`import_run` → copy a completed run into `candidates/<run-id>/`, gated by the reused `diff` loader), `approve.py` (`approve_candidate` → copy candidate into a versioned `assets/<asset-id>/artifacts/`, write `asset.json`, supersede the prior asset, update `current.json`/`docset.json`/`catalog.json`), `query.py` (downstream read side: `load_current_asset`/`resolve_current_artifact`/`list_docsets`), `cli.py` (`foundry` sub-app). Assets are self-contained copies; generation is untouched. |

**File-I/O exits:** only `generate/` (`generate_outputs`), `run/` (which owns the run-dir), `preparation/report.py` (`write_reports`, writes `preparation-report.{json,md}`), `score/report.py` (`write_reports`, writes `score/score.{json,md}`), `foundry/store.py` (governance-json), `foundry/register.py`, `foundry/importer.py`, and `foundry/approve.py` (which copy run trees into `.foundry/`), and `diff/report.py` (`write_reports`, writes `diff/report.{json,md}`) write files. The one read-side exception is `preparation/coverage.py` (`load_coverage` reads the agent-written `url_sources/coverage.json`, writes nothing). Every other module is pure functions — keep it that way; it's what makes them unit-testable.

## Correction & fail-closed classification

There is **no deterministic in-code correction loop** — `assemble` reports the validation result via `--json`; the agent drives correction itself (re-read sources → overwrite the extraction JSON → re-run `assemble`).

**The gate is severity, not the issue code:** a run FAILs iff it has any `error`-severity issue (`ValidationReport.ok`); `warning`s are reported gaps that don't block. The same code can be `error` or `warning` by context, so don't key blocking off the code. (`auto_fixable` is a per-issue bool set only for the three integration-reference mismatches; the `CorrectionCategory` enum is defined but unused — not a live taxonomy.)

How the agent responds, by intent:

- **Regenerate after fix** (`OPENAPI_INVALID`, `OUTPUT_MISMATCH`): invalid OpenAPI/Markdown or an unresolved integration `payload_ref`/`operation_ref` → correct the upstream JSON/reference, re-assemble.
- **Re-read & fill** (`REQUIRED_INFO_MISSING`, or `SOURCE_UNVERIFIED` from a missing citation): re-read the affected source scope and fill the JSON.
- **Fail-closed** (`SOURCE_CONFLICT`, `UNSUPPORTED_ASSERTION`, or `SOURCE_UNVERIFIED` surviving re-verification): present the remaining gaps/conflicts — **never fabricate**.

Per-code severity and the structured-routing fields (`target_file`/`field_path`/`requery_scope`) are documented in `skills/loop-apidoc/reference/assemble-and-correction.md`.

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
- CI workflow: `.github/workflows/ci.yml`; release checklist: `docs/RELEASE_CHECKLIST.md`
- Pipeline follow-ups (post-benchmark improvements): `docs/PIPELINE_FOLLOWUPS.md`
