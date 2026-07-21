# AGENTS.md

This file provides guidance to Codex (OpenAI Codex CLI) when working with code in this repository.

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

The stable product architecture now lives in `loop_apidoc/domain/`,
`loop_apidoc/core/`, `loop_apidoc/adapters/`, and `loop_apidoc/evaluation/`.
It is model/platform independent: runtime output is a claim/support proposal, Core
deterministically verifies claim-level `explicit_support` / `derived_support` /
`contradicts` / `insufficient` relationships and governs it, Domain owns the Canonical API
Contract IR and deterministic rules/projections,
and Evaluation is isolated from production mutation. The agent-native flow below remains
the current CLI compatibility adapter, not a product invariant. See
`docs/superpowers/specs/2026-07-20-model-independent-loop-apidoc-architecture-design.md`.

There is **one** extraction path: the current coding agent (Claude Code or Codex) is the extraction engine. Driven by `skills/loop-apidoc/SKILL.md`, it reads the sources via a subagent fan-out that is **read-only toward sources**: each **endpoint** subagent writes its own `endpoints/ep<N>.json` and returns a one-line summary, while the **inventory**/**integration** subagents return JSON that the orchestrating agent writes to `inventory.json` (+ optional `integration.json`). The orchestrator then verifies the extraction (`verify-extraction`, the same input gate `assemble` applies) before calling the deterministic CLI `assemble` for the shared **plan → generate → validate** back half.

`assemble` does **not** extract — it only assembles agent-written JSON (`manifest → plan → generate → validate`) and reports results via `--json` so the agent can drive the correction loop itself (re-reading sources and overwriting the JSON, then re-running `assemble`). `--architecture-mode shadow` opt-in runs the verified manifest + normalization plan through the model-independent Core after legacy validation and writes observational artifacts under `<run-dir>/core/`; shadow success or failure never changes legacy validation, score, approval, Foundry, run status, or exit code. The default `legacy` mode creates no `core/`.

The CLI commands include source acquisition, quality, assembly, analysis, and Foundry asset governance. In addition to catalog/HTML and direct-OpenAPI acquisition, `cache-gitbook-llms` fetches one GitBook `llms.txt` index and caches every safe same-origin, entry-prefix `.md` URL with immutable URL/SHA-256/timestamp sidecars and coverage. Index/output collisions fail before page writes; page fetch failures remain `fetch_failed`. `extract-markdown-drafts` reads manifest-named Markdown into non-authoritative, line-cited endpoint/table/example facts; it never writes extraction JSON and stays separate from `source_facts` validation. The final source-grounded path remains agent review → `verify-extraction` → `assemble`.

> A former `run-agent` CLI mode (subprocess `claude -p`) and a NotebookLM extraction backend were both retired in 2026-06; agent-native is now the only path.

## Package boundaries

| Package | Responsibility |
| --- | --- |
| `loop_apidoc/manifest/` | scan local sources + build `manifest.json` (`scanner.py` excludes non-spec furniture via `DEFAULT_EXCLUDES` + `--exclude` globs → `status: ignored`, never source evidence) |
| `loop_apidoc/url_catalog.py` | reproducible URL navigation catalog behind `catalog-url`/`select-url`: `fetch_catalog` (bounded HTTP GET of *one* entry page, size-capped, `CatalogFetchError`), `build_catalog` (parse only sidebar/nav lists into `CatalogNode`s — entry-page fragments kept as `anchor` section identities; links are recorded, never followed), `select_catalog` (pure filter by branch/term/URL; widens nothing, fetches nothing) |
| `loop_apidoc/url_corpus.py` | token-efficient cached URL corpus behind `cache-url-pages`/`cache-url-entry`/`related-url-pages`: `cache_catalog_pages` (fetch each catalog URL once — anchors of the same document become `sections` — and write content-addressed `raw/<sha256>.html` + `body/<sha256>.txt`; failures become `status: fetch_failed` entries, not exceptions), `extract_page_metadata` (pure: title/headings/body/internal links/`action:`+error-code entities from `<main>`), `find_related_pages` (pure evidence-based scoring — same branch / in-out links / shared entities — returning candidate cards without loading body text) |
| `loop_apidoc/gitbook_llms.py` | deterministic GitBook `llms.txt` filtering/cache with safe path preservation, URL sidecars, and coverage |
| `loop_apidoc/markdown_drafts/` | separate non-authoritative, line-cited Markdown endpoint/table/example drafts; never alters `source_facts` validation |
| `loop_apidoc/html_snapshot.py` | `normalize-html-snapshot`: `html_to_markdown` (pure: readable main-document text, no invented content) + `normalize_html_snapshot` (writes the Markdown and a `.source.json` sidecar binding it to the raw file's URL + sha256) |
| `loop_apidoc/source_quality/` | pre-extraction source quality gate behind `assess-sources`: `models.py` (`QualityObservation`/`QualityFinding`, `FindingSeverity`, verdict `pass`/`reject` + `SourceDiffReport`), `loader.py` (read side: manifest, agent-written observations JSON, and a completed assessment dir — `SourceQualityInputError`), `assess.py` (`assess_source_quality`, pure: manifest usability + observations → findings, any blocker ⇒ `reject`), `diff.py` (`build_source_diff`, pure manifest-vs-manifest added/removed/changed), `report.py` (`write_reports` → `source-quality-report.{json,zh-TW.md}` + `source-diff.{json,md}`). `assemble --source-quality` re-loads the reports: `reject` blocks assembly; a passing pair is copied into the run-dir's `source-quality/` |
| `loop_apidoc/freshness/` | cheap scheduled freshness gate behind `record-fingerprint`/`check-freshness`/`check-freshness-batch`: `models.py` (`SourceKind`/`SourceStatus`/`FreshnessVerdict`, `SourceSignal`/`FingerprintEntry`/`SourceFingerprint`, `SourceResult`/`FreshnessReport`, `Watchlist`/`WatchlistItem`, `BatchItemStatus`/`BatchItemResult`/`BatchReport`, `EXIT_CODES` verdict→exit-code map, `FreshnessInputError`), `signals.py` (pure `hash_bytes`/`file_signal`/OpenAPI-version detection + `classify` comparing an observed signal to a baseline entry; network `fetch_url_signal` — OpenAPI-URL sources compare `info.version`, HTML uses ETag/Last-Modified then body sha256 — writes nothing), `record.py` (`build_fingerprint` reads a completed run's manifest + URL coverage into a `SourceFingerprint`, `write_fingerprint` — WRITE exit, refuses overwrite without `force`), `check.py` (`check_freshness` orchestration: reads the baseline fingerprint, re-derives each source's current signal via `signals.py`, aggregates into a `FreshnessReport`; writes nothing), `batch.py` (`load_watchlist` — fail-loud parse of a `freshness-watchlist.json`; `scan_watchlist` — fans `check_freshness` over each watchlist item, capturing per-item errors into that item's `BatchItemResult` rather than aborting the batch, and aggregates into a `BatchReport`; writes nothing), `report.py` (`write_reports` → `freshness-report.{json,md}` — WRITE exit; also `render_batch_markdown`/`write_batch_reports` → `freshness-scan.{json,md}` — WRITE exit) |
| `loop_apidoc/agentcli/` | `assemble.py` (assemble agent-written JSON → plan→generate→validate, `AssembleInputError` / `RunDirectoryCollisionError`), `input_schema.py` (typed pydantic guards that validate agent-written extraction JSON at the assemble boundary, before any run dir is created), `source_guard.py` (pure boundary checks for the three schema contracts a subagent can't infer: `endpoints[].path` must start with `/`, each extraction file's `source` citations must name a manifest source — per-file scope, so a partially-citing file is left to validation's per-entry `SOURCE_UNVERIFIED` — and null-path endpoints must carry a `summary`), `cross_file.py` (pure cross-file invariants: endpoint files ↔ inventory — count, identity multiset (`(method, path)`, or `(method, summary)` for null-path webhooks), no duplicates, `schema_ref`/`security[]` resolution, `endpoints[].server` → `environments[].name` resolution), `gate.py` (`check_extraction`, the single aggregator `assemble` and `verify-extraction` both call — also folds in `source_facts`' semantic completeness and deferral checks, taking the `FactIndex` as an argument so it stays pure), `verify.py` (the `verify-extraction` shell: build manifest + load extraction + gate; writes nothing), `extraction.py` (convert `inventory.json` into plan stage answers), `preprocess.py` (PDF→markdown via pymupdf4llm) |
| `loop_apidoc/adapters/fragments.py` | read-side I/O exit that materializes exact page/line/section/table-cell/JSON Pointer fragments from source artifacts; fragment digests use normalized fragment content, not whole-document bytes |
| `loop_apidoc/shadow/` | opt-in legacy/Core compatibility sidecar: `models.py` (mode, diagnostics, comparison, summaries), `bridge.py` (pure manifest/plan → evidence/support proposals/metadata; filename-only legacy citations degrade to `insufficient`/unverified), `runner.py` (in-memory deterministic verification and evidence-aware projections through validate only), `report.py` (successful `core/*.json` plus `core/projections/`, or safe `core/error.json`; this package's only file-I/O exit) |
| `loop_apidoc/source_facts/` | deterministic source-fact inventory feeding the semantic completeness gate (issue #14): `models.py` (`EndpointFact`/`SourceFacts`/`FactIndex`, `by_identity()` keeping only the **intersection** when several sources document one `(METHOD, path)` — an overview index table or a deprecated v1 section would otherwise widen the requirement past what the extraction was right to ignore; ambiguity fails open), `markdown.py` (`scan_markdown`, pure: endpoint declarations, parameter-table field names — only tables whose first header cell is name-like, with nested-row decoration stripped and group-label rows skipped — and fenced example-block counts, fence-aware so code samples never leak facts. **Scope limit:** only well-structured Markdown yields facts; a flattened HTML-to-text dump yields none and the gate is a no-op on it — an accepted trade-off, since guessing structure would manufacture false facts and a false fact blocks a correct extraction), `collect.py` (`collect_facts`, the package's only read: manifest-named Markdown sources → `FactIndex`; unreadable sources are skipped, since manifest coverage already reports them), `gate.py` (`source_fact_violations`, pure: for every extracted endpoint that matches a fact by `(METHOD, path)`, a documented field absent from every structural position — and not named in `missing[]` — or a documented example with an empty `examples[]` is a violation; no match ⇒ no judgement), `deferral.py` (`deferral_violations`, pure: rejects placeholder answers like "requires further extraction"/「需進一步擷取」 outside `missing[]`) |
| `loop_apidoc/extraction/` | shared models + utilities (models, stages, questions, store, jsonblock) used by the agent extraction |
| `loop_apidoc/plan/` | normalization plan + source-match classification |
| `loop_apidoc/generate/` | OpenAPI / Markdown / `review.html` / provenance generation (`review.py` builds the offline manual-review page; `handoff.py`'s `build_handoff` emits the derived `handoff/` pack — `integration-tasks.md` / `postman_collection.json` / `sdk-hints.json` — from OpenAPI + plan + integration, duplicating no schema) |
| `loop_apidoc/validate/` | structure / completeness / consistency / no-speculation checks + report |
| `loop_apidoc/run/` | run-id generation, result/status models, and persisting the plan into the run dir |
| `loop_apidoc/diff/` | run-to-run version diff: `loader.py` (load a completed run-dir's artifacts, `DiffInputError`), `compare.py` (classify changes across `openapi.yaml` / `integration-contract.json` / `provenance.json` / `validation/report.json` / `manifest.json` into `breaking` / `additive` / `changed` / `source_only`), `models.py` (`DiffFinding` / `DiffImpact` / `DiffReport`), `report.py` (render + write `diff/report.{json,md}`) |
| `loop_apidoc/preparation/` | pre-generation readiness assessment: `assess.py` (`assess_preparation` grades `manifest` + inventory + endpoint texts + `plan` into a `PreparationReport` of phases/findings with severity `error`/`warning` and status `blocked`/`needs_attention`/`ready`; also `_assess_url_coverage` appends a **warning-only** `url_coverage` phase — expected-vs-fetched URL omission check — but only when the run has URL sources), `coverage.py` (`load_coverage`/`UrlCoverage`/`CoverageInputError`: the sole file-reading function in this package, parses + fail-loud validates the agent-written `url_sources/coverage.json` ledger), `report.py` (`write_reports` → `preparation-report.{json,md}`). Runs *inside* `assemble` between plan and generate; also read back by `diff/` as a supporting artifact |
| `loop_apidoc/score/` | deterministic documentation-quality score for a completed run-dir: `loader.py` (`load_score_inputs`, `ScoreInputError`), `evaluate.py` (`evaluate_score` — weighted categories openapi_validity / completeness / consistency / source_grounding / reviewability → 0–100, `ci` / `review` profiles), `report.py` (`write_reports` → `score/score.{json,md}`). Surfaced via the `score` command and `assemble --score`; **never** changes validation pass/fail or exit code |
| `loop_apidoc/foundry/` | project-local asset governance under `.foundry/api/`: `models.py` (Docset/Asset/Catalog/CurrentPointer + `FoundryInputError`/`FoundryApprovalError`), `paths.py` (pure `.foundry/api/` layout), `store.py` (governance-json read/write), `register.py` (`register_docset`), `importer.py` (`import_run` → copy a completed run into `candidates/<run-id>/`, gated by the reused `diff` loader), `approve.py` (`approve_candidate` → copy candidate into a versioned `assets/<asset-id>/artifacts/`, write `asset.json`, supersede the prior asset, update `current.json`/`docset.json`/`catalog.json`), `query.py` (downstream read side: `load_current_asset`/`resolve_current_artifact`/`list_docsets`), `cli.py` (`foundry` sub-app). Assets are self-contained copies; generation is untouched. |

**File-I/O exits:** only `generate/` (`generate_outputs`), `run/` (which owns the run-dir), `preparation/report.py` (`write_reports`, writes `preparation-report.{json,md}`), `score/report.py` (`write_reports`, writes `score/score.{json,md}`), `source_quality/report.py` (`write_reports`, writes the assessment reports — also called by `assemble` to retain a passing assessment in the run-dir), `url_corpus.py` (`cache_catalog_pages`, writes the `raw/`+`body/` corpus files), `html_snapshot.py` (`normalize_html_snapshot`, writes Markdown + sidecar), `foundry/store.py` (governance-json), `foundry/register.py`, `foundry/importer.py`, and `foundry/approve.py` (which copy run trees into `.foundry/`), `diff/report.py` (`write_reports`, writes `diff/report.{json,md}`), `freshness/record.py` (`write_fingerprint`, writes `source-fingerprint.json`), and `freshness/report.py` (`write_reports`/`write_batch_reports`, writes `freshness-report.{json,md}` and `freshness-scan.{json,md}`) write files (plus `cli.py` itself, which writes the catalog/selection/corpus/related-pages JSON outputs of the URL commands). The read-side exceptions are `preparation/coverage.py` (`load_coverage` reads the agent-written `url_sources/coverage.json`, writes nothing), `source_quality/loader.py` (reads manifest/observations/assessment reports, writes nothing), `agentcli/verify.py` (reads sources + the agent-written extraction dir, writes nothing), and `source_facts/collect.py` (`collect_facts` reads manifest-named Markdown sources, writes nothing); `url_catalog.py`'s `fetch_catalog` does network I/O but writes nothing, and so does `freshness/signals.py`'s `fetch_url_signal`; `freshness/check.py` (`check_freshness`) writes nothing (read-side orchestration), and neither does `freshness/batch.py` (`load_watchlist`/`scan_watchlist`). Every other module is pure functions — keep it that way; it's what makes them unit-testable.

`adapters/fragments.py` is a read-side I/O exit that reads source artifacts but writes
nothing. `shadow/report.py` is a file-I/O exit: it writes observational `core/*.json`,
`core/projections/*.json`, or `core/error.json`; the rest of `shadow/` stays pure or
in-memory.

## Correction & fail-closed classification

There is **no deterministic in-code correction loop** — `assemble` reports the validation result via `--json`; the agent drives correction itself (re-read sources → overwrite the extraction JSON → re-run `assemble`).

**The gate is severity, not the issue code:** a run FAILs iff it has any `error`-severity issue (`ValidationReport.ok`); `warning`s are reported gaps that don't block. The same code can be `error` or `warning` by context, so don't key blocking off the code. (`auto_fixable` is a per-issue bool set only for the three integration-reference mismatches; the `CorrectionCategory` enum is defined but unused — not a live taxonomy.)

How the agent responds, by intent:

- **Regenerate after fix** (`OPENAPI_INVALID`, `OUTPUT_MISMATCH`): invalid OpenAPI/Markdown or an unresolved integration `payload_ref`/`operation_ref` → correct the upstream JSON/reference, re-assemble.
- **Re-read & fill** (`REQUIRED_INFO_MISSING`, or `SOURCE_UNVERIFIED` from a missing citation): re-read the affected source scope and fill the JSON.
- **Fail-closed** (`SOURCE_CONFLICT`, `UNSUPPORTED_ASSERTION`, or `SOURCE_UNVERIFIED` surviving re-verification): present the remaining gaps/conflicts — **never fabricate**.

Per-code severity and the structured-routing fields (`target_file`/`field_path`/`requery_scope`) are documented in `skills/loop-apidoc/reference/assemble-and-correction.md`. The skill's other reference docs live alongside it in `skills/loop-apidoc/reference/`: `extraction-schemas.md`, `model-orchestration.md`, `source-quality.md`, and `url-fetching.md`.

## Provenance ↔ validation alignment

`provenance.json` `target` strings align **one-to-one** with OpenAPI locations (`paths.{path}.{method}`, `components.schemas.{name}`, `components.securitySchemes.{name}`). The no-speculation check cross-references these targets: anything entering the output must trace back to a source-grounded plan item, or it's a violation.

## Conventions

- Python `>=3.11`, managed with `uv` (no `pip`). Deps: typer, pydantic v2, httpx, pyyaml, openapi-spec-validator, jsonschema, pymupdf.
- Prefer immutable patterns (return new values; pure functions outside the I/O modules above).
- The skill file `skills/loop-apidoc/SKILL.md` is written in **English** (token economy); generated *product* output remains `zh-TW`.
- **Documentation language policy (for wider adoption/promotion):** teaching, promotion, and reference docs are **English-primary, Traditional-Chinese-secondary** — write the canonical copy in English so the project reaches the broadest audience, and provide zh-TW as the supporting/localized layer (e.g. `README.md` zh-TW ↔ `README.en.md` English). This applies to the human-facing docs listed under "Release: keep teaching & promotion docs in sync". The only content that stays `zh-TW`-first is *generated product output* (the `api-guide.zh-TW.md` guide and other run artifacts).

## Release: keep teaching & promotion docs in sync (non-negotiable)

A release is **not done** when `scripts/release.py prepare`/`tag` finish. That script only
synchronizes *version metadata* in a fixed set of files:
`pyproject.toml`, `loop_apidoc/__init__.py`, `.claude-plugin/plugin.json`, `uv.lock`,
`README.md`, `README.en.md`, `docs/introduction.html` (its version footer only),
`tests/test_plugin_manifest.py`, and it writes `docs/RELEASE_NOTES_<version>.md`.

Every **human-facing teaching / promotion document is NOT touched by that script** and
**MUST be reviewed and updated in the same release** whenever the change alters
user-facing behavior (new/renamed/removed command or flag, changed process, new feature,
new pipeline stage). These docs drift silently and are the first thing readers see:

- `docs/index.html` / `docs/introduction.html` — 「認識 loop-apidoc」landing/intro
- `docs/onboarding.html` — new-engineer technical tour
- `docs/operator-manual.html` — operator manual (commands & workflows)
- `docs/architecture-manual.html` — architecture manual
- `README.md` / `README.en.md` — command lists, examples, feature descriptions
  (their release-notes link is auto-bumped; their *body content* is not)
- `AGENTS.md` / `CLAUDE.md` — keep both agent-guidance files aligned with each other

Rule of thumb: if a code/process change would make any sentence, command example, or
feature list in the docs above wrong, fix it **in the same commit/release** — never defer.
Cross-check with `docs/RELEASE_CHECKLIST.md`.

## Benchmark harness contract

- A committed benchmark case is a `benchmarks/<case>/` directory containing both
  `extraction/inventory.json` and `expected/validation.expect.json`.
- `scripts/quality_gate.py::REQUIRED_BENCHMARK_CASES` is an explicit reviewed
  inventory. Adding or removing a committed fixture requires an intentional matching
  update; `test_required_benchmark_cases_match_committed_cases` enforces exact set
  parity.
- Discovery is CI-safe and must work without local source snapshots. Source-backed
  assertions require the original, dated, operator-provided and gitignored
  `benchmarks/<case>/sources/` snapshot.
- A skipped case has not passed source-backed revalidation. Never report a discovered or
  skipped case as passed.
- `uv run python scripts/quality_gate.py --strict-local` requires non-empty sources for
  every required case and rejects any benchmark skip. Only a zero-skip run may be
  described as strict-local passed.
- Never replace an unavailable historical snapshot with a newer document, synthetic
  fixture, or error page. Record the unavailable evidence, run deterministic CI checks,
  and perform a legitimate targeted source-backed spot-check instead.
- The canonical four-layer model, thirteen-case inventory, terminology, and case-addition
  workflow are in `docs/BENCHMARK_VALIDATION_PLAN.md`.

## Further docs

- Architecture + data flow (with diagrams): `docs/ARCHITECTURE.md`
- Design spec: `docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md`
- Stage implementation plans: `docs/superpowers/plans/`
- Contributing: `CONTRIBUTING.md`
- CI workflow: `.github/workflows/ci.yml`; release checklist: `docs/RELEASE_CHECKLIST.md`
- Pipeline follow-ups (post-benchmark improvements): `docs/PIPELINE_FOLLOWUPS.md`
