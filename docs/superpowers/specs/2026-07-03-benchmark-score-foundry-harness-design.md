# Benchmark harness — wire `score` + `foundry` into the regression suite

**Date:** 2026-07-03
**Scope:** Phase A of the benchmark-expansion effort. Adds end-to-end benchmark
coverage for two subsystems that currently have **zero** benchmark-level
assertions: `score` (documentation-quality grading) and `foundry` (project-local
asset governance). Unit tests for both already exist (`tests/score/`,
`tests/foundry/`, `tests/test_cli_score.py`, `tests/test_cli_foundry.py`); this
spec adds *integration* coverage that drives them against **real committed
benchmark run dirs**, so a pipeline change that silently breaks score/foundry on
realistic inputs is caught as a regression.

## Motivation

The benchmark regression harness (`tests/test_benchmarks.py`,
`docs/BENCHMARK_VALIDATION_PLAN.md`) currently exercises only the
`assemble → validate` tail (plus integration-contract / provenance / examples).
The 10 committed cases already cover a broad source-format / auth / structure
matrix, so **adding more extraction cases has low marginal value** — it re-proves
the same path. The higher-value gap is **vertical**: three newer subsystems
(`score`, `diff`, `foundry`) have no benchmark coverage. This spec covers
`score` + `foundry` (Phase A); `diff` (needs a two-version run-dir pair) is a
separate later phase.

## Non-goals

- **No product-code changes.** Only `tests/test_benchmarks.py` is touched.
- **No changes to benchmark data or `expected/*.json`.** score uses structural
  invariants only (no per-case score floors); foundry uses a throwaway
  `tmp_path` project root.
- **No `diff` coverage** (Phase B) and **no new extraction cases** (Phase C).
- **No `min_score` gating in foundry** — score and foundry stay decoupled.

## Design

### Component 1 — shared `assembled` fixture (the one refactor)

Today `test_benchmark_case` is parametrized via
`@pytest.mark.parametrize("case", _cases(), ids=...)` and runs
`run_assemble_pipeline(...)` inline. To let three independent tests share **one**
assemble per case (instead of re-running it 3×), convert `case` into a
parametrized fixture and memoize the assemble result:

```python
@pytest.fixture(params=_cases(), ids=[c.name for c in _cases()])
def case(request) -> Path:
    return request.param

_ASSEMBLED: dict[str, "RunResult"] = {}   # memoize: assemble each case once per session

@pytest.fixture
def assembled(case, tmp_path_factory):
    if not _has_sources(case):
        pytest.skip(f"{case.name}: sources/ not present (operator-provided, gitignored)")
    if case.name not in _ASSEMBLED:
        out = tmp_path_factory.mktemp(f"bench-{case.name}")   # session-lived → run_dir persists
        _ASSEMBLED[case.name] = run_assemble_pipeline(
            sources_root=case / "sources",
            extraction_dir=case / "extraction",
            output_root=out,
            run_id="bench",
            generated_at=_FIXED_TS,
        )
    return _ASSEMBLED[case.name]
```

- `run_assemble_pipeline` returns a `RunResult` with `.run_dir: str` and
  `.report` (a `ValidationReport`).
- `tmp_path_factory` is session-scoped, so the produced `run_dir` survives for
  the whole test session — safe to share.
- The `run_dir` is treated **read-only** by all consumers: `score` only reads it;
  `foundry.import_run` does `shutil.copytree` *from* it. So sharing one `run_dir`
  across score + foundry tests is safe.
- The `_has_sources` skip moves into the fixture, so every consuming test skips
  uniformly when a case's gitignored `sources/` is absent.

`test_benchmark_case` is refactored to take `(case, assembled)` and drop its
inline `run_assemble_pipeline` call and its own skip guard; **all of its existing
assertions stay byte-for-byte identical** (it reads `result.report` /
`result.run_dir` from `assembled` instead of a local variable).

### Component 2 — `test_benchmark_score` (structural invariants)

