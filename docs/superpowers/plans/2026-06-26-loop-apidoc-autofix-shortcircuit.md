# AUTO_FIX No-op Short-Circuit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the correction loop short-circuit to FAILED the moment a round can only act on AUTO_FIX issues, instead of burning all 3 rounds regenerating identical invalid output.

**Architecture:** A single predictive guard inside `run_correction_loop`. When the round's actionable issues contain zero RE_QUERY issues, the round is provably a no-op (generation is deterministic from the plan and `requery` is the only thing that mutates the plan), so we return FAILED immediately. The guard makes the subsequent `requery` call unconditional.

**Tech Stack:** Python 3.12, Pydantic v2, pytest. Pure in-memory logic over injected closures — no I/O.

## Global Constraints

- Python ≥ 3.12; Pydantic v2 models (`model_copy`, immutable update pattern — never mutate inputs).
- `run_correction_loop` stays pure: it operates only on the injected `regenerate` / `requery` / `validate` closures and returns a new `CorrectionOutcome`. No file I/O, no NotebookLM calls.
- Reuse `RunStatus.FAILED` for the short-circuit — do NOT add a new enum value.
- `RunResult.ok` semantics unchanged (`status is RunStatus.PASSED`); CLI exit code unchanged.
- Commit message format: `<type>: [ <scope> ] <subject>` — scope is `run`.

---

### Task 1: Short-circuit AUTO_FIX-only rounds

**Files:**
- Modify: `loop_apidoc/run/correction.py` (the `run_correction_loop` while-body + the AUTO_FIX `NOTE` comment at lines 15-22)
- Test: `tests/run/test_correction_loop.py`

**Interfaces:**
- Consumes (unchanged signature):
  `run_correction_loop(plan, result, *, regenerate, requery, validate, max_rounds=3) -> CorrectionOutcome`
  where `regenerate: Callable[[NormalizationPlan], GenerateResult]`,
  `requery: Callable[[NormalizationPlan, ValidationReport], NormalizationPlan]`,
  `validate: Callable[[NormalizationPlan, GenerateResult], ValidationReport]`.
- Uses existing helpers in the same module: `actionable_codes(report) -> list[Issue]`,
  `classify_issue(issue) -> CorrectionCategory`, `annotate_fixability(report) -> ValidationReport`.
- `CorrectionCategory.RE_QUERY` / `.AUTO_FIX` from `loop_apidoc.run.models`.
- Produces: same `CorrectionOutcome` type. New behavior only — no signature change.

- [ ] **Step 1: Update the existing AUTO_FIX-only test to expect the short-circuit**

In `tests/run/test_correction_loop.py`, replace the body of `test_auto_fix_only_does_not_requery` (currently asserting `rounds == 3`) with the new expectation:

```python
def test_auto_fix_only_does_not_requery() -> None:
    auto_fix_report = ValidationReport(
        issues=[
            Issue(
                code=IssueCode.OPENAPI_INVALID,
                severity=Severity.ERROR,
                location="paths",
                evidence="invalid schema",
                suggested_fix="fix schema",
            )
        ]
    )
    requeries = {"n": 0}
    regenerations = {"n": 0}

    def requery(p, r):
        requeries["n"] += 1
        return p

    def regenerate(p):
        regenerations["n"] += 1
        return _result()

    outcome = run_correction_loop(
        _plan(),
        _result(),
        regenerate=regenerate,
        requery=requery,
        validate=lambda p, r: auto_fix_report,
    )
    assert outcome.status is RunStatus.FAILED
    assert outcome.rounds == 0  # short-circuits immediately, no wasted rounds
    assert requeries["n"] == 0  # AUTO_FIX-only never triggers requery
    assert regenerations["n"] == 0  # no futile regeneration
```

- [ ] **Step 2: Add a scenario where RE_QUERY progresses then the report turns AUTO_FIX-only**

Append this test to `tests/run/test_correction_loop.py`. It proves the loop short-circuits before `max_rounds` once no RE_QUERY issue remains:

```python
def test_short_circuits_when_requery_leaves_only_auto_fix() -> None:
    auto_fix_report = ValidationReport(
        issues=[
            Issue(
                code=IssueCode.OPENAPI_INVALID,
                severity=Severity.ERROR,
                location="paths",
                evidence="invalid schema",
                suggested_fix="fix schema",
            )
        ]
    )
    # round 0 validate -> RE_QUERY (missing); after round 1 -> AUTO_FIX-only.
    reports = [_missing_report(), auto_fix_report]
    calls = {"n": 0}

    def validate(p, r):
        report = reports[calls["n"]]
        calls["n"] += 1
        return report

    requeries = {"n": 0}

    def requery(p, r):
        requeries["n"] += 1
        return p

    outcome = run_correction_loop(
        _plan(),
        _result(),
        regenerate=lambda p: _result(),
        requery=requery,
        validate=validate,
    )
    assert outcome.status is RunStatus.FAILED
    assert outcome.rounds == 1  # one RE_QUERY round, then short-circuit (not 3)
    assert requeries["n"] == 1  # requery ran only for the RE_QUERY round
```

- [ ] **Step 3: Run the two tests to verify they FAIL**

Run: `uv run pytest tests/run/test_correction_loop.py::test_auto_fix_only_does_not_requery tests/run/test_correction_loop.py::test_short_circuits_when_requery_leaves_only_auto_fix -v`
Expected: both FAIL. `test_auto_fix_only_does_not_requery` fails on `assert outcome.rounds == 0` (current code returns 3); the new test fails on `assert outcome.rounds == 1` (current code returns 3).

