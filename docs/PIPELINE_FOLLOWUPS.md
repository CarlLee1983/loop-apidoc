# Pipeline Follow-ups

This document tracks pipeline improvements from item 2 onward, after the benchmark
regression harness work.

## 2. Run Directory Isolation

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

## 3. More Actionable Correction Reports

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

## 4. Earlier Extraction Input Schema Validation

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

## 5. CI / Release Gate

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

