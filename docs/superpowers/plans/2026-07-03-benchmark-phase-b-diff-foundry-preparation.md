# Benchmark Phase B — diff / foundry multi-version / preparation + score verdict Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `tests/test_benchmarks.py` so `diff`, `foundry` multi-version governance, `preparation`, and `score` loop-verdict are each exercised against the real committed benchmark run dirs, closing their benchmark-coverage gap.

**Architecture:** Six new tests (three parametrized over all cases, three non-parametrized on the `stripe-basic-rest` representative case) are appended to `tests/test_benchmarks.py`. A small refactor extracts the existing `assembled` fixture body into a memoized module-level helper so the non-parametrized tests can reuse the same read-only run dir. All new tests consume already-public APIs of `loop_apidoc.diff`, `loop_apidoc.foundry`, `loop_apidoc.preparation`, and `loop_apidoc.score`.

**Tech Stack:** Python ≥3.11, `uv`, pytest, pydantic v2. No new dependencies.

## Global Constraints

- Python `>=3.11`, `uv` (no `pip`). Run tests via `uv run pytest`.
- **Only** `tests/test_benchmarks.py` is modified. No product-code changes; no edits to `benchmarks/**` data or `expected/*.json`.
- The Phase A `assembled` run dir is treated **read-only** by every new consumer. Any test needing a mutated or second copy `copytree`s into its own `tmp_path` first — it never writes into the shared run dir.
- `_FIXED_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)` is the single fixed timestamp wherever determinism matters. Where two distinct foundry approvals are needed (supersession), the second uses `_FIXED_TS + timedelta(seconds=1)` — still deterministic, because `make_asset_id` derives the id from `now` at one-second resolution and identical timestamps would collide.
- **TDD inversion:** every subsystem under test already exists, so each new benchmark test is expected to **PASS on first run** against real data. A failure is a genuine subsystem finding — stop and investigate with superpowers:systematic-debugging rather than weakening the test.
- A case whose `sources/` is absent SKIPs (inherited from Phase A). Non-parametrized tests skip the same way when the representative case's sources are absent.

---

## Verified facts this plan relies on (confirmed by running the real code against committed data)

These were empirically confirmed before writing the plan; the task code encodes them directly:

- **diff identity:** `build_diff_report(A, copytree(A))` over a benchmark run dir yields **zero** `breaking`/`additive`/`changed` findings (and, for a byte-identical copytree, zero `source_only` too — but `source_only` is *allowed* to be non-empty and is never asserted on).
- **diff mutation (stripe):** removing the `/capture` endpoint → exactly one `breaking` "operation removed"; adding a new `/v1/payment_intents/{intent}/increment_authorization` endpoint → exactly one `additive` "operation added"; flipping the `PaymentIntent.description` schema field from `required:true` to `required:false` → exactly one `changed` "property no longer required" at `components.schemas.PaymentIntent.description`.
- **foundry supersession (stripe, PASS case):** approving v1 (`now=_FIXED_TS`) then v2 (`now=_FIXED_TS + 1s`) transitions v1's asset to `AssetStatus.SUPERSEDED`; `load_current_asset` resolves to v2's asset id.
- **foundry `min_score` gate:** `approve_candidate` reads the candidate's score from `<candidate>/score/score.json` (via `_read_score`). The assembled run dir has **no** score file, so the gate test must first compute the score and write it into the candidate copy with `score.write_reports(report, run_dir / "score")` **before** `import_run`. With a real score present, `min_score = score + 1` raises `FoundryApprovalError`; `min_score = score` succeeds. `allow_failing` does **not** bypass the `min_score` gate (it only bypasses the validation-ok gate), so the success path uses a `min_score` the run meets, not `allow_failing`.
- **preparation (stripe, PASS case):** `preparation-report.json` parses to `PreparationReport`; `status = needs_attention`; 4 phases; all finding severities are `warning`. Invariant: a validation-PASS case is never `blocked`.
- **score verdict (stripe):** `evaluate_score` (CI profile) → `score=78`, `min_score=85`, 6 findings; `classify_findings` partitions them losslessly; `loop_verdict(prev_score=None, curr_score=78, target=85, round_index=1, max_rounds=3, findings=...)` → `plateau` (deterministic across a second call). The `score >= min_score ⇒ CONVERGED` coupling invariant is asserted only when it applies.

