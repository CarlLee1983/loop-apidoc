# AGENTS.md

This file provides guidance to Codex (OpenAI Codex CLI) when working with code in this repository.

## Warrant

This repository follows Warrant. Work is bounded by human-approved intent and
proven by this repository's own verification.

**Verification command:** `make verify`

1. **Intent is approved by a human.** Work starts from a Story at
   `specs/stories/<slug>.md` with Goal, Out of Scope, and Acceptance Criteria.
   A Story is approved only when a human has committed it to the default
   branch, or has explicitly assigned it in the current session. When it is
   not committed and the human only asks you to implement it, ask once whether
   they approve it as written; only a yes counts. A Story you
   drafted or committed yourself is not approved: stop and wait. Approval is
   not a work queue; the human chooses which Story to do.
2. **Completion is proven by evidence.** Run the verification command above and
   repair failures until it passes; if the repair lies outside the Story, stop
   and report it. Map every acceptance criterion to a reproducible observation:
   the command you ran and its output, or the `file:line` you inspected. If no
   verification command is declared, report that and stop; do not choose
   checks yourself.
3. **The standard is not yours to change.** Do not change requirements, weaken
   or reinterpret acceptance criteria, delete or skip failing tests, edit the
   Story to fit the work, or widen scope. When work outside the Story is
   needed, or a criterion conflicts with Out of Scope, stop and report it.

Finish with a completion report of three sections: (1) each acceptance
criterion → command run → observed result; (2) skipped or blocked checks;
(3) residual risks. An inference or substitute check is not an observation.
If the verification command did not pass, or any criterion lacks a passing
observation, the report says **partial**, never done.

Directories under `specs/stories/` are legacy records, not pending work.

## Code Quality

* Follow the repository's existing formatter, lint, type, and architecture
  settings.
* Do not disable, bypass, or weaken existing rules merely to obtain PASS.
* Keep new code consistent with neighboring code and the existing architecture.
* Treat `make verify` as the authority for every automated judgment.
* Leave design judgments that cannot be automated to Human Review.

## What this is

`loop-apidoc` is a **source-grounded API documentation pipeline**: its current compatibility flow turns heterogeneous API integration docs into OpenAPI artifacts. The Core also owns protocol-neutral contracts and deterministic GraphQL/AsyncAPI compilers, but those formats have no public run integration until a named downstream consumer establishes the required source and acceptance contract. Every supported run retains a Traditional-Chinese guide, offline review page, provenance, and validation reports.

It ships as **both** a Python CLI and an agent-native skill. The repo root is a Claude Code plugin (see `.claude-plugin/` and `skills/loop-apidoc/SKILL.md`); the same `SKILL.md` is portable and also loads under the OpenAI Codex CLI — it abstracts the CLI call behind an `<APIDOC>` placeholder (`$CLAUDE_PLUGIN_ROOT` set → bundled `uv run --project`; otherwise → globally-installed `loop-apidoc`).

**Core invariant (non-negotiable):** supplier sources are the sole authority for normative, provider-documented claims. Anything a source does not state is left `null` and recorded in `missing` — never inferred, never filled with REST/OAuth conventions. Validation fails loudly on missing required info rather than guessing. Passive Implementation Observations form a separate empirical conformance axis for one exact Applicability Envelope; they never become supplier-source support or mutate the Normative Contract.

## Commands

```bash
uv sync                                    # install deps
uv run loop-apidoc --help                  # CLI entry (pyproject [project.scripts])
uv run loop-apidoc review --help           # local Foundry review workbench
uv run pytest                              # run tests
uv run pytest --cov=loop_apidoc            # with coverage
uv run pytest tests/test_cli_assemble.py   # single test file
uv run pytest -k assemble                  # single test by name
uv run ruff check .                        # lint
npm run docs:check                         # verify Markdown docs against local evidence
```

## Graft usage

For repository orientation, feature discovery, cross-file changes, dependency
analysis, and refactoring:

- Use `graft_repo_map` before exploring an unfamiliar area.
- Use `graft_find_code` before broad manual file searches.
- Use `graft_file_api` before reading an entire large file.
- Use `graft_trace_calls` before changing public symbols or contracts.
- Use `graft_find_all` when exhaustive matching is required.
- Run `graft_check_freshness` after code changes.
- Fall back to native file search when Graft results are incomplete.

## Development workflow: test-driven development

For every behavior-changing feature or bug fix, use a vertical **Red → Green →
Verify** loop. Documentation-only changes and purely mechanical release-version updates
do not need a Red phase, but still require an appropriate consistency check.