```python
def test_benchmark_score(case, assembled):
    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    inputs = load_score_inputs(Path(assembled.run_dir))
    for profile in (ScoreProfile.CI, ScoreProfile.REVIEW):
        rep = evaluate_score(inputs, profile=profile)
        assert 0 <= rep.score <= 100                 # score in band
        assert rep.profile is profile                # profile echoed
        assert evaluate_score(inputs, profile=profile).score == rep.score   # deterministic
    # Core invariant: score NEVER changes validation pass/fail.
    assert assembled.report.ok is (expect.get("current_status") == "PASS")
```

Rationale for structural-only (no per-case floor): a validation-PASS case can
legitimately score low due to completeness *warnings*, so a hard per-case floor
would be brittle. The durable signals are: score stays in `0..100`, is
deterministic for a fixed input, echoes its profile, and — the CLAUDE.md
invariant — does not alter validation's pass/fail verdict.

### Component 3 — `test_benchmark_foundry` (full governance chain)

```python
def test_benchmark_foundry(case, assembled, tmp_path):
    expect = json.loads((case / "expected" / "validation.expect.json").read_text("utf-8"))
    want_pass = expect.get("current_status") == "PASS"
    root = tmp_path                                  # fresh .foundry/, zero pollution

    register_docset(root, Docset(
        docset_id="bench", title=case.name, provider="bench", product="bench",
    ))
    imp = import_run(root, "bench", Path(assembled.run_dir))
    asset = approve_candidate(
        root, "bench", imp.run_id,
        approved_by="bench", now=_FIXED_TS,
        allow_failing=not want_pass,                 # paypal (EXPECTED_FAIL) needs this
    )
    current = load_current_asset(root, "bench")
    assert current.asset_id == asset.asset_id        # candidate → asset → current pointer chain
    art = resolve_current_artifact(root, "bench", "openapi")   # key is "openapi", not "openapi.yaml"
    assert art.is_file()                             # resolved artifact exists on disk
```

- Runs the full chain for **every** case; the only per-case branch is
  `allow_failing = not want_pass`, so the one EXPECTED_FAIL case (`paypal`)
  exercises the `allow_failing` path while the 9 PASS cases approve normally.
- `import_run` requires only a *complete* run dir (not validation-PASS), so the
  EXPECTED_FAIL case imports fine; only `approve_candidate` needs the override.
- `resolve_current_artifact`'s artifact argument is an `AssetArtifacts` field
  name — use `"openapi"` (fields: `openapi`, `provenance`, `validation`,
  `integration_contract`, `review`, `score`, `handoff`), **not** a filename.
- No `min_score` passed → foundry approval stays decoupled from `score`.

### Imports to add

`from pathlib import Path` is already imported. New:

```python
from loop_apidoc.score import ScoreProfile, evaluate_score, load_score_inputs
from loop_apidoc.foundry.models import Docset
from loop_apidoc.foundry.register import register_docset
from loop_apidoc.foundry.importer import import_run
from loop_apidoc.foundry.approve import approve_candidate
from loop_apidoc.foundry.query import load_current_asset, resolve_current_artifact
```

### Discovery guard

`test_benchmark_harness_discovers_cases` stays as-is (it calls `_cases()`
directly, independent of the fixture refactor).

## Error handling / edge cases

- **Absent `sources/`** → the `assembled` fixture skips; all three tests skip
  uniformly (same behavior as today, just centralized).
- **Malformed committed extraction** → `run_assemble_pipeline` raises
  `AssembleInputError` inside the fixture → the depending tests **error** (not
  fail), which is the correct signal that committed JSON must stay assemble-able.
- **EXPECTED_FAIL case** → handled by the `allow_failing=not want_pass` branch.

## Testing / verification

- `uv run pytest tests/test_benchmarks.py -v` — expect the existing
  `test_benchmark_case[...]` params to stay green, plus new
  `test_benchmark_score[...]` and `test_benchmark_foundry[...]` params (and skips
  where `sources/` is absent, e.g. in CI).
- `uv run pytest` — full suite stays green (fixture refactor must not disturb
  other tests; `test_benchmarks.py` is self-contained).
- `uv run ruff check tests/test_benchmarks.py`.

## Follow-ups (out of scope)

- **Phase B:** `diff` benchmark coverage — needs a two-version run-dir pair
  (e.g. a prior-version extraction of an existing case).
- **Phase C:** new auth/structure cases (OAuth2 flows + scopes, query-param API
  key) and a multi-source-merge case.
