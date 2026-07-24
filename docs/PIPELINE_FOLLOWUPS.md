# Pipeline Follow-ups

This document tracks pipeline improvements from item 2 onward, after the benchmark
regression harness work.

> **Status (2026-07-24):** items 2–7 implemented on branch `feat/pipeline-followups`
> (commits `d3b0ae8`, `e89cbd7`, `75ef8cb`, `f7d374d`). Each section's acceptance
> criteria are met and covered by tests / CI.
> Items 6–7 were subsequently resolved on 2026-06-29. The `preprocess`
> output-path collision recorded under item 8 was resolved on 2026-07-24.

## 2. Run Directory Isolation — ✅ done (`d3b0ae8`)

### Current State

- `loop_apidoc.run.runid.make_run_id()` uses second-level precision
  (`%Y%m%dT%H%M%SZ`).
- `run_assemble_pipeline()` creates `output_root / run_id` with
  `mkdir(parents=True, exist_ok=True)`.
- A fast correction loop, repeated local command, or parallel benchmark execution
  can target the same run directory when two runs start in the same second.

### Risk

Outputs from separate runs can mix in the same directory, making validation
results and artifacts harder to trust.

### Recommended Work

1. Make run IDs collision-resistant.
   - Prefer adding subsecond precision, e.g. `%Y%m%dT%H%M%S.%fZ`, or append a short
     random/monotonic suffix.
   - Keep filesystem-safe characters.
2. Decide whether `assemble` should fail if the target run directory already
   exists.
   - Strict option: use `mkdir(exist_ok=False)` and report a clear collision.
   - Permissive option: keep unique run IDs and leave existing directories alone.
3. Add regression tests.
   - `make_run_id()` produces distinct IDs for distinct close timestamps.
   - `run_assemble_pipeline()` does not silently reuse an existing run directory,
     or explicitly proves the chosen collision policy.

### Acceptance Criteria

- Two assemble runs started within the same second do not write into the same
  run directory.
- Existing tests still pass.
- README output structure is updated if the run ID format changes.

## 3. More Actionable Correction Reports — ✅ done (`e89cbd7`)

### Current State

- Validation issues expose `code`, `severity`, `location`, `evidence`,
  `suggested_fix`, and `auto_fixable`.
- The agent correction loop infers which file to edit from free-form
  `location` values.

### Risk

The report is human-readable, but not strongly machine-actionable. The agent can
misidentify whether to update `inventory.json`, `endpoints/<N>.json`, or
`integration.json`, especially as issue locations become more detailed.

### Recommended Work

1. Extend `Issue` with optional structured routing fields.
   - `target_file`: `inventory.json`, `endpoints/epN.json`, `integration.json`, or
     `null`.
   - `field_path`: JSON-pointer-like path into that file.
   - `requery_scope`: source section, endpoint ref, integration area, or other
     bounded reread hint.
2. Populate these fields in validators where the mapping is deterministic.
3. Keep existing fields for backwards compatibility.
4. Update `skills/loop-apidoc/SKILL.md` to prefer structured fields when present
   and fall back to `location` otherwise.

### Acceptance Criteria

- `assemble --json` includes structured correction hints for at least:
  - missing endpoint details
  - malformed or missing integration crypto
  - unresolved `payload_ref` / `operation_ref`
- Existing consumers that read only `report.issues[*].location` keep working.
- Tests cover JSON serialization of the new fields.

## 4. Earlier Extraction Input Schema Validation — ✅ done (`75ef8cb`)

### Current State

- `load_extraction_inputs()` verifies that extraction files exist and are valid
  JSON.
- The plan builder tolerates some malformed shapes by recording missing items
  instead of crashing.
- Some schema-contract mistakes are only discovered later through output quality
  or benchmark review.

### Risk

Bad extraction JSON can travel too far into the pipeline. The resulting failure
may appear as a validation gap or degraded output instead of a direct extraction
contract error.

### Recommended Work

1. Add typed pydantic models for agent-written extraction inputs.
   - `InventoryInput`
   - `EndpointDetailInput`
   - `IntegrationInput` or a thin validator around the existing integration
     contract builder
2. Validate these immediately in `load_extraction_inputs()`.
3. Return `AssembleInputError` with file path and field path for invalid input.
4. Keep null/empty values allowed where the source genuinely omits information.
5. Preserve fail-closed behavior: unsupported or uncertain source facts remain
   `missing`, not guessed.

