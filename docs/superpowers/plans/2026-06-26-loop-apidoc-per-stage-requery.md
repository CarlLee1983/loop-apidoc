# per-stage requery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the correction loop's requery re-run only the extraction stages relevant to the failing issues (security→04, endpoint→05+06) instead of re-running all 10 stages, saving NotebookLM quota.

**Architecture:** Extract the per-stage extraction body into a shared `_run_stage` helper; add `rerun_stages(prior, stage_ids)` that re-queries only the requested stages and merges them with retained prior artifacts; add `stages_for_requery(report)` to map actionable RE_QUERY issues to stage ids; rewire the pipeline's requery closure (extracted to a testable `_make_requery`) to target stages, falling back to a full re-extraction when no stage can be pinned.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, uv. Pure logic over an injected `adapter`/`store`; no real network.

## Global Constraints

- Python ≥ 3.12; Pydantic v2 models; never mutate inputs.
- `run_extraction`'s public behavior, signature, and output MUST stay identical after the refactor (only its body is restructured to call `_run_stage`).
- Coarse issue→stage mapping: `components.securitySchemes*` → `{"04"}`; `paths.*`/`endpoints[*` → `{"05","06"}`. Mapping is by `Issue.location` prefix only — never parse `Issue.evidence`.
- Only ERROR-severity RE_QUERY issues drive requery (use the existing `actionable_codes` + `classify_issue`); AUTO_FIX issues never add stages.
- Empty stage set → fall back to full `run_extraction` (fail-closed; never skip a needed requery).
- Re-run stage's `known_summary` must reflect every earlier stage's latest answer (fresh if re-run, else retained), matching `run_extraction`'s accumulation.
- Do NOT change `build_normalization_plan`, `ExtractionStore`'s persistence format, `classify_issue`, or any §9.5 IssueCode.
- Test commands use `uv run pytest` (no bare `pytest`, no `pip`).
- Commit format `<type>: [ <scope> ] <subject>`; scopes used: `extraction`, `run`. No attribution trailers.

---

### Task 1: Extract `_run_stage` and add `rerun_stages`

**Files:**
- Modify: `loop_apidoc/extraction/orchestrator.py`
- Test: `tests/extraction/test_rerun_stages.py` (create)

**Interfaces:**
- Consumes (existing, unchanged):
  - `STAGES`, `QueryStage`, `QueryKind`, `StageMode` from `loop_apidoc.extraction.stages`.
  - `build_question`, `build_known_summary` from `loop_apidoc.extraction.questions`.
  - `extract_json_block`, `find_gaps` from `loop_apidoc.extraction.jsonblock`.
  - `AnswerArtifact`, `ExtractionResult` from `loop_apidoc.extraction.models`;
    `ExtractionResult.for_stage(id) -> list[AnswerArtifact]`, `.initial(id) -> AnswerArtifact | None`.
  - `_ask_and_store(adapter, store, stage, kind, question, notebook_url, max_attempts) -> AnswerArtifact` (existing module-private helper).
- Produces (used by Task 3):
  - `rerun_stages(adapter, notebook_url, store, prior: ExtractionResult, stage_ids: set[str], *, max_attempts: int = 3) -> ExtractionResult`
  - `_run_stage(adapter, store, stage, known: str, notebook_url: str, max_attempts: int) -> list[AnswerArtifact]` (module-private; INITIAL first in the returned list).

- [ ] **Step 1: Write the failing tests**

Create `tests/extraction/test_rerun_stages.py`:

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.extraction.models import ExtractionResult
from loop_apidoc.extraction.orchestrator import rerun_stages, run_extraction
from loop_apidoc.extraction.stages import STAGES
from loop_apidoc.extraction.store import ExtractionStore

NB = "https://notebooklm.google.com/notebook/abc"


class _FakeAskResult:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.returncode = 0