1. **Agree the seam first.** Before writing a test, identify the public behavior being
   exercised — for example a CLI command/exit code, a public pure function, a typed
   model contract, a generated artifact, or a persisted report. State that seam and get
   requester confirmation; do not test private helpers or internal call sequences.
2. **Red.** Add one focused regression or feature test at that seam with an independently
   known expected result. Run the targeted test and confirm it fails for the missing or
   incorrect behavior, rather than because of fixture/setup errors.
3. **Green.** Make the smallest production change that makes that one test pass. Do not
   pre-build speculative behavior for later cases or weaken source-grounding rules to
   satisfy a test.
4. **Repeat in small slices.** Each additional observable behavior gets its own
   Red → Green cycle. Keep tests as refactor-resistant behavioral specifications; avoid
   mocks of private collaborators and assertions derived by reimplementing production
   logic in the test.
5. **Verify.** Run the affected test module(s), then the proportionate regression suite
   and `uv run ruff check .`. For a bug fix, keep the reproducing test permanently.

For source-backed benchmarks, TDD fixtures must still obey the benchmark harness contract:
never substitute a newer, synthetic, or error-page document for unavailable historical
source evidence.

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
`docs/ARCHITECTURE.md` and `docs/DESIGN_DECISIONS.md`.

There is **one** extraction path: the current coding agent (Claude Code or Codex) is the extraction engine. Driven by `skills/loop-apidoc/SKILL.md`, it reads the sources via a subagent fan-out that is **read-only toward sources**: each **endpoint** subagent writes its own `endpoints/ep<N>.json` and returns a one-line summary, while the **inventory**/**integration** subagents return JSON that the orchestrating agent writes to `inventory.json` (+ optional `integration.json`). The orchestrator then verifies the extraction (`verify-extraction`, the same input gate `assemble` applies) before calling the deterministic CLI `assemble` for the shared **plan → generate → validate** back half. Extraction entries may additionally carry optional v1 `evidence[]` references (exact manifest source identity, typed locator, normalized fragment digest, claim path); both gates materialize them through the fragment adapter and resolve the path against the shared plan projection before a run exists, and any stale, ambiguous, or unmatched reference fails closed.

Before that fan-out, the mandatory compatibility order is **acquisition/preprocess → manifest
→ `inspect-source-risk` → agent quality review → `assess-sources --source-risk` →
extraction**. No router, reviewer, or extractor reads source-derived text before the risk pass.
The exact readable package—not the original binary when PDF/Word required conversion—owns the
manifest and audit binding. `--source-quality` is a required `assemble` option: it rebuilds the
manifest and revalidates the embedded stable source-risk binding before it creates a run
directory, so an unaudited run is refused — which is not a proof of when an agent read source
text outside this process.

`--focus` is an optional input to both `verify-extraction` and `assemble`. Requester-authored directives are broadcast into every extraction subagent's prompt and answered exactly once in `<extraction>/focus-response.json`; a directive's `kind` is the sole determinant of severity, its `intent` the sole determinant of anchor type, and the only outcomes are `satisfied` (anchors carrying mandatory v1 exact evidence — filename-only citations are refused here) and `not_found` (which must account for every readable manifest source). There is deliberately no "not applicable" outcome. Structural violations join the shared extraction gate and fail before a run directory exists; a falsified Expectation Directive is instead an error-severity `FOCUS_UNMET` validation issue so the run's artifacts survive for the operator to judge. A `collect_error_codes` answer is additionally judged against the **documented error-code floor** — the codes a Markdown source tabulates are a deterministic lower bound, so reporting fewer is a `FOCUS_INCOMPLETE` validation issue naming the omitted codes and where each is documented, with severity again from `kind`; reporting more still passes, and sources with no recognisable table yield no floor and no judgement (ADR 0005). `verify-extraction` forecasts a shortfall without entering `--json` or changing its exit code. A directive never licenses inferring anything, and focus material never reaches provenance, the score, or Foundry (ADR 0004).

`assemble` does **not** extract — it only assembles agent-written JSON (`manifest → plan → generate → validate`) and reports results via `--json` so the agent can drive the correction loop itself (re-reading sources and overwriting the JSON, then re-running `assemble`). `--architecture-mode shadow` opt-in runs the verified manifest + normalization plan through the model-independent Core after legacy validation and writes observational artifacts under `<run-dir>/core/`; shadow success or failure never changes legacy validation, score, approval, Foundry, run status, or exit code. `--architecture-mode strict` is the separate blocking path: every legacy-supported material claim must re-verify against exact evidence before it atomically writes an unapproved Core candidate; strict rejection fails the run and strict execution errors block it. Foundry revalidates the strict execution and candidate bindings before import or human approval, and `--allow-failing` cannot bypass that gate. The default `legacy` mode creates no `core/`.

The CLI commands include source acquisition, quality, assembly, analysis, and Foundry asset governance. In addition to catalog/HTML and direct-OpenAPI acquisition, `cache-gitbook-llms` fetches one GitBook `llms.txt` index and caches every safe same-origin, entry-prefix `.md` URL with immutable URL/SHA-256/timestamp sidecars and coverage. Index/output collisions fail before page writes; page fetch failures remain `fetch_failed`. `extract-markdown-drafts` reads manifest-named Markdown into non-authoritative, line-cited endpoint/table/example facts; `scaffold-extraction` projects those facts into extraction-shaped JSON under a dedicated output directory. A fresh scaffold is never the blessed `--extraction` input: agents copy its inventory/endpoints into the real workdir, re-read citations, and fill security/integration/missing gaps before verification. Neither command alters `source_facts` validation. The final source-grounded path remains agent review → `verify-extraction` → `assemble`.

> A former `run-agent` CLI mode (subprocess `claude -p`) and a NotebookLM extraction backend were both retired in 2026-06; agent-native is now the only path.

## Package boundaries

Per-package responsibilities live in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#套件職責表) (`### 套件職責表`); read it before changing which package owns what.

**File-I/O exits** include `generate/` (`generate_outputs`), `run/` (which owns the legacy run-dir), `agentcli/preprocess.py`, report writers for preparation, score, source risk, source quality, diff, freshness, governance, focus, and feedback, URL-corpus, HTML-snapshot, rendered-URL acquisition, DOCX source reads (`docx_normalization.py`) and staged publication (`docx_publish.py`), and Foundry descriptor persistence, namespace management, mutable-head publication, and approval publication (including write-once feedback inputs and appended governance records). `review/workflow.py` writes through `foundry/`'s writers rather than by its own call, which is why the mechanical inventory below does not list it. `foundry/integrity.py` is the deliberate shared bounded read adapter for governed artifact bytes; it does not replace the public `foundry/query.py` read seam. `core/conformance.py`, `core/conformance_policy.py`, `domain/conformance.py`, `docx_validation.py`, and `docx_render.py` remain pure. `commands/acquisition.py` writes the manifest and catalog/selection/corpus/related-pages command outputs, and `commands/drafts.py` writes the Markdown-draft command outputs. The read-side exceptions include `focus/loader.py`, `feedback/loader.py`, `foundry/query.py`, `foundry/effective_binding.py` (package-internal, held-descriptor verification only), `foundry/integrity.py`, `url_coverage.py`, `rendered_url.py`'s provenance verifier, `source_risk/inspect.py`, `source_risk/loader.py`, `source_quality/loader.py`, `agentcli/verify.py`, `agentcli/evidence.py`, `source_facts/collect.py`, and `review/binding.py`; public Effective lineage traversal is centralized in `foundry/query.py`, while its private binding helper never opens a project path. `url_catalog.py` and `freshness/signals.py` may perform network reads but write nothing. `url_safety.py` resolves DNS and writes nothing: it is the single egress gate every outbound fetch passes through — `safe_client()` validates the caller's own URL *and* each redirect hop in a `request` event hook, so a fetcher cannot forget to check and cannot be bypassed by a 302 into a private address (issue #155). The criterion is written beside it: HTTP(S) scheme, no userinfo, and *every* resolved address globally routable. The same module owns the write side (issue #156): `RedactedUrl` is an annotated type whose serializer strips credential values on the way to disk, so a URL stays whole in memory — a fetcher reads it off the model before fetching — and is redacted only when an artifact is written. Which *names* denote a credential is `privacy.py`'s question, not this module's. A URL in an artifact is evidence unless the pipeline reads that artifact back to fetch from it; the one instruction artifact, `catalog.json`, keeps its URLs whole and is held out of Git by the hygiene roots instead (ADR 0015). URL identity is redaction-invariant — `rendered_url.canonicalize_url` redacts — so a redacted artifact still matches the raw `--url` an operator typed, and `tests/test_url_redaction_contract.py` walks live `BaseModel` subclasses (not source text, so a model inheriting through a mixin is still seen) and requires every URL-shaped field to redact or be argued into `EXEMPT_FIELDS`. The generation side is held separately (issue #158): `UrlSource.fetch_url` is for fetching and `UrlSource.citation_id` — its redacted form — is for naming, comparing and writing down, because a raw URL copied into a plain `str` field such as `manifest_source` or a descriptor `locator` escapes the model's own serializer. The raw accessor is spelled `fetch_url` while the serialized key stays `url`: a name nothing else uses makes `tests/test_citation_identity_contract.py` an exact check on every read rather than a heuristic, and makes a missed read an `AttributeError` rather than a leak. A citation locator is prose that may quote a URL, so it goes through `redact_text`, which redacts the URLs it finds and leaves the surrounding words alone. The same derivation is what keeps snapshot backfill and `loop-apidoc validate`'s coverage check working; a one-sided redaction silently broke both, because each compares something read back from disk against something still in memory. Acquisition commands let a refusal propagate; `manifest --url`'s best-effort probe records it as a note with no digest, like any other fetch failure. Fixing the original eight call sites does not stop a ninth, so `test_only_the_egress_gate_constructs_an_http_client` fails on any module but `url_safety.py` that *can issue a request*: constructing a client, calling a module-level verb (`httpx.get`, `httpx.stream`, `urllib.request.urlopen`), or reaching any of those through a renamed import. The criterion is calls, not spellings — `scripts/quality_gate.py::NETWORK_MODULES` resolves import bindings first, because a rule keyed on the text `httpx.Client` is bypassed by `import httpx as h`. `httpx.get(...)` is the shape worth naming: one ordinary-looking line, no client constructed, and `trust_env=True` by default, so it honours the proxy variables `safe_client` deliberately ignores. Feedback commands perform no provider network reads. Every other module is pure functions — keep it that way. That last sentence is a claim about all 40 writers — the count is asserted against the inventory, not typed from memory — not only the ones this paragraph highlights, so the authoritative list is `scripts/quality_gate.py::FILE_IO_EXIT_MODULES`: `test_every_module_that_writes_is_in_the_file_io_inventory` walks `loop_apidoc/` for write calls (the criterion is written beside the inventory) and fails both on a writer that is not listed and on a listed module that no longer writes. This paragraph names the notable exits for a reader; the inventory is what holds the boundary.

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
- **Change the preprocessing path** (`SOURCE_FACTS_UNSCANNED`): the semantic completeness gate never judged that source — it scanned zero endpoint facts, its facts matched no extracted endpoint, or its tail went unread behind a fence whose closing line was refused. Read the source before acting: a flattened dump or an unconverted PDF/Word file needs acquisition/preprocessing re-run along a table-preserving path (`normalize-html-snapshot`, `preprocess`) — re-reading it fixes nothing; a source whose structure is intact but whose method and path are not on one line (a bare URL with the method in prose or on a neighbouring line, or a null-path webhook) keeps the warning permanently — a method written out beside the path is read whichever form it takes (ADR 0011), but the scan never crosses a line to infer a missing one (ADR 0007) — and is not an extraction defect; for the zero-match shape, check whether the extraction missed the endpoints that source documents; and when the issue names a line number the cause is already known — fix the fence in the source, never the extraction. Warning severity, never blocking; a prose-only source with no parameter tables legitimately lands here (ADR 0007).
- **Re-answer the directive** (`FOCUS_UNMET`, `FOCUS_INCOMPLETE`): re-read the sources named in `requery_scope` — for a shortfall, `evidence` names each omitted code with the source and line documenting it. Report the gap rather than invent one; severity comes from the directive's `kind` alone.
- **Hand to a human** (`SUPPLEMENTARY_SUPPORT`): the claim's only support is a supplementary carrier. Do **not** re-read or re-extract — the citation resolves and the extraction is not defective; a person weighs the claim before approval (ADR 0010).

Per-code severity and the structured-routing fields (`target_file`/`field_path`/`requery_scope`) are documented in `skills/loop-apidoc/reference/assemble-and-correction.md`. The skill's other reference docs live alongside it in `skills/loop-apidoc/reference/`: `extraction-schemas.md`, `focus-directives.md`, `model-orchestration.md`, `source-quality.md`, and `url-fetching.md`.

## Provenance ↔ validation alignment

`provenance.json` `target` strings align **one-to-one** with projected artifact locations: OpenAPI uses `paths.*`/`components.*`, GraphQL uses `graphql:<Type>.<field>`, and AsyncAPI uses `asyncapi:<channel>.*` plus `asyncapi:components.schemas.*`. Anything entering an output must trace to a supported exact fragment or validation fails.

## Conventions

- Python `>=3.11`, managed with `uv` (no `pip`). Deps: typer, pydantic v2, httpx, pyyaml, openapi-spec-validator, jsonschema, pymupdf.
- Prefer immutable patterns (return new values; pure functions outside the I/O modules above).
- The skill file `skills/loop-apidoc/SKILL.md` is written in **English** (token economy); generated *product* output remains `zh-TW`. Validation issue text (`evidence`, `suggested_fix`, `fix_once`) is product output, so it is `zh-TW` too — one report must not address the operator in two languages, which is what happened while `validate/coverage.py` and `validate/response_contract.py` each chose their own.
- Docsentry governs the selected Markdown documents in `.docsentry.json`: it checks local links and documented package scripts against checked-in evidence. It does not validate HTML manuals, external URLs, prose style, translations, or generated run output.
- **Documentation language policy (for wider adoption/promotion):** teaching, promotion, and reference docs are **English-primary, Traditional-Chinese-secondary** — write the canonical copy in English so the project reaches the broadest audience, and provide zh-TW as the supporting/localized layer (e.g. `README.md` zh-TW ↔ `README.en.md` English). This applies to the human-facing docs listed under "Release: keep teaching & promotion docs in sync". The only content that stays `zh-TW`-first is *generated product output* (the `api-guide.zh-TW.md` guide and other run artifacts).

## Release: keep teaching & promotion docs in sync (non-negotiable)

A release is **not done** when `scripts/release.py prepare` finishes. The prepare command only
synchronizes *version metadata* in a fixed set of files:
`pyproject.toml`, `loop_apidoc/__init__.py`, `.claude-plugin/plugin.json`, `uv.lock`,
`README.md`, `README.en.md`, `docs/introduction.html` (its version footer only),
`tests/test_plugin_manifest.py`, and it writes `docs/RELEASE_NOTES_<version>.md`.

Every **human-facing teaching / promotion document is NOT touched by that script** and
**MUST be reviewed and updated in the same release** whenever the change alters
user-facing behavior (new/renamed/removed command or flag, changed process, new feature,
new pipeline stage). These docs drift silently and are the first thing readers see:

- `docs/index.html` / `docs/index.en.html` / `docs/introduction.html` / `docs/introduction.en.html` — 「認識 loop-apidoc」landing/intro
- `docs/onboarding.html` / `docs/onboarding.en.html` — new-engineer technical tour
- `docs/operator-manual.html` / `docs/operator-manual.en.html` — operator manual (commands & workflows)
- `docs/architecture-manual.html` / `docs/architecture-manual.en.html` — architecture manual
- `README.md` / `README.en.md` — command lists, examples, feature descriptions
  (their release-notes link is auto-bumped; their *body content* is not)
- `AGENTS.md` / `CLAUDE.md` — keep both agent-guidance files aligned with each other
- `docs/PRODUCT_EXTENSION_ROADMAP.md` / `docs/DESIGN_DECISIONS.md` — review whenever a
  change introduces a subsystem, changes product direction, or changes roadmap priority

Rule of thumb: if a code/process change would make any sentence, command example, or
feature list in the docs above wrong, fix it **in the same commit/release** — never defer.
Cross-check with `docs/RELEASE_CHECKLIST.md`.

Every generated release-note skeleton contains a mandatory `Strategy impact` declaration.
Select exactly one option: explain why there is no strategy impact, or list the strategy
documents updated in the release. `release:tag` (including dry-run) and `release:github`
must reject an unresolved declaration before any external action.

`npm run release:tag -- --message "loop-apidoc <version>"` is the mandatory complete
publication command: it verifies committed `docs/RELEASE_NOTES_<version>.md`, pushes
`HEAD` to `origin/main`, asks Tagsmith to publish the annotated `v<version>` tag, then
creates the matching non-draft GitHub Release from those notes using `gh release create
--verify-tag`. A real run checks `gh auth status` before any push or tag creation. Do
not stop after the tag, create a normal Release manually, or let GitHub CLI create a
tag. If the tag succeeds but the final GitHub Release step fails, fix the
authentication/API problem and run `npm run release:github` from a clean worktree.
`release:tag --dry-run` writes nothing, including no GitHub Release. After the release
is visible, record its URL and use `gh run list --branch main --limit 1` followed by
`gh run watch <run-id> --exit-status` to monitor CI. Failures require a follow-up
release, never a force-moved tag.

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
- The `.docx` (`docx_*.py`) and GitBook (`cache-gitbook-llms`) paths are **not validated
  against a real source**: no case in the inventory has a Word or GitBook source and every
  DOCX under `tests/` is synthesised in `tmp_path`, so their evidence strength is exactly a
  skipped case's. Never describe either as validated or source-backed; `README.md`,
  `README.en.md`, the landing/intro pages, both operator manuals, and
  `docs/PRODUCT_EXTENSION_ROADMAP.md` carry the label. Removing it requires the first real
  Word delivery or GitBook site to arrive as a benchmark case in the same change.
- Two labels grade the acquisition paths, and they are never interchangeable, because what is
  missing differs. **Not validated against a real source** — complete, unit-tested code that no
  case has used: `import-supplementary-note`, `import-rendered-url`, `select-url`,
  `related-url-pages`, plus the `.docx` path above; the first real source along the path becomes a
  case and removes the label. **Outside the harness by construction** — `catalog-url`,
  `cache-url-pages`/`cache-url-entry`, `snapshot-openapi-url`, and `cache-gitbook-llms` issue
  network requests while a harness run must be offline-reproducible; only a replayable recording
  contract removes that, never another source. `cache-gitbook-llms` is in both states.
  `manifest`, `preprocess` (PDF), and `normalize-html-snapshot` carry a real source in at least one
  case and take neither label. Never write a labelled path as validated, and never author a
  synthetic case to erase a label. Both READMEs, both operator manuals, and
  `docs/BENCHMARK_VALIDATION_PLAN.md` carry this grading.
- The grading itself is a fourth reviewed inventory:
  `scripts/quality_gate.py::SOURCE_ACQUISITION_EVIDENCE_TIERS` maps each acquisition command
  to **every** label its branches earn — a tuple, because `preprocess` is source-backed for
  PDF and un-validated for `.docx`, and `cache-gitbook-llms` is in both un-validated states —
  and `NON_ACQUISITION_CLI_COMMANDS` names every other command with the reason it acquires
  nothing. The criterion is written beside them: a command is an acquisition path when it
  brings supplier material into the local, manifest-bindable corpus, or establishes that
  corpus. The two mappings must classify every command `loop_apidoc.cli.app` registers,
  sub-app commands included under their full invocation (`foundry import`, `feedback
  assess`), so a later `foundry fetch-portal` cannot ship ungraded;
  `test_every_cli_command_is_graded_or_explicitly_excluded` fails both on an unclassified
  new command and on a listed command the CLI no longer has. The doc tables are the
  human-readable presentation, checked against the list by
  `tests/docs/test_acquisition_evidence_tiers.py` and never generated from it.
- Implementation-backed conformance benchmarks are a separate assurance lane. They report
  only the declared Applicability Envelope, time, and suite version; they never count as a
  source-backed strict-local pass or documentary grounding coverage.
- `uv run python scripts/quality_gate.py --strict-local` requires non-empty sources for
  every required case and rejects any benchmark skip. Only a zero-skip run may be
  described as strict-local passed.
- Because `assemble` requires `--source-quality`, each required case also needs an
  operator-generated, gitignored `benchmarks/<case>/source-quality/` package; the harness
  skips a case that lacks it and `--strict-local` names the missing package before it runs
  pytest.
- `scripts/quality_gate.py::SANITIZED_BENCHMARK_CASES` is a separate reviewed
  inventory for redistributable, line-preserving exact-evidence subsets. Its
  descriptors must have exact set parity with the inventory. Run
  `uv run python scripts/quality_gate.py --sanitized-fixtures`; never describe
  this supplemental result as source-backed or strict-local, and never use its
  `sanitized_sources/` as a fallback for `--strict-local`.
- A PDF-derived case may additionally commit `source-derivation.json`, binding the
  original PDF (case-relative path under gitignored `raw/`, official URL, capture
  date, SHA-256), the derived Markdown (case-relative path, SHA-256), and the
  conversion tool by name — never a pinned version, since `uv.lock` is the sole
  authority for which pymupdf4llm runs (ADR 0013). Neither the original PDF nor
  its Markdown is ever *committed* — both `raw/` and `sources/` are gitignored —
  so `derived_markdown.sha256` is the only tracked anchor. `scripts/quality_gate.py::
  SOURCE_DERIVATION_BENCHMARK_CASES` is a third reviewed inventory with the same
  exact-set-parity rule; `--strict-local` names a case whose original is not
  restored into `raw/` before it runs pytest. `tests/test_benchmarks.py` checks
  the local Markdown's digest unconditionally wherever that file exists, and
  additionally re-runs `preprocess` over the restored original, asserting the
  output is byte-identical to the local Markdown, when `raw/` is also present —
  SKIPping the re-derivation half like every other source-backed assertion when
  the original is absent. This grants no
  new evidence strength — a declared case was already source-backed — it only
  exercises the conversion step that previously sat outside every harness run.
  Only `ecpay-creditcard-pdf` is in this lane today; `jili-legacy-gaming-pdf`'s
  source is a supplier delivery with no public URL and joins only once that file
  is available.
- Never replace an unavailable historical snapshot with a newer document, synthetic
  fixture, or error page. Record the unavailable evidence, run deterministic CI checks,
  and perform a legitimate targeted source-backed spot-check instead.
- `scripts/quality_gate.py::EXACT_EVIDENCE_PARITY_BENCHMARK_CASES` is a fourth reviewed
  inventory: the cases with an executable full Core-parity replay today. It cannot be
  derived from the files — every committed case *declares*
  `require_exact_evidence_for_all_material_claims` in `core-parity.json`, and a
  declaration is the bar a case must meet, never evidence that it met it.
  `test_case_obeys_declared_core_parity_contract` is parametrized over it.
- `uv run python scripts/benchmark_attestation.py --json-out <path> --markdown-out <path>`
  writes a per-case `benchmark-attestation/v1` report: every required case exactly once,
  its assets and their availability, and which of committed, discovered,
  prerequisites-unavailable, source-backed executed, sanitized-fixture executed,
  exact-evidence parity and strict-local eligible/passed actually holds — with harness
  conformance and the `PASS`/`EXPECTED_FAIL` contract validation stated separately, so an
  `EXPECTED_FAIL` case stays `FAIL` while being conformant. What executed is read from one
  pytest run's JUnit XML, never from pytest prose. It reports assurance and never raises
  it: it is not part of `make verify`, it fails closed on malformed, stale, tampered or
  contradictory input, it refuses an existing or symlinked output path, and it persists no
  supplier content, absolute path, or unredacted credential.
- The canonical four-layer model, thirteen-case inventory, terminology, per-case
  attestation, and case-addition workflow are in `docs/BENCHMARK_VALIDATION_PLAN.md`.

## Repository hygiene

Some directories at the repository root are *generated* or *supplied*, never authored
here: a run writes them, or an operator drops someone else's material into them.
Committing one adds thousands of files nobody reviews — and that happened, root `work/`
was tracked on `main` for several releases because nothing checked. `.gitignore` stops the next accidental `git add`; the gate is
what fails loudly if one lands anyway.

`scripts/quality_gate.py::REPOSITORY_HYGIENE_FORBIDDEN_ROOTS` is a reviewed inventory in
the same family as the four above, and the table is its human-readable presentation —
checked against it by `tests/docs/test_repository_hygiene_documentation.py`, never
generated from it.

| Forbidden tracked root | Kind | Why it must not be committed |
| --- | --- | --- |
| `work/` | run artifact | local pipeline scratch: URL raw/cache, extraction JSON, agent answers, source-quality and source-risk reports, assemble run outputs |
| `out/` | run artifact | operator-chosen assemble output root (`--output` has no default) |
| `runs/` | run artifact | accumulated run directories |
| `tmp/` | run artifact | ad-hoc scratch |
| `.loop-apidoc/` | run artifact | local tool state |
| `sources/` | third-party material | operator-provided supplier snapshots, redistribution rights uncertain |
| `teams-archive-preview/` | third-party material | local Teams export containing chat content |

The `Kind` column is not decoration: `third-party material` is what makes the gate tell an
operator to escalate to the repository owner instead of just removing the directory.
`test_documented_kinds_match_the_disclosure_subset` holds it to
`REPOSITORY_HYGIENE_DISCLOSURE_ROOTS`.

- **The criterion**, deliberately narrow: a tracked path violates repository hygiene
  when its **first** path segment is exactly a listed root *and* at least one more
  segment follows. Not a substring match — `workflows/ci.yml` and `work.json` are
  ordinary files. Not a root-level file — a tracked file named exactly `work` is
  authored, and `git rm -r --cached work` over it would remove the wrong thing. Not a
  nested match, so
  `benchmarks/<case>/work/` and `benchmarks/<case>/sources/` (governed by
  `benchmarks/.gitignore`, and the latter is exactly the snapshot the harness binds to)
  are untouched, as would be a package that ever adds its own `sources/` module. Widening this to a nested match
  would break the benchmark harness contract, not merely over-report. `.work/` is a different name and has its own rule.
- **Two kinds of root, and the second is why the rule earns its place.** The first five
  hold regenerable clutter. `sources/` and `teams-archive-preview/` hold *other people's
  material* — operator-provided supplier snapshots whose redistribution rights are
  uncertain, and a Teams export containing chat content. Committing one of those is a
  disclosure, not a mess, and unlike clutter a later `git rm` does not undo it: the blob
  stays reachable in history and in every existing clone. That is why the gate refuses
  the commit rather than trusting review to catch it, and why
  `REPOSITORY_HYGIENE_DISCLOSURE_ROOTS` names that subset: the failure message for those
  roots says removal is not the whole fix, routes the purge decision to the repository
  owner, and tells the reporter not to quote the contents. A contributor never performs
  a purge, and this gate never performs one either.
- Widening the inventory is a decision, not a tidy-up. Third-party tool caches
  (`node_modules/`, `.venv/`, `dist/`, `graft/`, `htmlcov/`, `__pycache__/`) are
  deliberately absent — committing them is an ecosystem-wide mistake every contributor's
  tooling already flags, not a property of this repository, and `dist/` is a directory
  some projects commit on purpose. `benchmark_out/`, `benchmark_work/` and `output/` stay
  out too: listing a root nothing has ever written is guessing. Adding a root requires a
  matching table row in the same change;
  `test_documented_hygiene_table_matches_the_controlled_list` enforces exact set parity
  in both directions, so neither the code nor this table can move alone.
- `repository_hygiene_violations` is a pure function over the Git-tracked path list —
  never a filesystem walk, so ignored and untracked local files are out of scope by
  construction — and `main()` runs it before any gate step, so a dirty tree fails in
  milliseconds. The failure names relative paths and the remedy; it never opens a file,
  so a leaked artifact's contents can never reach the gate's output.
- The remedy for an already-tracked root is `git rm -r --cached <root>`, which leaves the
  operator's local copies on disk. That is a forward commit, not a Git history rewrite;
  this gate never asks for one. Purging history is a separate owner decision about
  redistribution rights, and it is never a step in clearing a hygiene failure.
- **`.gitignore` prevents, the gate detects, and the two are held in agreement by
  `tests/test_gitignore_contract.py`** — which asks Git via `git check-ignore -v` rather
  than reimplementing the pattern language, and asserts *which* rule won, so a developer's
  global `core.excludesFile` can never satisfy the contract. Prevention lives in two files:
  the root `.gitignore` and `benchmarks/.gitignore`, whose `*/sources/`, `*/work/`,
  `*/raw/`, `*/output/` and `*/source-quality/` cover the per-case operator material. Every root in the inventory must have an ignore
  entry, or the gate becomes the only line of defence and fails the contributor at commit
  time instead of preventing the mistake. The run-artifact entries are root-anchored
  (`/tmp/`, `/runs/`, `/.loop-apidoc/`): unanchored, they also swallowed any same-named
  directory at any depth, so a future `loop_apidoc/tmp/` module would have vanished from
  `git add` with no error — the silent failure this boundary exists to prevent.
- **`sources/` is deliberately *not* anchored** — the one exception, and worth stating
  precisely because the obvious reason for it is wrong. It is *not* that the benchmark
  snapshots depend on it: `benchmarks/.gitignore`'s `*/sources/` is the rule that actually
  wins there, and anchoring the root entry leaves every committed case still ignored. The
  real reason is that a nested `sources/` holding supplier material is a layout operators
  actually use — one exists under each of `work/`, `.work/`, `tmp/`, `.loop-apidoc/` and
  `runs/` — and `sources` is a disclosure root, where the failure is redistributing someone
  else's document and a later `git rm` does not undo it. A second overlapping rule is cheap
  insurance there. The cost is real and accepted: a future `loop_apidoc/sources/` module
  would be ignored silently, and the root-anchored gate cannot cover the nested case either.
  Both the exception and its cost are pinned by tests that fail if the entry is anchored.
- **A leak that already reached history is the repository owner's to purge, never this
  gate's.** The gate reports paths and exits non-zero; it does not rewrite history, delete
  refs, or force-push, and asking the host to garbage-collect afterwards is part of that
  purge rather than a follow-up. Root `work/` was purged on this basis on 2026-08-30 —
  scope, evidence, and falsification condition in
  [ADR 0014](docs/adr/0014-a-leaked-third-party-document-is-purged-by-the-owner-not-the-gate.md).
- Where material *should* go — reviewed, reproducible test cases in `benchmarks/`,
  reader-facing samples in `examples/` — is contributor guidance and lives in
  `CONTRIBUTING.md`.

## Further docs

- Architecture + data flow (with diagrams): `docs/ARCHITECTURE.md`
- Product design decisions: `docs/DESIGN_DECISIONS.md`
- Contributing: `CONTRIBUTING.md`
- CI workflow: `.github/workflows/ci.yml`; release checklist: `docs/RELEASE_CHECKLIST.md`
- Pipeline follow-ups (deferred work): GitHub issues on `CarlLee1983/loop-apidoc`