---

## File Structure

Single file touched: `tests/test_benchmarks.py`. New module-level additions, in append order:

- `_assemble_case(case, tmp_path_factory) -> RunResult` — memoized assemble+skip helper (extracted from the current `assembled` fixture body).
- `_case_by_name(name) -> Path` — resolve a benchmark case dir by folder name.
- `_STRIPE = "stripe-basic-rest"` — module constant for the representative case.
- `_mutate_stripe_extraction(src, dst) -> None` — copytree + three known mutations for the diff detection test.
- `test_benchmark_diff_identity(case, assembled)` — parametrized.
- `test_benchmark_diff_detects_change(tmp_path_factory, tmp_path)` — non-parametrized (stripe).
- `test_benchmark_foundry_supersession(tmp_path_factory, tmp_path)` — non-parametrized (stripe).
- `test_benchmark_foundry_min_score_gate(tmp_path_factory, tmp_path)` — non-parametrized (stripe).
- `test_benchmark_preparation(case, assembled)` — parametrized.
- `test_benchmark_score_verdict(case, assembled)` — parametrized.

---

### Task 1: Imports + memoized assemble helper (refactor, no behavior change)

Extract the `assembled` fixture body into a reusable memoized helper and add every Phase B import. This must leave the existing suite byte-for-byte green.

**Files:**
- Modify: `tests/test_benchmarks.py` (import block lines 16–35; fixture lines 75–88)

**Interfaces:**
- Produces: `_assemble_case(case: Path, tmp_path_factory) -> RunResult` (skips if no sources, memoizes in `_ASSEMBLED`), `_case_by_name(name: str) -> Path`, `_STRIPE: str`. The `assembled` fixture now delegates to `_assemble_case`.

- [ ] **Step 1: Extend the import block**

Replace the existing import block (the `from datetime …` line and the `loop_apidoc` imports) so it reads exactly:

```python
import json
import shutil
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from openapi_spec_validator import validate as validate_openapi

from loop_apidoc.agentcli.assemble import run_assemble_pipeline
from loop_apidoc.diff import DiffImpact, build_diff_report, load_run_artifacts
from loop_apidoc.foundry import store as foundry_store
from loop_apidoc.foundry.approve import approve_candidate
from loop_apidoc.foundry.importer import import_run
from loop_apidoc.foundry.models import AssetStatus, Docset, FoundryApprovalError
from loop_apidoc.foundry.query import load_current_asset, resolve_current_artifact
from loop_apidoc.foundry.register import register_docset
from loop_apidoc.preparation import PreparationReport, PreparationSeverity, PreparationStatus
from loop_apidoc.run.models import RunResult
from loop_apidoc.score import (
    LoopVerdict,
    ScoreProfile,
    classify_findings,
    evaluate_score,
    load_score_inputs,
    loop_verdict,
)
from loop_apidoc.score import write_reports as write_score_reports
```

- [ ] **Step 2: Add the memoized helper + `_case_by_name` + `_STRIPE`, and slim the fixture**

The module already defines `_ASSEMBLED: dict[str, RunResult] = {}` above the fixture — keep it. Replace the current `assembled` fixture (lines 75–88) with the helper plus a thin fixture, and add the case-name helpers just below `_ASSEMBLED`:

```python
_STRIPE = "stripe-basic-rest"


def _case_by_name(name: str) -> Path:
    return _BENCH_ROOT / name


def _assemble_case(case: Path, tmp_path_factory) -> RunResult:
    """Assemble a case at most once per session and memoize the RunResult.

    Skips when the case's operator-provided sources are absent. The produced run
    dir is treated read-only by every consumer (score reads it; foundry/diff
    copytree FROM it), so a single shared dir is safe. Non-parametrized tests
    reuse this same helper via `_case_by_name` so they never re-assemble."""
    if not _has_sources(case):
        pytest.skip(f"{case.name}: sources/ not present (operator-provided, gitignored)")
    if case.name not in _ASSEMBLED:
        out = tmp_path_factory.mktemp(f"bench-{case.name}")
        _ASSEMBLED[case.name] = run_assemble_pipeline(
            sources_root=case / "sources",
            extraction_dir=case / "extraction",
            output_root=out,
            run_id="bench",
            generated_at=_FIXED_TS,
        )
    return _ASSEMBLED[case.name]


@pytest.fixture
def assembled(case, tmp_path_factory):
    return _assemble_case(case, tmp_path_factory)
```