class _MarkerAdapter:
    """Records every question and returns a per-stage, per-call marker answer.

    The marker (`ANSWER-<stage_id>-<n>`) lets tests detect which stage produced
    an answer and whether a re-run produced a *fresh* one (higher n). Stages are
    identified by their goal text (INITIAL) or `Topic: <title>` (FOLLOWUP/REVERSE)
    embedded in the question. Returns prose-shaped markers, so structured stages
    find no JSON block and never emit a follow-up — keeping query counts simple
    (2 per stage: initial + reverse)."""

    def __init__(self) -> None:
        self.questions: list[str] = []
        self._counts: dict[str, int] = {}

    def ask(self, question: str, notebook_url: str) -> _FakeAskResult:
        self.questions.append(question)
        for stage in STAGES:
            if stage.goal in question or f"Topic: {stage.title}" in question:
                self._counts[stage.stage_id] = self._counts.get(stage.stage_id, 0) + 1
                return _FakeAskResult(f"ANSWER-{stage.stage_id}-{self._counts[stage.stage_id]}")
        return _FakeAskResult("ANSWER-unknown")


def _goal(stage_id: str) -> str:
    return next(s.goal for s in STAGES if s.stage_id == stage_id)


def test_rerun_only_queries_requested_stage(tmp_path: Path) -> None:
    store = ExtractionStore(tmp_path)
    adapter = _MarkerAdapter()
    prior = run_extraction(adapter, NB, store)
    adapter.questions.clear()

    merged = rerun_stages(adapter, NB, store, prior, {"04"})

    # Only stage 04 was queried: 2 questions (initial + reverse).
    assert len(adapter.questions) == 2
    assert all(_goal("04") in q or "Topic: Authentication" in q for q in adapter.questions)


def test_rerun_retains_other_stages_and_refreshes_target(tmp_path: Path) -> None:
    store = ExtractionStore(tmp_path)
    adapter = _MarkerAdapter()
    prior = run_extraction(adapter, NB, store)

    merged = rerun_stages(adapter, NB, store, prior, {"04"})

    # Non-target stage 05 artifacts are the retained prior ones (identical).
    assert merged.for_stage("05") == prior.for_stage("05")
    # Target stage 04 got a fresh initial answer (higher marker count than prior).
    assert prior.initial("04").answer == "ANSWER-04-1"
    assert merged.initial("04").answer == "ANSWER-04-2"
    # Every stage still represented exactly once for its initial.
    assert {s.stage_id for s in STAGES} == {a.stage_id for a in merged.artifacts}


def test_rerun_context_includes_fresh_prior_stage(tmp_path: Path) -> None:
    store = ExtractionStore(tmp_path)
    adapter = _MarkerAdapter()
    prior = run_extraction(adapter, NB, store)
    adapter.questions.clear()

    rerun_stages(adapter, NB, store, prior, {"05", "06"})

    # Stage 06's INITIAL question must carry the FRESH stage-05 answer (run 2),
    # proving the known_summary accumulator uses re-run answers, not retained ones.
    six_initial = next(q for q in adapter.questions if _goal("06") in q)
    assert "ANSWER-05-2" in six_initial


def test_rerun_far_fewer_queries_than_full(tmp_path: Path) -> None:
    store = ExtractionStore(tmp_path)
    adapter = _MarkerAdapter()
    prior = run_extraction(adapter, NB, store)
    full_count = len(adapter.questions)
    adapter.questions.clear()

    rerun_stages(adapter, NB, store, prior, {"05", "06"})
    assert len(adapter.questions) == 4  # 2 stages x (initial + reverse)
    assert len(adapter.questions) < full_count
```

- [ ] **Step 2: Run the tests to verify they FAIL**

Run: `uv run pytest tests/extraction/test_rerun_stages.py -v`
Expected: FAIL with `ImportError: cannot import name 'rerun_stages'` (function does not exist yet).

- [ ] **Step 3: Refactor `run_extraction` to use `_run_stage`, and add `rerun_stages`**

In `loop_apidoc/extraction/orchestrator.py`, replace the `run_extraction` function with the following two functions plus the new `_run_stage` helper (keep the existing imports and `_ask_and_store` unchanged):

```python
def _run_stage(
    adapter: NotebookLMAdapter,
    store: ExtractionStore,
    stage: QueryStage,
    known: str,
    notebook_url: str,
    max_attempts: int,
) -> list[AnswerArtifact]:
    """Run one stage: INITIAL, optional FOLLOWUP (structured gaps), then REVERSE.

    The INITIAL artifact is always the first element of the returned list.
    """
    artifacts: list[AnswerArtifact] = []

    initial_q = build_question(
        stage, QueryKind.INITIAL, notebook_url=notebook_url, known_summary=known
    )
    initial = _ask_and_store(
        adapter, store, stage, QueryKind.INITIAL, initial_q, notebook_url, max_attempts
    )
    artifacts.append(initial)

    if stage.mode is StageMode.STRUCTURED:
        block = extract_json_block(initial.answer)
        gaps = find_gaps(block) if block is not None else []
        if gaps:
            followup_q = build_question(
                stage, QueryKind.FOLLOWUP, notebook_url=notebook_url,
                known_summary=known, pending_fields=gaps,
            )
            artifacts.append(
                _ask_and_store(adapter, store, stage, QueryKind.FOLLOWUP,
                               followup_q, notebook_url, max_attempts)
            )

    reverse_q = build_question(
        stage, QueryKind.REVERSE, notebook_url=notebook_url, known_summary=known
    )
    artifacts.append(
        _ask_and_store(adapter, store, stage, QueryKind.REVERSE,
                       reverse_q, notebook_url, max_attempts)
    )
    return artifacts


