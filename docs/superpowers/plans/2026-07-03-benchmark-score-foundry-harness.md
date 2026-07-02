# Benchmark score + foundry harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add benchmark-level regression coverage for the `score` and `foundry` subsystems by driving them against the real committed benchmark run dirs inside `tests/test_benchmarks.py`.

**Architecture:** Convert the existing `case` parametrize into a fixture and add a memoized `assembled` fixture so every case is assembled exactly once per session; three independent tests (`test_benchmark_case`, `test_benchmark_score`, `test_benchmark_foundry`) then share that read-only run dir. score assertions are structural invariants only; foundry drives the full register→import→approve→resolve_current chain against a throwaway `tmp_path` project root.

**Tech Stack:** Python 3.11+, pytest, `uv`, existing `loop_apidoc.score` / `loop_apidoc.foundry` public APIs.

## Global Constraints

- Python `>=3.11`, managed with `uv` (no `pip`). Run tests via `uv run pytest`.
- **Only** `tests/test_benchmarks.py` is modified. No product-code changes, no changes to `benchmarks/**` data or `expected/*.json`.
- Prefer immutable / pure patterns; the run dir is treated read-only by all consumers.
- TDD inversion: the subsystems under test already exist, so each new benchmark test is **expected to PASS** on first run against real data. A failure is a genuine subsystem finding — stop and investigate with superpowers:systematic-debugging rather than editing the test to go green.
- `_FIXED_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)` is the single fixed timestamp used everywhere determinism matters.

---

### Task 1: Shared `assembled` fixture (refactor existing harness)

Convert `case` from a `@pytest.mark.parametrize` argument into a parametrized fixture, add a memoized `assembled` fixture, and refactor `test_benchmark_case` to consume it. The existing assertions must stay byte-for-byte identical — this task changes only *where* assemble runs, not *what* is asserted.

**Files:**
- Modify: `tests/test_benchmarks.py`

**Interfaces:**
- Consumes: `run_assemble_pipeline(sources_root, extraction_dir, output_root, run_id, generated_at) -> RunResult` (already imported). `RunResult` exposes `.run_dir: str` and `.report` (a `ValidationReport` with `.ok: bool`, `.issues`, `.errors()`).
- Produces (for Tasks 2–3):
  - fixture `case` → `Path` (a benchmark case dir), parametrized over `_cases()` with `ids=[c.name ...]`.
  - fixture `assembled` → `RunResult`; skips the test when the case's `sources/` is absent; memoized in module-level `_ASSEMBLED: dict[str, RunResult]` keyed by `case.name`.

- [ ] **Step 1: Replace the `case` parametrize and add the two fixtures**

In `tests/test_benchmarks.py`, delete the `@pytest.mark.parametrize("case", ...)` decorator on `test_benchmark_case` and change its signature. Immediately **above** `test_benchmark_case`, add the `case` and `assembled` fixtures. Insert this block after `_issue_classes(...)` and before the (now-un-decorated) `test_benchmark_case`:

```python
@pytest.fixture(params=_cases(), ids=[c.name for c in _cases()])
def case(request) -> Path:
    return request.param


# Assemble each case at most once per session; the produced run dir is treated
# read-only by every consumer (score reads it; foundry copytrees FROM it), so a
# single shared run dir is safe. tmp_path_factory is session-scoped, so the dir
# survives for the whole session.
_ASSEMBLED: dict[str, object] = {}


@pytest.fixture
def assembled(case, tmp_path_factory):
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
```

- [ ] **Step 2: Refactor `test_benchmark_case` to consume the fixture**

Change the signature to `def test_benchmark_case(case, assembled):` (drop `tmp_path`). Remove the inline skip guard and the inline `run_assemble_pipeline(...)` call; bind the result from the fixture. Replace the top of the function body — from the `if not _has_sources(...)` line through the `result = run_assemble_pipeline(...)` block and `report = result.report` — with:

```python
def test_benchmark_case(case, assembled) -> None:
    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    minimum = json.loads((case / "expected" / "minimum.json").read_text("utf-8"))
    must = minimum.get("must_have", {})

    result = assembled
    report = result.report
```

Everything from `# --- 1. PASS/FAIL matches expectation ---` downward stays **exactly as-is** (it already refers to `result` and `report`).

