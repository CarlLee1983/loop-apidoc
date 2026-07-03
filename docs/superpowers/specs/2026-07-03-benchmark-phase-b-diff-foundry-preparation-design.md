# Benchmark Phase B — diff / foundry multi-version / preparation + score verdict

**Status:** Design approved 2026-07-03. Next: implementation plan (writing-plans).

## Goal

Extend the benchmark regression harness (`tests/test_benchmarks.py`) so three downstream
subsystems that today have only unit coverage — or none at the benchmark level — are
exercised against the **real committed benchmark run dirs**:

1. `diff` — run-to-run version diff (currently zero benchmark coverage).
2. `foundry` multi-version governance — supersession + `min_score` gate (Phase A only drove
   a single `register → import → approve → resolve` chain).
3. `preparation` readiness report + `score` loop verdict (neither is benchmark-tested).

All new tests are deterministic, need no new operator-provided sources, and reuse Phase A's
memoized `assembled` fixture. This is **Phase B**; adding *new document-sample cases*
(`.docx` / OpenAPI YAML / `SOURCE_CONFLICT` two-source) is deferred to a separate spec because
it is blocked on operator-provided sources.

## Constraints

- Python `>=3.11`, `uv` (no `pip`). Run tests via `uv run pytest`.
- **Only** `tests/test_benchmarks.py` is modified. No product-code changes; no changes to
  `benchmarks/**` data or `expected/*.json`.
- The Phase A `assembled` run dir is treated **read-only** by every new consumer. Any test that
  needs a mutated or second copy `copytree`s into its own `tmp_path` first — it never writes
  into the shared run dir.
- `_FIXED_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)` remains the single fixed timestamp
  wherever determinism matters (foundry `approve` `now=`).
- **TDD inversion:** every subsystem under test already exists, so each new benchmark test is
  expected to PASS on first run against real data. A failure is a genuine subsystem finding —
  stop and investigate with systematic-debugging rather than weakening the test.

## Architecture

Five new tests appended to `tests/test_benchmarks.py`, grouped by subsystem. They consume the
existing `case` (parametrized `Path`) and `assembled` (memoized `RunResult`) fixtures. New
imports come from the already-public APIs of `loop_apidoc.diff`, `loop_apidoc.foundry`,
`loop_apidoc.preparation`, and `loop_apidoc.score`.

Verified interfaces the design relies on:

- `diff`: `load_run_artifacts(run_dir: Path) -> RunArtifacts` and
  `build_diff_report(base: RunArtifacts, head: RunArtifacts) -> DiffReport` (both public from
  `loop_apidoc.diff`); `DiffReport.findings: list[DiffFinding]`, each with
  `.impact: DiffImpact` ∈ {`breaking`, `additive`, `changed`, `source_only`}.
- `foundry`: `register_docset`, `import_run(...).run_id`, `approve_candidate(..., approved_by,
  now, min_score=None, allow_failing=False) -> Asset`, `load_current_asset`, plus catalog/list
  read side and `FoundryApprovalError` (raised when a candidate fails the `min_score` gate).
  Asset status transitions to `SUPERSEDED` on the prior asset when a newer one is approved.
- `preparation`: `assemble` writes `preparation-report.json` into the run dir; its `status`
  field is a `PreparationStatus` ∈ {`ready`, `needs_attention`, `blocked`}, with `phases[]`
  each carrying `findings[]` of `severity` ∈ {`error`, `warning`}.
- `score`: `ScoreReport` exposes `.score`, `.min_score`, `.findings: list[ScoreFinding]`;
  `classify_findings(findings) -> (reducible, irreducible)` (order-preserving partition);
  `loop_verdict(*, prev_score, curr_score, target, round_index, max_rounds, findings) ->
  LoopReport` with `.verdict: LoopVerdict` ∈ {`converged`, `plateau`, `exhausted`, `continue`}.
  Precedence: `curr_score >= target` → `CONVERGED` first.

## Components

### Component 1 — `diff` (self-diff identity + controlled mutation)

**`test_benchmark_diff_identity(case, assembled)`** — parametrized over all cases.
`copytree` the shared run dir into a `tmp_path` copy, `load_run_artifacts` both sides, compare,
and assert the change sets classified `breaking`, `additive`, and `changed` are all **empty**
(`source_only` differences are allowed — provenance/manifest source paths legitimately differ
between two copies). Invariant: *diffing a run against an identical copy yields no semantic
change.* This is the spurious-diff regression net.