def run_extraction(
    adapter: NotebookLMAdapter,
    notebook_url: str,
    store: ExtractionStore,
    *,
    max_attempts: int = 3,
) -> ExtractionResult:
    artifacts: list[AnswerArtifact] = []
    prior_initials: list[tuple[str, str]] = []

    for stage in STAGES:
        known = build_known_summary(prior_initials)
        stage_artifacts = _run_stage(
            adapter, store, stage, known, notebook_url, max_attempts
        )
        artifacts.extend(stage_artifacts)
        prior_initials.append((stage.title, stage_artifacts[0].answer))

    return ExtractionResult(notebook_url=notebook_url, artifacts=artifacts)


def rerun_stages(
    adapter: NotebookLMAdapter,
    notebook_url: str,
    store: ExtractionStore,
    prior: ExtractionResult,
    stage_ids: set[str],
    *,
    max_attempts: int = 3,
) -> ExtractionResult:
    """Re-query only `stage_ids`; retain prior artifacts for every other stage.

    Iterates STAGES in order so a re-run stage's known_summary reflects each
    earlier stage's latest answer (fresh if re-run this round, else retained).
    Returns a merged ExtractionResult consumable by build_normalization_plan
    unchanged.
    """
    artifacts: list[AnswerArtifact] = []
    prior_initials: list[tuple[str, str]] = []

    for stage in STAGES:
        if stage.stage_id in stage_ids:
            known = build_known_summary(prior_initials)
            stage_artifacts = _run_stage(
                adapter, store, stage, known, notebook_url, max_attempts
            )
            artifacts.extend(stage_artifacts)
            initial_answer = stage_artifacts[0].answer
        else:
            retained = prior.for_stage(stage.stage_id)
            artifacts.extend(retained)
            retained_initial = prior.initial(stage.stage_id)
            initial_answer = retained_initial.answer if retained_initial else ""
        prior_initials.append((stage.title, initial_answer))

    return ExtractionResult(notebook_url=notebook_url, artifacts=artifacts)
```

- [ ] **Step 4: Run the new tests to verify they PASS**

Run: `uv run pytest tests/extraction/test_rerun_stages.py -v`
Expected: PASS — all 4 tests.

- [ ] **Step 5: Run the existing extraction suite to confirm the refactor is behavior-preserving**

Run: `uv run pytest tests/extraction -q`
Expected: PASS — all pre-existing orchestrator tests still green (artifact ids, ordering, follow-up-only-on-gaps unchanged).

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/extraction/orchestrator.py tests/extraction/test_rerun_stages.py
git commit -m "feat: [ extraction ] add rerun_stages for targeted re-extraction"
```

---

### Task 2: `stages_for_requery` issue→stage mapping

**Files:**
- Create: `loop_apidoc/run/requery.py`
- Test: `tests/run/test_requery.py`

**Interfaces:**
- Consumes:
  - `actionable_codes(report) -> list[Issue]` and `classify_issue(issue) -> CorrectionCategory` from `loop_apidoc.run.correction`.
  - `CorrectionCategory` from `loop_apidoc.run.models`.
  - `Issue`, `IssueCode`, `Severity`, `ValidationReport` from `loop_apidoc.validate.models`.
- Produces (used by Task 3): `stages_for_requery(report: ValidationReport) -> set[str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/run/test_requery.py`:

```python
from __future__ import annotations

from loop_apidoc.run.requery import stages_for_requery
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def _issue(code: IssueCode, severity: Severity, location: str) -> Issue:
    return Issue(code=code, severity=severity, location=location,
                 evidence="e", suggested_fix="f")


def _report(*issues: Issue) -> ValidationReport:
    return ValidationReport(issues=list(issues))


def test_security_issue_maps_to_stage_04() -> None:
    report = _report(_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR,
                            "components.securitySchemes"))
    assert stages_for_requery(report) == {"04"}


def test_endpoint_path_issue_maps_to_05_and_06() -> None:
    report = _report(_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR,
                            "paths./users.get"))
    assert stages_for_requery(report) == {"05", "06"}


def test_endpoint_index_issue_maps_to_05_and_06() -> None:
    report = _report(_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR,
                            "endpoints[0]"))
    assert stages_for_requery(report) == {"05", "06"}


def test_mixed_security_and_endpoint() -> None:
    report = _report(
        _issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR, "components.securitySchemes"),
        _issue(IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR, "paths./u.post"),
    )
    assert stages_for_requery(report) == {"04", "05", "06"}


def test_warning_severity_is_not_actionable() -> None:
    # summary/examples-missing are WARNING REQUIRED_INFO_MISSING -> not actionable.
    report = _report(_issue(IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING,
                            "paths./u.get"))
    assert stages_for_requery(report) == set()


def test_non_requery_codes_are_ignored() -> None:
    report = _report(
        _issue(IssueCode.SOURCE_CONFLICT, Severity.ERROR, "conflict.auth"),
        _issue(IssueCode.OPENAPI_INVALID, Severity.ERROR, "paths"),
    )
    assert stages_for_requery(report) == set()


def test_empty_report() -> None:
    assert stages_for_requery(_report()) == set()
```

- [ ] **Step 2: Run the tests to verify they FAIL**

Run: `uv run pytest tests/run/test_requery.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.run.requery'`.

- [ ] **Step 3: Create the mapping module**

Create `loop_apidoc/run/requery.py`:

```python
from __future__ import annotations

from loop_apidoc.run.correction import actionable_codes, classify_issue
from loop_apidoc.run.models import CorrectionCategory
from loop_apidoc.validate.models import ValidationReport


def stages_for_requery(report: ValidationReport) -> set[str]:
    """Map actionable RE_QUERY issues to the extraction stages that produced them.

    Coarse mapping (spec deferral #3): endpoint-shaped issues bundle stages 05
    (inventory) and 06 (details); security issues map to stage 04. Mapping is by
    Issue.location prefix only. An empty result means the locations could not be
    pinned to a stage — the caller falls back to a full re-extraction.
    """
    stages: set[str] = set()
    for issue in actionable_codes(report):
        if classify_issue(issue) is not CorrectionCategory.RE_QUERY:
            continue
        location = issue.location
        if location.startswith("components.securitySchemes"):
            stages.add("04")
        elif location.startswith("paths.") or location.startswith("endpoints["):
            stages.update({"05", "06"})
    return stages
```

- [ ] **Step 4: Run the tests to verify they PASS**

Run: `uv run pytest tests/run/test_requery.py -v`
Expected: PASS — all 7 tests.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/run/requery.py tests/run/test_requery.py
git commit -m "feat: [ run ] map actionable RE_QUERY issues to extraction stages"
```

---

### Task 3: Wire targeted requery into the pipeline

**Files:**
- Modify: `loop_apidoc/run/pipeline.py`
- Test: `tests/run/test_make_requery.py` (create)

**Interfaces:**
- Consumes:
  - `rerun_stages(adapter, notebook_url, store, prior, stage_ids, *, max_attempts=3)` and `run_extraction(adapter, notebook_url, store)` from `loop_apidoc.extraction.orchestrator` (Task 1).
  - `stages_for_requery(report) -> set[str]` from `loop_apidoc.run.requery` (Task 2).
  - existing `build_normalization_plan`, `ExtractionStore`, `_persist_plan`.
- Produces: module-level `_make_requery(*, adapter, notebook_url, store, manifest, run_dir, state) -> Callable[[plan, report], plan]` where `state` is a dict holding `{"extraction": ExtractionResult}` (mutated in place across rounds).

- [ ] **Step 1: Write the failing tests**

Create `tests/run/test_make_requery.py`:

```python
from __future__ import annotations

from pathlib import Path