- [ ] **Step 3: Run the full benchmark file to confirm no regression**

Run: `uv run pytest tests/test_benchmarks.py -v`
Expected: the same `test_benchmark_case[<name>]` params as before — PASS where `sources/` exists locally, SKIP where absent — plus `test_benchmark_harness_discovers_cases` PASS. No errors from the fixture wiring.

- [ ] **Step 4: Lint**

Run: `uv run ruff check tests/test_benchmarks.py`
Expected: no findings.

- [ ] **Step 5: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: [benchmarks] extract shared assembled fixture (assemble once per case)"
```

---

### Task 2: `test_benchmark_score` — structural invariants

Add a benchmark test that grades each case's run dir under both score profiles and asserts the durable invariants: score in band, deterministic, profile echoed, and — the CLAUDE.md rule — score never alters validation pass/fail.

**Files:**
- Modify: `tests/test_benchmarks.py`

**Interfaces:**
- Consumes: fixtures `case` and `assembled` from Task 1; `load_score_inputs(run_dir: Path) -> ScoreInputs`, `evaluate_score(inputs, *, profile: ScoreProfile) -> ScoreReport` (`.score: int` 0–100, `.profile: ScoreProfile`), `ScoreProfile.CI` / `ScoreProfile.REVIEW`.
- Produces: nothing consumed downstream.

- [ ] **Step 1: Add the score imports**

Add to the import block near the top of `tests/test_benchmarks.py` (after the existing `from loop_apidoc.agentcli.assemble import run_assemble_pipeline` line):

```python
from loop_apidoc.score import ScoreProfile, evaluate_score, load_score_inputs
```

- [ ] **Step 2: Write the score test**

Add after `test_benchmark_case`:

```python
def test_benchmark_score(case, assembled) -> None:
    """score grades every run dir 0–100, deterministically, without ever changing
    validation pass/fail (the CLAUDE.md invariant). No per-case score floor — a
    validation-PASS case can legitimately score low on completeness warnings."""
    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    inputs = load_score_inputs(Path(assembled.run_dir))

    for profile in (ScoreProfile.CI, ScoreProfile.REVIEW):
        report = evaluate_score(inputs, profile=profile)
        assert 0 <= report.score <= 100, f"{case.name}: score {report.score} out of band"
        assert report.profile is profile, f"{case.name}: profile not echoed"
        again = evaluate_score(inputs, profile=profile)
        assert again.score == report.score, f"{case.name}: score not deterministic"

    # Core invariant: scoring does not change the validation verdict.
    want_pass = expect.get("current_status") == "PASS"
    assert assembled.report.ok is want_pass, f"{case.name}: score run perturbed validation ok"
```

- [ ] **Step 3: Run the score test (expect PASS on real data)**

Run: `uv run pytest tests/test_benchmarks.py -v -k score`
Expected: `test_benchmark_score[<name>]` PASS where `sources/` exists, SKIP otherwise. If any param FAILs, that is a genuine `score` finding on real data — stop and investigate with superpowers:systematic-debugging; do not weaken the test.

- [ ] **Step 4: Lint**

Run: `uv run ruff check tests/test_benchmarks.py`
Expected: no findings.

- [ ] **Step 5: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: [benchmarks] assert score structural invariants per case"
```

---

### Task 3: `test_benchmark_foundry` — full governance chain

Add a benchmark test that drives the complete foundry chain (register → import → approve → resolve current) against a throwaway `tmp_path` project root, branching only on `allow_failing` for the one EXPECTED_FAIL case.

**Files:**
- Modify: `tests/test_benchmarks.py`

**Interfaces:**
- Consumes: fixtures `case`, `assembled` (Task 1), plus pytest's `tmp_path`. Foundry APIs:
  - `register_docset(project_root: Path, docset: Docset, *, exist_ok=False) -> Docset` where `Docset` requires `docset_id`, `title`, `provider`, `product`.
  - `import_run(project_root, docset_id, run_dir: Path, *, overwrite=False) -> ImportResult` with `.run_id: str`.
  - `approve_candidate(project_root, docset_id, run_id, *, approved_by: str, now: datetime, min_score=None, allow_failing=False, ...) -> Asset` with `.asset_id: str`.
  - `load_current_asset(project_root, docset_id) -> Asset`; `resolve_current_artifact(project_root, docset_id, artifact: str) -> Path` where `artifact` is an `AssetArtifacts` field name (use `"openapi"`).