- [ ] **Step 3: Run the full existing suite to verify no regression**

Run: `uv run pytest tests/test_benchmarks.py -v`
Expected: PASS — the identical set of Phase A tests (`test_benchmark_case`, `test_benchmark_score`, `test_benchmark_foundry`, `test_benchmark_harness_discovers_cases`) with the same pass/skip pattern as before the refactor. (`RunResult`, `evaluate_score`, `load_score_inputs`, `ScoreProfile` remain imported and used, so no unused-import lint.)

- [ ] **Step 4: Lint**

Run: `uv run ruff check tests/test_benchmarks.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: [benchmarks] extract memoized assemble helper for Phase B reuse"
```

---

### Task 2: `test_benchmark_diff_identity` — spurious-diff regression net (Component 1a)

Diffing a run against an identical copy must yield no semantic change.

**Files:**
- Modify: `tests/test_benchmarks.py` (append test)

**Interfaces:**
- Consumes: `case` fixture (`Path`), `assembled` fixture (`RunResult`), `load_run_artifacts`, `build_diff_report`, `DiffImpact`.

- [ ] **Step 1: Write the test (TDD inversion — expected to PASS immediately)**

```python
def test_benchmark_diff_identity(case, assembled, tmp_path) -> None:
    """Diffing a run against a byte-identical copy of itself yields no semantic
    change. `source_only` differences (provenance/manifest source paths) are
    allowed and never asserted on; the breaking/additive/changed sets must be
    empty. This is the spurious-diff regression net."""
    run_dir = Path(assembled.run_dir)
    copy = tmp_path / "identical" / run_dir.name
    shutil.copytree(run_dir, copy)

    report = build_diff_report(load_run_artifacts(run_dir), load_run_artifacts(copy))
    semantic = [
        f for f in report.findings
        if f.impact in {DiffImpact.BREAKING, DiffImpact.ADDITIVE, DiffImpact.CHANGED}
    ]
    assert not semantic, (
        f"{case.name}: self-diff produced spurious semantic findings — "
        f"{[(f.impact.value, f.location, f.summary) for f in semantic]}"
    )
```

- [ ] **Step 2: Run to verify it PASSES**

Run: `uv run pytest tests/test_benchmarks.py -v -k diff_identity`
Expected: PASS for every case with local sources, SKIP otherwise. A non-empty `semantic` list is a genuine `diff` finding — investigate with superpowers:systematic-debugging, do not weaken the assertion.

- [ ] **Step 3: Lint**

Run: `uv run ruff check tests/test_benchmarks.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: [benchmarks] diff self-identity yields no semantic change"
```

---

### Task 3: `test_benchmark_diff_detects_change` — controlled mutation (Component 1b)

A single non-parametrized test on `stripe-basic-rest`: mutate the committed extraction three ways, re-assemble, and assert all three `DiffImpact` classes appear, anchored to the mutated operation/field.

**Files:**
- Modify: `tests/test_benchmarks.py` (append `_mutate_stripe_extraction` helper + test)

**Interfaces:**
- Consumes: `_assemble_case`, `_case_by_name`, `_STRIPE`, `run_assemble_pipeline`, `load_run_artifacts`, `build_diff_report`, `DiffImpact`, `_FIXED_TS`.
- Produces: `_mutate_stripe_extraction(src: Path, dst: Path) -> None` — copytree `src`→`dst`, then apply the three mutations (proven to yield one finding each).

- [ ] **Step 1: Write the mutation helper**