import loop_apidoc.run.pipeline as pipeline
from loop_apidoc.extraction.models import ExtractionResult
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def _endpoint_report() -> ValidationReport:
    return ValidationReport(issues=[Issue(
        code=IssueCode.REQUIRED_INFO_MISSING, severity=Severity.ERROR,
        location="paths./u.get", evidence="no responses", suggested_fix="add")])


def _unmappable_report() -> ValidationReport:
    # An actionable RE_QUERY issue whose location matches no stage prefix.
    return ValidationReport(issues=[Issue(
        code=IssueCode.REQUIRED_INFO_MISSING, severity=Severity.ERROR,
        location="mystery.location", evidence="x", suggested_fix="y")])


def _patch_common(monkeypatch):
    sentinel = ExtractionResult(notebook_url="nb")
    monkeypatch.setattr(pipeline, "build_normalization_plan",
                        lambda extraction, manifest: "PLAN")
    monkeypatch.setattr(pipeline, "_persist_plan", lambda run_dir, plan: None)
    return sentinel


def test_requery_targets_mapped_stages(monkeypatch, tmp_path: Path) -> None:
    sentinel = _patch_common(monkeypatch)
    calls = {}
    monkeypatch.setattr(pipeline, "rerun_stages",
                        lambda *a, **k: calls.__setitem__("rerun", a) or sentinel)
    monkeypatch.setattr(pipeline, "run_extraction",
                        lambda *a, **k: calls.__setitem__("full", True) or sentinel)

    state = {"extraction": ExtractionResult(notebook_url="nb")}
    requery = pipeline._make_requery(
        adapter=object(), notebook_url="nb", store=object(),
        manifest=object(), run_dir=tmp_path, state=state)

    new_plan = requery("oldplan", _endpoint_report())

    assert new_plan == "PLAN"
    assert "rerun" in calls and "full" not in calls
    # positional args: (adapter, notebook_url, store, prior, stage_ids)
    assert calls["rerun"][4] == {"05", "06"}
    assert state["extraction"] is sentinel  # holder updated for next round


def test_requery_falls_back_to_full_when_unmappable(monkeypatch, tmp_path: Path) -> None:
    sentinel = _patch_common(monkeypatch)
    calls = {}
    monkeypatch.setattr(pipeline, "rerun_stages",
                        lambda *a, **k: calls.__setitem__("rerun", True) or sentinel)
    monkeypatch.setattr(pipeline, "run_extraction",
                        lambda *a, **k: calls.__setitem__("full", a) or sentinel)

    state = {"extraction": ExtractionResult(notebook_url="nb")}
    requery = pipeline._make_requery(
        adapter=object(), notebook_url="nb", store=object(),
        manifest=object(), run_dir=tmp_path, state=state)

    requery("oldplan", _unmappable_report())

    assert "full" in calls and "rerun" not in calls
    assert state["extraction"] is sentinel
```

- [ ] **Step 2: Run the tests to verify they FAIL**

Run: `uv run pytest tests/run/test_make_requery.py -v`
Expected: FAIL with `AttributeError: module 'loop_apidoc.run.pipeline' has no attribute '_make_requery'`.

- [ ] **Step 3: Add `_make_requery` and rewire `run_pipeline`**

In `loop_apidoc/run/pipeline.py`, add these imports next to the existing ones:

```python
from loop_apidoc.extraction.orchestrator import rerun_stages, run_extraction
from loop_apidoc.run.requery import stages_for_requery
```

(The module already imports `run_extraction`; change that line to the combined `rerun_stages, run_extraction` import above and remove the old standalone `run_extraction` import.)

Add this module-level factory (e.g. above `run_pipeline`):

```python
def _make_requery(*, adapter, notebook_url, store, manifest, run_dir, state):
    """Build the correction-loop requery closure.

    Targets only the stages the report's actionable RE_QUERY issues map to;
    falls back to a full re-extraction when none can be pinned. `state` holds
    the current ExtractionResult and is updated in place so each round re-runs
    against the latest extraction.
    """
    def requery(p, r):
        stages = stages_for_requery(r)
        if stages:
            fresh = rerun_stages(adapter, notebook_url, store, state["extraction"], stages)
        else:
            fresh = run_extraction(adapter, notebook_url, store)
        state["extraction"] = fresh
        new_plan = build_normalization_plan(fresh, manifest)
        _persist_plan(run_dir, new_plan)
        return new_plan

    return requery