- [ ] **Step 4: Add the guard and simplify the requery call in `run_correction_loop`**

In `loop_apidoc/run/correction.py`, replace the while-loop body. Current:

```python
    while not report.ok and rounds < max_rounds:
        actionable = actionable_codes(report)
        if not actionable:
            return CorrectionOutcome(
                plan=plan,
                result=result,
                report=annotate_fixability(report),
                rounds=rounds,
                status=RunStatus.EARLY_STOPPED,
            )

        rounds += 1
        if any(
            classify_issue(issue) is CorrectionCategory.RE_QUERY for issue in actionable
        ):
            plan = requery(plan, report)
        result = regenerate(plan)
        report = validate(plan, result)
```

Replace with:

```python
    while not report.ok and rounds < max_rounds:
        actionable = actionable_codes(report)
        if not actionable:
            return CorrectionOutcome(
                plan=plan,
                result=result,
                report=annotate_fixability(report),
                rounds=rounds,
                status=RunStatus.EARLY_STOPPED,
            )

        # AUTO_FIX-only: this round is provably a no-op. The plan only changes
        # via requery (RE_QUERY-driven), and generation is deterministic from
        # the plan, so regenerating would reproduce the identical invalid
        # output and report. Short-circuit to FAILED instead of burning the
        # remaining rounds. Consumes no NotebookLM quota.
        if not any(
            classify_issue(issue) is CorrectionCategory.RE_QUERY for issue in actionable
        ):
            return CorrectionOutcome(
                plan=plan,
                result=result,
                report=annotate_fixability(report),
                rounds=rounds,
                status=RunStatus.FAILED,
            )

        rounds += 1
        plan = requery(plan, report)
        result = regenerate(plan)
        report = validate(plan, result)
```

- [ ] **Step 5: Rewrite the module-level AUTO_FIX `NOTE` comment**

In `loop_apidoc/run/correction.py`, replace the comment block at lines 15-22 (the `# NOTE on AUTO_FIX (v1 limitation): ...` paragraph ending in "is a deferred enhancement.") with:

```python
# NOTE on AUTO_FIX (v1): generation is deterministic from the plan, and v1
# ships no OpenAPI/output repair transform. An AUTO_FIX issue with no
# accompanying RE_QUERY issue therefore cannot change between rounds. The
# correction loop detects this and short-circuits to FAILED immediately (see
# the AUTO_FIX-only guard in run_correction_loop) rather than regenerating the
# identical invalid output until max_rounds. A real autofix transform that
# repairs OPENAPI_INVALID/OUTPUT_MISMATCH from a valid plan remains future work.
```

- [ ] **Step 6: Run the full correction-loop test file to verify all pass**

Run: `uv run pytest tests/run/test_correction_loop.py -v`
Expected: PASS — all tests, including the unchanged `test_passes_on_first_validation`, `test_recovers_within_three_rounds`, `test_final_failure_after_three_rounds`, `test_early_stop_on_unfixable_only`.

- [ ] **Step 7: Run the integration scenarios and fix any AUTO_FIX-only round-count assertion**

Run: `uv run pytest tests/integration/test_correction_scenarios.py -v`
Expected: PASS. If a scenario asserted an AUTO_FIX-only failure burns 3 rounds, update its expected `rounds` to the short-circuit value (the round count at which the report first becomes AUTO_FIX-only — `0` if AUTO_FIX-only from the first validation). Do NOT loosen any PASSED/EARLY_STOPPED/RE_QUERY assertions.

- [ ] **Step 8: Run the whole suite to confirm no regressions**

Run: `uv run pytest -q`
Expected: PASS (prior baseline 202 passed + 1 skipped; count may rise by the one added test).

- [ ] **Step 9: Commit**

```bash
git add loop_apidoc/run/correction.py tests/run/test_correction_loop.py tests/integration/test_correction_scenarios.py
git commit -m "fix: [ run ] short-circuit AUTO_FIX-only correction rounds to FAILED"
```

---

## Post-Implementation: memory update

Not a code task — do this after Task 1 lands. Update the plan-sequence memory at
`/Users/carl/.claude/projects/-Users-carl-Dev-CMG-Loop-ApiDoc/memory/loop-apidoc-plan-sequence.md`:
edit Plan 6 deferral #1 to note the AUTO_FIX-only short-circuit is implemented (rounds=0/early FAILED, no quota), leaving only "a real autofix repair transform" as future work.

---

## Self-Review

**Spec coverage:**
- Predictive guard in `run_correction_loop` → Task 1 Step 4. ✓
- Reuse `FAILED` status → Step 4 (returns `RunStatus.FAILED`). ✓
- Simplify requery to unconditional → Step 4. ✓
- Behavior table (AUTO_FIX-only rounds 3→0; RE_QUERY-then-AUTO_FIX early stop) → Steps 1, 2. ✓
- Unchanged PASSED/EARLY_STOPPED/RE_QUERY behavior → Step 6 (existing tests untouched). ✓
- NOTE comment rewrite → Step 5. ✓
- Integration scenario update → Step 7. ✓
- Memory deferral #1 update → Post-Implementation section. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; every run step shows exact command + expected outcome. ✓

**Type consistency:** `run_correction_loop`, `CorrectionOutcome`, `RunStatus.FAILED`, `CorrectionCategory.RE_QUERY`, `actionable_codes`, `classify_issue`, `annotate_fixability` all match the names in `loop_apidoc/run/correction.py` and `loop_apidoc/run/models.py`. Test helpers `_plan()`, `_result()`, `_missing_report()` already exist in the test file. ✓