```python
def _mutate_stripe_extraction(src: Path, dst: Path) -> None:
    """Copytree the stripe extraction dir `src` into `dst`, then apply three
    known mutations that each produce exactly one diff finding:
      (breaking) remove the /capture endpoint (ep5.json + inventory entry),
      (additive) add a new increment_authorization endpoint (ep6.json + entry),
      (changed)  flip PaymentIntent.description from required:true to false.
    Proven against real stripe data before this plan was written."""
    shutil.copytree(src, dst)
    inv = json.loads((dst / "inventory.json").read_text("utf-8"))

    # (breaking) remove the capture endpoint
    inv["endpoints"] = [e for e in inv["endpoints"] if not e["path"].endswith("/capture")]
    (dst / "endpoints" / "ep5.json").unlink()

    # (additive) add a brand-new endpoint (inventory summary + full detail file)
    inv["endpoints"].append({
        "method": "POST",
        "path": "/v1/payment_intents/{intent}/increment_authorization",
        "summary": "Increment an authorization",
        "source": "paths./v1/payment_intents/{intent}/increment_authorization.post",
    })
    ep6 = {
        "method": "POST",
        "path": "/v1/payment_intents/{intent}/increment_authorization",
        "source": "paths./v1/payment_intents/{intent}/increment_authorization.post",
        "parameters": [
            {"name": "amount", "in": "body", "type": "integer", "required": True,
             "description": "New total amount to authorize."},
        ],
        "request": {"content_type": "application/x-www-form-urlencoded",
                    "schema": None, "required": True, "description": "Form body."},
        "responses": [{"status": "200", "description": "Returns the PaymentIntent object.",
                       "schema": None, "schema_ref": "PaymentIntent"}],
        "tags": ["Payment Intents"],
        "security": ["bearerAuth"],
        "examples": [],
        "missing": [],
    }
    (dst / "endpoints" / "ep6.json").write_text(json.dumps(ep6, indent=2), encoding="utf-8")

    # (changed) loosen one required schema field to optional
    for field in inv["schemas"][0]["fields"]:
        if field["name"] == "description":
            field["required"] = False
    (dst / "inventory.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")
```

- [ ] **Step 2: Write the test (TDD inversion — expected to PASS immediately)**

```python
def test_benchmark_diff_detects_change(tmp_path_factory, tmp_path) -> None:
    """stripe baseline vs a v2 built from three known extraction mutations must
    surface one breaking, one additive, and one changed finding, each anchored to
    the mutated operation/field. If the mutated extraction fails to assemble, that
    is a real finding (mutation helper wrong, or assemble regressed) — investigate,
    do not weaken."""
    case = _case_by_name(_STRIPE)
    baseline = _assemble_case(case, tmp_path_factory)  # skips if sources absent

    mutated_ext = tmp_path / "extraction2"
    _mutate_stripe_extraction(case / "extraction", mutated_ext)
    v2 = run_assemble_pipeline(
        sources_root=case / "sources",
        extraction_dir=mutated_ext,
        output_root=tmp_path / "v2_out",
        run_id="v2",
        generated_at=_FIXED_TS,
    )

    report = build_diff_report(
        load_run_artifacts(Path(baseline.run_dir)),
        load_run_artifacts(Path(v2.run_dir)),
    )
    by_impact: dict[DiffImpact, list] = {i: [] for i in DiffImpact}
    for finding in report.findings:
        by_impact[finding.impact].append(finding)

    assert any(
        "capture" in f.location and f.summary == "operation removed"
        for f in by_impact[DiffImpact.BREAKING]
    ), f"missing breaking (capture removed): {[(f.location, f.summary) for f in by_impact[DiffImpact.BREAKING]]}"
    assert any(
        "increment_authorization" in f.location and f.summary == "operation added"
        for f in by_impact[DiffImpact.ADDITIVE]
    ), f"missing additive (increment added): {[(f.location, f.summary) for f in by_impact[DiffImpact.ADDITIVE]]}"
    assert any(
        f.location == "components.schemas.PaymentIntent.description"
        and f.summary == "property no longer required"
        for f in by_impact[DiffImpact.CHANGED]
    ), f"missing changed (description loosened): {[(f.location, f.summary) for f in by_impact[DiffImpact.CHANGED]]}"
```

- [ ] **Step 3: Run to verify it PASSES**

Run: `uv run pytest tests/test_benchmarks.py -v -k diff_detects_change`
Expected: PASS when stripe sources are present, SKIP otherwise.

- [ ] **Step 4: Lint**

Run: `uv run ruff check tests/test_benchmarks.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: [benchmarks] diff detects breaking/additive/changed on mutated stripe"
```