```

Then, inside `run_pipeline`, replace the existing extraction + inline `requery` closure. Current:

```python
    store = ExtractionStore(run_dir / "extraction")
    extraction = run_extraction(adapter, notebook_url, store)
    plan = build_normalization_plan(extraction, manifest)
    _persist_plan(run_dir, plan)

    result = generate_outputs(plan, manifest, run_dir)

    def regenerate(p):
        return generate_outputs(p, manifest, run_dir)

    def validate(p, r):
        return validate_outputs(p, r, manifest)

    def requery(p, r):
        fresh = run_extraction(adapter, notebook_url, store)
        new_plan = build_normalization_plan(fresh, manifest)
        _persist_plan(run_dir, new_plan)
        return new_plan
```

Replace with:

```python
    store = ExtractionStore(run_dir / "extraction")
    extraction = run_extraction(adapter, notebook_url, store)
    state = {"extraction": extraction}
    plan = build_normalization_plan(extraction, manifest)
    _persist_plan(run_dir, plan)

    result = generate_outputs(plan, manifest, run_dir)

    def regenerate(p):
        return generate_outputs(p, manifest, run_dir)

    def validate(p, r):
        return validate_outputs(p, r, manifest)

    requery = _make_requery(
        adapter=adapter, notebook_url=notebook_url, store=store,
        manifest=manifest, run_dir=run_dir, state=state,
    )
```

Leave the `run_correction_loop(...)` call and everything after it unchanged.

- [ ] **Step 4: Run the new tests to verify they PASS**

Run: `uv run pytest tests/run/test_make_requery.py -v`
Expected: PASS — both tests.

- [ ] **Step 5: Run the run + pipeline integration suites for regressions**

Run: `uv run pytest tests/run tests/integration -q`
Expected: PASS. In particular `tests/integration/test_run_pipeline.py` (full pipeline, auth-block + run-dir layout) still passes — the happy path and BLOCKED path are unaffected by the requery rewiring.

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS (baseline 212 passed + 1 skipped; count rises by the added tests).

- [ ] **Step 7: Commit**

```bash
git add loop_apidoc/run/pipeline.py tests/run/test_make_requery.py
git commit -m "feat: [ run ] target requery to affected stages with full-extraction fallback"
```

---

## Post-Implementation: memory update

Not a code task — do this after Task 3 lands. Update the plan-sequence memory at
`/Users/carl/.claude/projects/-Users-carl-Dev-CMG-Loop-ApiDoc/memory/loop-apidoc-plan-sequence.md`:
edit Plan 6 deferral #3 to note per-stage requery is implemented — `rerun_stages` re-queries only
mapped stages (security→04, endpoint→05+06 via `stages_for_requery`), retains the rest, rebuilds the
plan from the merged extraction; falls back to full `run_extraction` when no stage maps; orchestrator
refactored to a shared `_run_stage`. No remaining sub-items for #3.

---

## Self-Review

**Spec coverage:**
- Orchestrator `_run_stage` refactor, behavior-preserving → Task 1 Steps 3, 5. ✓
- `rerun_stages` targeted re-extraction + merge + context chain → Task 1 Step 3; tested Steps 1 (retention, freshness, fresh-context, query count). ✓
- `stages_for_requery` coarse location mapping, RE_QUERY/ERROR only → Task 2. ✓
- Empty-set fallback to full `run_extraction` → Task 3 `_make_requery`; tested `test_requery_falls_back_to_full_when_unmappable`. ✓
- Pipeline holder retains extraction across rounds → Task 3 `state` dict; tested holder update. ✓
- No change to build_normalization_plan / store format / classify_issue → none of the tasks touch them. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; every run step has an exact command + expected outcome. ✓

**Type consistency:** `rerun_stages` / `_run_stage` / `run_extraction` signatures identical between Task 1 (definition) and Task 3 (call); `stages_for_requery(report) -> set[str]` identical between Task 2 (def) and Task 3 (call). `_make_requery` keyword params match its call site in `run_pipeline`. `state["extraction"]` is the holder in both `_make_requery` and `run_pipeline`. The `_MarkerAdapter.ask` return object exposes `.answer`/`.returncode`, matching what `_ask_and_store`/`run_with_retries` consume (the existing `_FakeAdapter` uses the same shape). ✓