- Produces: nothing consumed downstream.

- [ ] **Step 1: Add the foundry imports**

Add to the import block (after the score import from Task 2):

```python
from loop_apidoc.foundry.approve import approve_candidate
from loop_apidoc.foundry.importer import import_run
from loop_apidoc.foundry.models import Docset
from loop_apidoc.foundry.query import load_current_asset, resolve_current_artifact
from loop_apidoc.foundry.register import register_docset
```

- [ ] **Step 2: Write the foundry test**

Add after `test_benchmark_score`:

```python
def test_benchmark_foundry(case, assembled, tmp_path) -> None:
    """Full governance chain against a throwaway .foundry/: register → import →
    approve → resolve current. import_run needs only a complete run dir (not a
    PASS), so the EXPECTED_FAIL case imports fine and only approval needs the
    allow_failing override."""
    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    want_pass = expect.get("current_status") == "PASS"
    root = tmp_path  # fresh .foundry/, zero pollution

    register_docset(root, Docset(
        docset_id="bench", title=case.name, provider="bench", product="bench",
    ))
    imported = import_run(root, "bench", Path(assembled.run_dir))
    asset = approve_candidate(
        root, "bench", imported.run_id,
        approved_by="bench", now=_FIXED_TS,
        allow_failing=not want_pass,  # EXPECTED_FAIL cases (e.g. paypal) need this
    )

    current = load_current_asset(root, "bench")
    assert current.asset_id == asset.asset_id, f"{case.name}: current pointer != approved asset"
    openapi = resolve_current_artifact(root, "bench", "openapi")
    assert openapi.is_file(), f"{case.name}: current asset openapi artifact missing on disk"
```

- [ ] **Step 3: Run the foundry test (expect PASS on real data)**

Run: `uv run pytest tests/test_benchmarks.py -v -k foundry`
Expected: `test_benchmark_foundry[<name>]` PASS where `sources/` exists, SKIP otherwise. A FAIL is a genuine `foundry` finding — investigate, don't weaken.

- [ ] **Step 4: Run the whole benchmark file + lint**

Run: `uv run pytest tests/test_benchmarks.py -v && uv run ruff check tests/test_benchmarks.py`
Expected: `test_benchmark_case`, `test_benchmark_score`, `test_benchmark_foundry` params all PASS/SKIP consistently; `test_benchmark_harness_discovers_cases` PASS; no lint findings.

- [ ] **Step 5: Full suite guard**

Run: `uv run pytest`
Expected: full suite green — the fixture refactor must not disturb any other test.

- [ ] **Step 6: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: [benchmarks] drive full foundry governance chain per case"
```

---

## Self-Review

**Spec coverage:**
- Component 1 (shared `assembled` fixture + `case` fixture + refactor `test_benchmark_case`) → Task 1. ✅
- Component 2 (`test_benchmark_score`, structural invariants, both profiles, no `expected/` change) → Task 2. ✅
- Component 3 (`test_benchmark_foundry`, full chain, `allow_failing=not want_pass`, artifact key `"openapi"`, throwaway root, no `min_score`) → Task 3. ✅
- Imports-to-add block → split across Task 2 Step 1 and Task 3 Step 1. ✅
- Discovery guard stays as-is → untouched by all tasks (verified green in Task 1 Step 3). ✅
- Error handling (absent sources → skip; malformed extraction → error; EXPECTED_FAIL → allow_failing) → fixture skip (Task 1), TDD-inversion note (Global Constraints), allow_failing branch (Task 3). ✅
- Verification commands (`pytest tests/test_benchmarks.py`, full `pytest`, `ruff`) → Tasks 1/2/3 steps. ✅

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step shows full code. ✅

**Type consistency:** `case: Path`, `assembled: RunResult` (`.run_dir: str`, `.report.ok: bool`) used identically in Tasks 1–3. `ScoreProfile`/`evaluate_score`/`load_score_inputs` signatures match spec. `Docset(docset_id/title/provider/product)`, `import_run(...).run_id`, `approve_candidate(..., approved_by, now, allow_failing).asset_id`, `resolve_current_artifact(..., "openapi")` match verified foundry signatures. ✅