---

### Task 4: foundry supersession + `min_score` gate (Component 2)

Two non-parametrized tests on `stripe-basic-rest` (a PASS case): the supersession path Phase A never reached, and the `min_score` approval gate.

**Files:**
- Modify: `tests/test_benchmarks.py` (append `_score_candidate` helper + two tests)

**Interfaces:**
- Consumes: `_assemble_case`, `_case_by_name`, `_STRIPE`, `_FIXED_TS`, `register_docset`, `import_run`, `approve_candidate`, `load_current_asset`, `foundry_store`, `Docset`, `AssetStatus`, `FoundryApprovalError`, `evaluate_score`, `load_score_inputs`, `ScoreProfile`, `write_score_reports`.
- Produces: `_score_candidate(run_dir: Path) -> int` — compute the CI-profile score for `run_dir`, write `<run_dir>/score/score.json`, and return the integer score.

- [ ] **Step 1: Write the score-writing helper**

```python
def _score_candidate(run_dir: Path) -> int:
    """Compute the CI-profile score for a run dir, write it to <run_dir>/score/
    (the path approve_candidate reads via _read_score), and return the score.
    The assembled run dir has no score.json, so the min_score gate needs this."""
    report = evaluate_score(load_score_inputs(run_dir), profile=ScoreProfile.CI)
    write_score_reports(report, run_dir / "score")
    return report.score
```

- [ ] **Step 2: Write the supersession test (TDD inversion — expected to PASS immediately)**

```python
def test_benchmark_foundry_supersession(tmp_path_factory, tmp_path) -> None:
    """Approving a second asset for the same docset supersedes the first and
    moves the `current` pointer. Two distinct timestamps are required because
    make_asset_id is one-second-resolution; identical timestamps would collide."""
    case = _case_by_name(_STRIPE)
    run = _assemble_case(case, tmp_path_factory)  # skips if sources absent
    run_dir = Path(run.run_dir)

    v1_dir = tmp_path / "runs" / "v1"
    v2_dir = tmp_path / "runs" / "v2"
    shutil.copytree(run_dir, v1_dir)
    shutil.copytree(run_dir, v2_dir)

    root = tmp_path / "project"  # fresh .foundry/, zero pollution
    root.mkdir()
    register_docset(root, Docset(
        docset_id="bench", title=case.name, provider="bench", product="bench",
    ))
    import_run(root, "bench", v1_dir)  # run_id == "v1" (run_dir.name)
    import_run(root, "bench", v2_dir)  # run_id == "v2"

    asset_v1 = approve_candidate(root, "bench", "v1", approved_by="bench", now=_FIXED_TS)
    asset_v2 = approve_candidate(
        root, "bench", "v2", approved_by="bench", now=_FIXED_TS + timedelta(seconds=1),
    )

    superseded = foundry_store.load_asset(root, "bench", asset_v1.asset_id)
    assert superseded.status is AssetStatus.SUPERSEDED, (
        f"v1 asset should be superseded, got {superseded.status.value}"
    )
    current = load_current_asset(root, "bench")
    assert current.asset_id == asset_v2.asset_id, "current pointer should resolve to v2"
```

- [ ] **Step 3: Write the `min_score` gate test (TDD inversion — expected to PASS immediately)**

```python
def test_benchmark_foundry_min_score_gate(tmp_path_factory, tmp_path) -> None:
    """approve_candidate rejects a candidate whose score is below min_score and
    accepts one that meets it. allow_failing does NOT bypass this gate (it only
    bypasses the validation-ok gate), so the success path uses a met min_score.
    The candidate needs a real score.json (the run dir has none) — see
    _score_candidate."""
    case = _case_by_name(_STRIPE)
    run = _assemble_case(case, tmp_path_factory)  # skips if sources absent

    cand_dir = tmp_path / "runs" / "gate"
    shutil.copytree(Path(run.run_dir), cand_dir)
    score = _score_candidate(cand_dir)  # writes cand_dir/score/score.json

    root = tmp_path / "project"
    root.mkdir()
    register_docset(root, Docset(
        docset_id="bench", title=case.name, provider="bench", product="bench",
    ))
    import_run(root, "bench", cand_dir)  # run_id == "gate"

    with pytest.raises(FoundryApprovalError):
        approve_candidate(
            root, "bench", "gate", approved_by="bench", now=_FIXED_TS,
            min_score=score + 1,
        )

    asset = approve_candidate(
        root, "bench", "gate", approved_by="bench", now=_FIXED_TS, min_score=score,
    )
    current = load_current_asset(root, "bench")
    assert current.asset_id == asset.asset_id, "met-min_score approval should become current"
```