### Acceptance Criteria

- Invalid extraction shape exits with code `2`, before creating a run directory.
- Error messages identify the file and field that failed validation.
- Existing benchmark extraction files pass the stricter validation.
- Tests cover localized-key/schema-field mistakes, malformed endpoint details,
  and optional `integration.json`.

## 5. CI / Release Gate — ✅ done (`f7d374d`)

### Current State

- Local test commands are documented.
- The repository has pytest configuration.
- The benchmark harness exists and passes locally when sources are present.
- No repo-local GitHub Actions workflow was found during inspection.

### Risk

Regressions can land unless every contributor remembers to run the same checks
locally. Benchmark coverage is especially easy to skip because source files are
operator-provided and gitignored.

### Recommended Work

1. Add a CI workflow for fast deterministic checks.
   - `uv sync`
   - `uv run pytest`
   - `uv run ruff check .`
2. Decide benchmark CI policy.
   - Minimal: run `tests/test_benchmarks.py`; allow source-missing skips, but keep
     discovery guard active.
   - Stronger: provide sanitized source fixtures or manifest fixtures so benchmark
     cases run in CI without copyrighted sources.
3. Add a release checklist.
   - Full tests
   - Ruff
   - Benchmark harness on a machine with sources
   - Manual spot-check for at least one generated OpenAPI, guide, provenance,
     examples, and integration contract

### Acceptance Criteria

- CI fails on unit/integration test failures.
- CI fails if benchmark case discovery becomes empty or loses required cases.
- Release checklist documents which benchmark checks require local source files.

## 6. Quality-Gate `Runner` Type Alias Too Narrow — resolved (2026-06-29)