**`test_benchmark_diff_detects_change()`** — a single, non-parametrized test on one clean
OpenAPI-sourced case (`stripe-basic-rest`). Build a v2 by applying three known mutations to a
`tmp_path` copy of that case's committed `extraction/` — (a) add one endpoint (**additive**),
(b) remove one endpoint (**breaking**), (c) change one field's `required`/type on a retained
endpoint (**changed**) — then `run_assemble_pipeline` the mutated extraction into a second run
dir and compare baseline vs v2. Assert each of the three `DiffImpact` classes is present in the
resulting findings, anchored to the mutated operation/field. If the mutated extraction fails to
assemble, that is a real finding (the harness's mutation helper is wrong, or assemble
regressed) — investigate, don't weaken.

### Component 2 — `foundry` multi-version (single representative case + `min_score` gate)

**`test_benchmark_foundry_supersession(...)`** — runs on one representative PASS case against a
throwaway `tmp_path` project root. `copytree` the shared run dir into two differently-named run
dirs (import uses `run_dir.name` as `run_id`), `register_docset`, `import_run` both, then
`approve_candidate` v1 followed by v2. Assert: the v1 asset transitions to `SUPERSEDED`, the
`current` pointer resolves to v2's asset id, and `load_current_asset` / the docset list read
side agree. This exercises the supersession path Phase A's single-approve test never reached.

**`min_score` gate** — same test (or an adjacent one on the same case): call `approve_candidate`
with a `min_score` above the run's actual score and assert `FoundryApprovalError` is raised;
then re-approve with `allow_failing=True` (or a `min_score` the run meets) and assert it
succeeds. Supersession semantics are case-content-independent, so one representative case is
sufficient — running all ten would only duplicate identical logic.

### Component 3 — `preparation` + `score` verdict (per-case invariants)

**`test_benchmark_preparation(case, assembled)`** — read `preparation-report.json` from the run
dir. Assert `status` is a valid `PreparationStatus` value, `phases` is non-empty, and every
finding's `severity` ∈ {`error`, `warning`}. Invariant: **a validation-PASS case must not be
`blocked` at preparation** (a run that proceeded to a PASS validation cannot have been
preparation-blocked). EXPECTED_FAIL cases (paypal) may hold any status.

**`test_benchmark_score_verdict(case, assembled)`** — from the real `ScoreReport`
(`evaluate_score` on the run dir): (a) assert `classify_findings(report.findings)` is a
loss-less, disjoint partition (`reducible + irreducible == findings`); (b) assert
`loop_verdict(prev_score=None, curr_score=report.score, target=report.min_score, round_index=1,
max_rounds=3, findings=report.findings).verdict` is a valid `LoopVerdict`, and is deterministic
across a second identical call; (c) coupling invariant: **`report.score >= report.min_score` ⇒
verdict is `CONVERGED`** (the loop must not ask for more correction once the target is met).

## Error handling

- Absent local `sources/` → the `assembled` fixture skips the case (inherited from Phase A).
- A malformed committed extraction → `AssembleInputError` errors the test (correct signal).
- Component 1's mutated extraction failing to assemble, or Component 2's approval gate behaving
  unexpectedly → genuine findings; investigate with systematic-debugging, never weaken.

## Testing / verification

- Per component: `uv run pytest tests/test_benchmarks.py -v -k <diff|foundry|preparation|score>`
  — PASS where local `sources/` exist, SKIP otherwise.
- Whole file: `uv run pytest tests/test_benchmarks.py -v` — all Phase A + Phase B params
  consistent; `test_benchmark_harness_discovers_cases` still PASS.
- Full suite: `uv run pytest` — the additions must not disturb any other test.
- Lint: `uv run ruff check tests/test_benchmarks.py` — no findings.

## Out of scope (YAGNI / deferred)

- New document-sample cases (`.docx`, OpenAPI YAML, `SOURCE_CONFLICT` two-source,
  `UNSUPPORTED_ASSERTION`) — separate spec, blocked on operator sources.
- Native generator support changes, product-code refactors — none; this is test-only.
- Per-case foundry multi-version — deliberately single representative (logic is
  case-independent).