- [ ] **Step 4: Run to verify both PASS**

Run: `uv run pytest tests/test_benchmarks.py -v -k foundry`
Expected: PASS for the two new tests (`supersession`, `min_score_gate`) plus the existing `test_benchmark_foundry` params, SKIP where sources absent. A gate mis-behaving is a genuine `foundry` finding — investigate, do not weaken.

- [ ] **Step 5: Lint**

Run: `uv run ruff check tests/test_benchmarks.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: [benchmarks] foundry supersession + min_score approval gate"
```

---

### Task 5: `test_benchmark_preparation` — readiness invariants (Component 3a)

Per-case: `preparation-report.json` shape holds, and a validation-PASS case is never `blocked`.

**Files:**
- Modify: `tests/test_benchmarks.py` (append test)

**Interfaces:**
- Consumes: `case`, `assembled`, `PreparationReport`, `PreparationStatus`, `PreparationSeverity`.

- [ ] **Step 1: Write the test (TDD inversion — expected to PASS immediately)**

```python
def test_benchmark_preparation(case, assembled) -> None:
    """preparation-report.json parses to a PreparationReport with a valid status,
    a non-empty phases list, and only error/warning finding severities. Invariant:
    a validation-PASS case cannot have been preparation-blocked. EXPECTED_FAIL
    cases (e.g. paypal) may hold any status."""
    run_dir = Path(assembled.run_dir)
    report = PreparationReport.model_validate_json(
        (run_dir / "preparation-report.json").read_text("utf-8")
    )

    assert report.status in set(PreparationStatus), f"{case.name}: invalid preparation status"
    assert report.phases, f"{case.name}: preparation phases empty"
    for phase in report.phases:
        for finding in phase.findings:
            assert finding.severity in {PreparationSeverity.ERROR, PreparationSeverity.WARNING}, (
                f"{case.name}: unexpected preparation severity {finding.severity!r}"
            )

    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    if expect.get("current_status") == "PASS":
        assert report.status is not PreparationStatus.BLOCKED, (
            f"{case.name}: validation-PASS case must not be preparation-blocked"
        )
```

- [ ] **Step 2: Run to verify it PASSES**

Run: `uv run pytest tests/test_benchmarks.py -v -k preparation`
Expected: PASS for every case with local sources, SKIP otherwise.

- [ ] **Step 3: Lint**

Run: `uv run ruff check tests/test_benchmarks.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: [benchmarks] preparation report shape + PASS-not-blocked invariant"
```

---

### Task 6: `test_benchmark_score_verdict` — loop-verdict invariants (Component 3b)

Per-case: `classify_findings` is a lossless disjoint partition; `loop_verdict` is a valid, deterministic verdict; and `score >= min_score ⇒ CONVERGED`.

**Files:**
- Modify: `tests/test_benchmarks.py` (append test)

**Interfaces:**
- Consumes: `case`, `assembled`, `evaluate_score`, `load_score_inputs`, `ScoreProfile`, `classify_findings`, `loop_verdict`, `LoopVerdict`.

- [ ] **Step 1: Write the test (TDD inversion — expected to PASS immediately)**