> Resolved: `Runner` now returns a structural `_RunResult` Protocol
> (`returncode`/`stdout`/`stderr`); `_default_runner`'s `CompletedProcess` and the
> tests' `FakeResult` both satisfy it. `pyright scripts/quality_gate.py
> tests/test_quality_gate.py` reports 0 errors (was 3).



### Current State

- `scripts/quality_gate.py` declares
  `Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]`.
- The unit tests inject a `FakeResult` dataclass (with `returncode` / `stdout` /
  `stderr`) as the runner. It is structurally compatible at runtime (duck typing),
  so all tests pass and ruff is clean.

### Risk

The alias nominally requires `subprocess.CompletedProcess[str]`, but the fakes are
not instances of it. Under `mypy --strict` or `pyright` strict, every test site
passing a `FakeResult`-returning runner would raise a type error. The repo does not
currently run a strict type-checker in CI, so this is latent — it would surface the
day a type-check step is added (which the quality gate itself might eventually grow).

### Recommended Work

1. Replace the alias's return type with a structural `Protocol`:

   ```python
   class _RunResult(Protocol):
       returncode: int
       stdout: str
       stderr: str

   Runner = Callable[[list[str]], _RunResult]
   ```

2. Keep `_default_runner` returning a real `subprocess.CompletedProcess` (it
   satisfies the Protocol).
3. Optionally type the test `FakeResult` against the same Protocol to lock the
   contract.

### Acceptance Criteria

- A strict type-checker (mypy/pyright) reports no errors on `scripts/quality_gate.py`
  and `tests/test_quality_gate.py` for the runner contract.
- Existing tests still pass with no runtime change.

## 7. `has_benchmark_skips` Char-Set Heuristic False Positive — resolved (2026-06-29)

> Resolved: the progress-dots path now requires the line to be dominated by `.`
> (`stripped.count(".") * 2 >= len(stripped)`), so prose words like `"esp"` return
> `False` while genuine progress lines (`"........s.."`) still return `True`. A
> docstring documents the `pytest -q` assumption. Regression test:
> `test_has_benchmark_skips_rejects_non_pytest_word`.



### Current State

- `has_benchmark_skips(stdout)` returns `True` when `"skipped"` appears in the
  output (the reliable path), or when a stripped line is a subset of the pytest
  result-character set (`.sfexXpP`) and contains an `s` (the progress-dots path).
- It is only ever called on `uv run pytest tests/test_benchmarks.py -q` output,
  where the reliable `"skipped"` summary path always fires for real skips.

### Risk

The progress-line path has a theoretical false positive: a standalone line such as
`esp` (a subset of `.sfexXpP` that contains `s`) returns `True`. This is unreachable
from the actual wired `pytest -q` output (summary lines contain digits/spaces that
break the subset test), so it is not a live defect — but the function reads like a
general-purpose helper and could mislead if reused elsewhere (e.g. against xdist
`[gw0]` / `[100%]` decorated output).

### Recommended Work

1. Tighten the progress-line detection so it only matches a genuine pytest progress
   line — e.g. require the line to be non-trivially long and dominated by `.`, or
   anchor on the summary line exclusively and drop the dots heuristic.
2. If the helper is intended to stay single-purpose, add a docstring stating it
   assumes `pytest -q` output and is not safe for arbitrary text.
3. Keep all four existing parametrized cases passing unchanged.

### Acceptance Criteria

- A contrived non-pytest line like `"esp"` returns `False`.
- The four existing cases still return `[True, True, True, False]`.
- `--strict-local` skip detection behavior is unchanged on real benchmark output.

## 8. Run Version Diff — Deferred Minor Findings — partially resolved (2026-07-02)

> Deferred from the `loop-apidoc diff` subagent-driven build (branch
> `feat/run-version-diff`, commits `519a321`..`786086c`). The final whole-branch
> review returned **Ready to merge — Yes** with 0 Critical/0 Important; every item
> below was independently triaged **acceptable-defer**. All are non-blocking polish
> on `loop_apidoc/diff/`.

### Current State

- `loop_apidoc/diff/` ships the `diff` command: loader, pure `compare.py`
  (OpenAPI + integration + provenance/validation/manifest), and `report.py`
  rendering. 33 diff+CLI tests pass; impact classes are pinned by enum-identity
  asserts.

### Risk

Items 1, 4, and 5 were already resolved before the 2026-07-02 correctness batch.
This batch resolves every listed diff finding; items 6 and 7 were completed in
the subsequent correctness batch.

### Recommended Work

1. **Resolved (2026-07-02 health check): Loader schema-mismatch error omits the file.**
   Bad provenance/validation/manifest parse paths now identify the offending
   artifact.
2. **Resolved (2026-07-02 correctness batch 1): `compare.py` object→scalar schema
   change double-reports.** Object/non-object flips now stop after the parent
   `schema changed` finding.
3. **Resolved (2026-07-02 correctness batch 1): `_provenance_map` compares entry
   lists by ordered position.** Entries are sorted inside each target group by
   `(manifest_source, query_id)` before comparison.
4. **Resolved (2026-07-02 health check): `_issue_key` excludes `suggested_fix`.**
   The issue key now includes remediation text so source-only validation changes
   are visible.
5. **Resolved (2026-07-02 health check): Integration key-collision on name-less
   items.** Duplicate unnamed items are disambiguated instead of overwritten.
6. **Resolved (2026-07-02 correctness batch 2): CLI summary key access.** `cli.py`
   diff summary now uses `report.summary.get(k, 0)` defensive lookups.
7. **Resolved (2026-07-02 correctness batch 2): Coverage gaps.** Added diff
   classification tests (`info.title` CHANGED; property-no-longer-required CHANGED;
   removed-component-schema CHANGED; callback core-field → BREAKING;
   validation-issue-removed → SOURCE_ONLY) and strengthened
   `test_response_schema_type_change_is_breaking` to exact-equality location.

### Acceptance Criteria

- Loader schema errors name the offending file.
- Any classification change keeps the existing 33 diff+CLI tests green and adds a
  regression test for the corrected behavior.
- New coverage tests assert `DiffImpact` enum identity, consistent with the
  existing diff test style.

### Later Correctness Ledger

- **Resolved (2026-07-02 health check): examples encoding consistency.**
- **Resolved (2026-07-02 health check): generator native oneOf/discriminator.**
- **Resolved (2026-07-02 correctness batch 2): path parameters absent from the URL
  template.** Template tokens without a declared parameter are synthesized (empty
  schema); declared `in: path` params with no matching token surface as an
  `error`-severity `SOURCE_CONFLICT`.
- **Resolved (2026-07-02 correctness batch 2): diff comparator review minors.**
  M1 (object-detection predicate deduped into `_looks_like_object`); M3
  (`_compare_parameters` recurses into object-typed parameter schemas).
- **Resolved (2026-07-24): preprocess output paths.** Directory input retains
  source-relative paths and a converted `foo.pdf` becomes `foo.pdf.md`; the
  complete output mapping is checked before any file content is written. Focused
  regression coverage proves nested same-basename sources and a PDF/Markdown sibling
  remain distinct.