```python
def test_benchmark_score_verdict(case, assembled) -> None:
    """From the real ScoreReport: (a) classify_findings is a lossless, disjoint
    partition; (b) loop_verdict returns a valid LoopVerdict, deterministic across
    a second identical call; (c) coupling invariant — score >= min_score implies
    CONVERGED (the loop must not ask for more correction once the target is met)."""
    run_dir = Path(assembled.run_dir)
    report = evaluate_score(load_score_inputs(run_dir), profile=ScoreProfile.CI)

    # (a) lossless, disjoint partition
    reducible, irreducible = classify_findings(report.findings)
    assert len(reducible) + len(irreducible) == len(report.findings), (
        f"{case.name}: classify_findings dropped or duplicated findings"
    )
    for finding in report.findings:
        assert (finding in reducible) ^ (finding in irreducible), (
            f"{case.name}: finding not in exactly one partition: {finding.code}"
        )

    # (b) valid + deterministic verdict
    kwargs = dict(
        prev_score=None, curr_score=report.score, target=report.min_score,
        round_index=1, max_rounds=3, findings=report.findings,
    )
    first = loop_verdict(**kwargs)
    again = loop_verdict(**kwargs)
    assert first.verdict in set(LoopVerdict), f"{case.name}: invalid loop verdict"
    assert first.verdict == again.verdict, f"{case.name}: loop verdict not deterministic"

    # (c) coupling invariant
    if report.score >= report.min_score:
        assert first.verdict is LoopVerdict.CONVERGED, (
            f"{case.name}: score {report.score} >= min {report.min_score} but verdict "
            f"is {first.verdict.value}, not converged"
        )
```

- [ ] **Step 2: Run to verify it PASSES**

Run: `uv run pytest tests/test_benchmarks.py -v -k score_verdict`
Expected: PASS for every case with local sources, SKIP otherwise. (`test_benchmark_score` from Phase A also matches `-k score`; both should pass.)

- [ ] **Step 3: Lint**

Run: `uv run ruff check tests/test_benchmarks.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: [benchmarks] score classify partition + loop-verdict invariants"
```

---

### Task 7: Whole-file + full-suite verification

Confirm the additions cohere and disturb nothing.

**Files:**
- None (verification only)

- [ ] **Step 1: Whole benchmark file**

Run: `uv run pytest tests/test_benchmarks.py -v`
Expected: all Phase A + Phase B tests consistent — parametrized tests PASS where local `sources/` exist and SKIP otherwise; the two `diff_detects_change`/`foundry_*` non-parametrized tests PASS (stripe sources present); `test_benchmark_harness_discovers_cases` still PASS.

- [ ] **Step 2: Full suite (no collateral damage)**

Run: `uv run pytest`
Expected: PASS — no other test perturbed. (Phase A baseline was 630 passed; expect that plus the new benchmark tests, minus any SKIPs.)

- [ ] **Step 3: Final lint**

Run: `uv run ruff check tests/test_benchmarks.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit only if Steps 1–3 surfaced fixes**

If any earlier task left an uncommitted tweak, commit it; otherwise nothing to do.

```bash
git status --porcelain tests/test_benchmarks.py
```

---

## Self-Review

**Spec coverage:**
- Component 1 (diff identity + controlled mutation) → Tasks 2 & 3.
- Component 2 (foundry supersession + `min_score` gate) → Task 4.
- Component 3 (preparation + score verdict) → Tasks 5 & 6.
- Constraints (single-file, read-only shared run dir, `_FIXED_TS`, TDD inversion, skip-on-no-sources) → Global Constraints + encoded in every task (copytree before mutate; `_FIXED_TS`/`+1s`; expected-PASS run steps).
- Testing/verification section (per-`-k`, whole-file, full-suite, ruff) → per-task Steps + Task 7.
- Out-of-scope items (new document samples, product-code changes) → not planned; explicitly excluded.

**Placeholder scan:** No TBD/TODO; every code step carries complete, runnable code proven against real data.

**Type consistency:** `_assemble_case`/`_case_by_name`/`_STRIPE`/`_mutate_stripe_extraction`/`_score_candidate` signatures match across producing and consuming tasks. API names (`build_diff_report`, `load_run_artifacts`, `DiffImpact`, `approve_candidate`, `import_run`, `load_current_asset`, `foundry_store.load_asset`, `AssetStatus`, `FoundryApprovalError`, `PreparationReport`/`PreparationStatus`/`PreparationSeverity`, `evaluate_score`/`load_score_inputs`/`ScoreProfile`/`classify_findings`/`loop_verdict`/`LoopVerdict`, `write_score_reports`) verified against the live packages. `write_score_reports(report, run_dir / "score")` matches `score.report.write_reports(report, score_dir)`. `approve_candidate(..., now=...)` keyword matches signature.
