# Continuous Correction Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repo-local quality gate and correction-loop documentation so every pipeline defect can be reproduced, fixed, and protected by durable regression evidence.

**Architecture:** Implement a dependency-free Python script at `scripts/quality_gate.py` that orchestrates existing commands and a small adversarial CLI smoke harness. Keep expensive command execution out of unit tests by factoring helper functions around injectable command runners and temporary directories. Document the human correction protocol in `docs/CORRECTION_LOOP.md` and link strict-local gate usage from the release checklist.

**Tech Stack:** Python >=3.11, stdlib `argparse` / `subprocess` / `tempfile`, current `uv` workflow, pytest, ruff.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `scripts/quality_gate.py` | New executable quality gate; runs ruff, pytest, benchmark harness, strict-local benchmark source checks, and adversarial CLI smoke scenarios. |
| `tests/test_quality_gate.py` | Unit tests for command orchestration, benchmark skip detection, required source checks, scenario result handling, and failure reporting using fake runners. |
| `docs/CORRECTION_LOOP.md` | Maintainer protocol for turning new failures into regression tests/benchmarks/follow-up records. |
| `docs/RELEASE_CHECKLIST.md` | Add the default and strict-local quality gate commands to existing release guidance. |
| `.github/workflows/ci.yml` | Optional final cleanup: run the default quality gate in CI if it is clearer than listing ruff/pytest separately. |

## Task 1: Add Testable Quality Gate Skeleton

**Files:**
- Create: `scripts/quality_gate.py`
- Create: `tests/test_quality_gate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_quality_gate.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts import quality_gate


@dataclass
class FakeResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def test_run_step_prints_pass_on_zero_exit(capsys):
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> FakeResult:
        calls.append(cmd)
        return FakeResult(stdout="ok")

    quality_gate.run_step("ruff", ["uv", "run", "ruff", "check", "."], runner=runner)

    assert calls == [["uv", "run", "ruff", "check", "."]]
    assert "[quality-gate] PASS ruff" in capsys.readouterr().out


def test_run_step_raises_with_output_excerpt_on_failure():
    def runner(cmd: list[str]) -> FakeResult:
        return FakeResult(returncode=7, stdout="stdout text", stderr="stderr text")

    with pytest.raises(quality_gate.QualityGateFailure) as exc:
        quality_gate.run_step("pytest", ["uv", "run", "pytest"], runner=runner)

    message = str(exc.value)
    assert "pytest failed with exit code 7" in message
    assert "stdout text" in message
    assert "stderr text" in message


def test_command_plan_default_mode():
    plan = quality_gate.command_plan(strict_local=False)
    assert plan == [
        ("ruff", ["uv", "run", "ruff", "check", "."]),
        ("pytest", ["uv", "run", "pytest"]),
        ("benchmarks", ["uv", "run", "pytest", "tests/test_benchmarks.py", "-q"]),
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_quality_gate.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing `quality_gate` attributes.

- [ ] **Step 3: Create package marker and minimal script**

Create `scripts/__init__.py` if imports require it in this repository layout:

```python
"""Repo-local maintenance scripts."""
```

Create `scripts/quality_gate.py`:

```python
from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass


Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class QualityGateFailure(RuntimeError):
    """Raised when a quality gate step fails."""


@dataclass(frozen=True)
class StepResult:
    name: str
    command: list[str]


def _default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=120)


def _excerpt(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def run_step(name: str, cmd: list[str], *, runner: Runner = _default_runner) -> None:
    print(f"[quality-gate] {name}: {' '.join(cmd)}")
    result = runner(cmd)
    if result.returncode != 0:
        raise QualityGateFailure(
            f"{name} failed with exit code {result.returncode}\n"
            f"stdout:\n{_excerpt(result.stdout)}\n"
            f"stderr:\n{_excerpt(result.stderr)}"
        )
    print(f"[quality-gate] PASS {name}")


def command_plan(*, strict_local: bool) -> list[tuple[str, list[str]]]:
    return [
        ("ruff", ["uv", "run", "ruff", "check", "."]),
        ("pytest", ["uv", "run", "pytest"]),
        ("benchmarks", ["uv", "run", "pytest", "tests/test_benchmarks.py", "-q"]),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-local", action="store_true")
    args = parser.parse_args(argv)
    try:
        for name, cmd in command_plan(strict_local=args.strict_local):
            run_step(name, cmd)
    except QualityGateFailure as exc:
        print(f"[quality-gate] FAILED\n{exc}", file=sys.stderr)
        return 1
    print("[quality-gate] COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_quality_gate.py -q`

Expected: PASS for the three skeleton tests.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check scripts/quality_gate.py tests/test_quality_gate.py
git add scripts/__init__.py scripts/quality_gate.py tests/test_quality_gate.py
git commit -m "test: [quality-gate] add testable gate skeleton"
```

## Task 2: Add Strict-Local Benchmark Source and Skip Detection

**Files:**
- Modify: `scripts/quality_gate.py`
- Modify: `tests/test_quality_gate.py`

- [ ] **Step 1: Write failing tests for source checks and skip parsing**

Append to `tests/test_quality_gate.py`:

```python
def test_required_benchmark_cases_lists_committed_cases():
    cases = quality_gate.required_benchmark_cases()
    assert {"newebpay-mpg", "apis-guru-baseline", "tappay-backend",
            "line-pay-online-v3", "stripe-basic-rest", "cybersource-payments",
            "github-webhooks", "paypal-webhooks-incomplete",
            "ecpay-creditcard-pdf", "adyen-payments-multimethod"} <= set(cases)


def test_missing_benchmark_sources_reports_absent_or_empty_dirs(tmp_path):
    root = tmp_path / "benchmarks"
    (root / "has-source" / "sources").mkdir(parents=True)
    (root / "has-source" / "sources" / "manual.md").write_text("ok", encoding="utf-8")
    (root / "empty-source" / "sources").mkdir(parents=True)

    missing = quality_gate.missing_benchmark_sources(
        benchmark_root=root,
        cases=["has-source", "empty-source", "absent-source"],
    )

    assert missing == ["empty-source", "absent-source"]


@pytest.mark.parametrize("stdout", [
    "10 passed, 1 skipped in 0.20s",
    "........s..",
    "SKIPPED [1] sources missing",
])
def test_has_benchmark_skips_detects_skip_signals(stdout):
    assert quality_gate.has_benchmark_skips(stdout)


def test_has_benchmark_skips_accepts_no_skip_output():
    assert not quality_gate.has_benchmark_skips("11 passed in 0.20s\n...........")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_quality_gate.py -q`

Expected: FAIL because strict-local helper functions do not exist.

- [ ] **Step 3: Implement helper functions**

Add to `scripts/quality_gate.py`:

```python
from pathlib import Path


BENCHMARK_ROOT = Path("benchmarks")
REQUIRED_BENCHMARK_CASES = (
    "newebpay-mpg",
    "apis-guru-baseline",
    "tappay-backend",
    "line-pay-online-v3",
    "stripe-basic-rest",
    "cybersource-payments",
    "github-webhooks",
    "paypal-webhooks-incomplete",
    "ecpay-creditcard-pdf",
    "adyen-payments-multimethod",
)


def required_benchmark_cases() -> tuple[str, ...]:
    return REQUIRED_BENCHMARK_CASES


def missing_benchmark_sources(
    *,
    benchmark_root: Path = BENCHMARK_ROOT,
    cases: tuple[str, ...] | list[str] = REQUIRED_BENCHMARK_CASES,
) -> list[str]:
    missing: list[str] = []
    for case in cases:
        src = benchmark_root / case / "sources"
        if not src.is_dir() or not any(path.is_file() for path in src.iterdir()):
            missing.append(case)
    return missing


def has_benchmark_skips(stdout: str) -> bool:
    lowered = stdout.lower()
    return "skipped" in lowered or "\ns" in lowered or "s" in stdout.strip(".")
```

Then update `run_step` so callers can inspect stdout:

```python
def run_step(
    name: str,
    cmd: list[str],
    *,
    runner: Runner = _default_runner,
) -> subprocess.CompletedProcess[str]:
    print(f"[quality-gate] {name}: {' '.join(cmd)}")
    result = runner(cmd)
    if result.returncode != 0:
        raise QualityGateFailure(
            f"{name} failed with exit code {result.returncode}\n"
            f"stdout:\n{_excerpt(result.stdout)}\n"
            f"stderr:\n{_excerpt(result.stderr)}"
        )
    print(f"[quality-gate] PASS {name}")
    return result
```

- [ ] **Step 4: Wire strict-local mode**

Update `main`:

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-local", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.strict_local:
            missing = missing_benchmark_sources()
            if missing:
                raise QualityGateFailure(
                    "strict-local benchmark sources missing or empty: "
                    + ", ".join(missing)
                )
        benchmark_result: subprocess.CompletedProcess[str] | None = None
        for name, cmd in command_plan(strict_local=args.strict_local):
            result = run_step(name, cmd)
            if name == "benchmarks":
                benchmark_result = result
        if args.strict_local and benchmark_result is not None:
            combined = f"{benchmark_result.stdout}\n{benchmark_result.stderr}"
            if has_benchmark_skips(combined):
                raise QualityGateFailure(
                    "strict-local benchmark run reported skips; all benchmark cases "
                    "must execute where local sources are present"
                )
    except QualityGateFailure as exc:
        print(f"[quality-gate] FAILED\n{exc}", file=sys.stderr)
        return 1
    print("[quality-gate] COMPLETE")
    return 0
```

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest tests/test_quality_gate.py -q`

Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check scripts/quality_gate.py tests/test_quality_gate.py
git add scripts/quality_gate.py tests/test_quality_gate.py
git commit -m "feat: [quality-gate] enforce strict-local benchmark coverage"
```

## Task 3: Add Adversarial CLI Smoke Harness

**Files:**
- Modify: `scripts/quality_gate.py`
- Modify: `tests/test_quality_gate.py`

- [ ] **Step 1: Write failing tests for scenario classification**

Append to `tests/test_quality_gate.py`:

```python
def test_scenario_result_requires_expected_exit_and_signal():
    result = quality_gate.ScenarioResult(
        scenario_id="ADV-001",
        exit_code=2,
        expected_exit=2,
        signal="inventory.json 不是合法 JSON",
        expected_signal="inventory.json 不是合法 JSON",
        cleanup_ok=True,
    )
    assert result.ok


def test_scenario_result_fails_on_exit_mismatch():
    result = quality_gate.ScenarioResult(
        scenario_id="ADV-001",
        exit_code=1,
        expected_exit=2,
        signal="inventory.json 不是合法 JSON",
        expected_signal="inventory.json 不是合法 JSON",
        cleanup_ok=True,
    )
    assert not result.ok


def test_scenario_result_fails_on_missing_signal():
    result = quality_gate.ScenarioResult(
        scenario_id="ADV-001",
        exit_code=2,
        expected_exit=2,
        signal="different",
        expected_signal="inventory.json 不是合法 JSON",
        cleanup_ok=True,
    )
    assert not result.ok
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_quality_gate.py -q`

Expected: FAIL because `ScenarioResult` does not exist.

- [ ] **Step 3: Add scenario result model and runner shell**

Add to `scripts/quality_gate.py`:

```python
import json
import os
import tempfile


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    exit_code: int
    expected_exit: int
    signal: str
    expected_signal: str
    cleanup_ok: bool

    @property
    def ok(self) -> bool:
        return (
            self.exit_code == self.expected_exit
            and self.expected_signal in self.signal
            and self.cleanup_ok
        )
```

Then add helper functions:

```python
BASE_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "manual.md"}],
    "security_schemes": [],
    "schemas": [],
    "errors": [],
    "operational": [{"topic": "Authentication", "details": "public API", "source": "manual.md"}],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "manual.md"}],
    "missing": [],
}

BASE_ENDPOINT = {
    "method": "GET",
    "path": "/ping",
    "parameters": [],
    "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [],
    "missing": [],
    "source": "manual.md",
}


def _write_valid_fixture(root: Path) -> tuple[Path, Path, Path]:
    sources = root / "sources"
    extraction = root / "extraction"
    endpoints = extraction / "endpoints"
    out = root / "out"
    sources.mkdir(parents=True)
    endpoints.mkdir(parents=True)
    (sources / "manual.md").write_text("# Demo API\nGET /ping\npublic API", encoding="utf-8")
    (extraction / "inventory.json").write_text(
        json.dumps(BASE_INVENTORY, ensure_ascii=False), encoding="utf-8")
    (endpoints / "ep0.json").write_text(
        json.dumps(BASE_ENDPOINT, ensure_ascii=False), encoding="utf-8")
    return sources, extraction, out
```

- [ ] **Step 4: Implement six adversarial scenarios**

Add this function to `scripts/quality_gate.py`:

```python
def run_adversarial_cli_smoke(*, runner: Runner = _default_runner) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    with tempfile.TemporaryDirectory(prefix="loop-apidoc-adv-") as td:
        root = Path(td)

        sources, extraction, out = _write_valid_fixture(root / "normal")
        cmd = ["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
               "--extraction", str(extraction), "--output", str(out), "--json"]
        res = runner(cmd)
        signal = res.stdout
        try:
            payload = json.loads(res.stdout)
            signal = f"ok={payload['ok']} status={payload['status']}"
        except json.JSONDecodeError:
            pass
        results.append(ScenarioResult("ADV-001", res.returncode, 0, signal, "ok=True", out.exists()))

        sources, extraction, out = _write_valid_fixture(root / "bad-json")
        (extraction / "inventory.json").write_text("{ not json", encoding="utf-8")
        res = runner(["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
                      "--extraction", str(extraction), "--output", str(out), "--json"])
        results.append(ScenarioResult(
            "ADV-002", res.returncode, 2, res.stderr,
            "inventory.json 不是合法 JSON", not out.exists()))

        sources, extraction, out = _write_valid_fixture(root / "localized-keys")
        inventory = dict(BASE_INVENTORY)
        inventory["schemas"] = [{"name": "Bad", "fields": [{"名稱": "id", "型別": "string"}],
                                 "source": "manual.md"}]
        (extraction / "inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
        res = runner(["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
                      "--extraction", str(extraction), "--output", str(out), "--json"])
        results.append(ScenarioResult(
            "ADV-003", res.returncode, 2, res.stderr,
            "schemas[0].fields[0]", not out.exists()))

        sources, extraction, out = _write_valid_fixture(root / "bad-integration")
        (extraction / "integration.json").write_text("[]", encoding="utf-8")
        res = runner(["uv", "run", "loop-apidoc", "assemble", "--sources", str(sources),
                      "--extraction", str(extraction), "--output", str(out), "--json"])
        results.append(ScenarioResult(
            "ADV-004", res.returncode, 2, res.stderr,
            "integration.json 必須是 JSON 物件", not out.exists()))

        run_dir = root / "incomplete-run"
        run_dir.mkdir()
        res = runner(["uv", "run", "loop-apidoc", "validate", "--output", str(run_dir)])
        report_path = run_dir / "validation" / "report.json"
        signal = res.stdout
        if report_path.exists():
            signal += report_path.read_text(encoding="utf-8")
        results.append(ScenarioResult(
            "ADV-005", res.returncode, 1, signal,
            "OUTPUT_MISMATCH", report_path.exists()))

        srcroot = root / "symlink-src"
        srcroot.mkdir()
        (srcroot / "good.md").write_text("# ok", encoding="utf-8")
        secret = root / "outside-secret.md"
        secret.write_text("TOP SECRET DO NOT READ", encoding="utf-8")
        os.symlink(secret, srcroot / "leak.md")
        res = runner(["uv", "run", "loop-apidoc", "manifest", "--sources", str(srcroot)])
        signal = res.stdout
        results.append(ScenarioResult(
            "ADV-006", res.returncode, 0, signal,
            '"status": "unreadable"', True))

    return results
```

- [ ] **Step 5: Wire the adversarial smoke step into `main`**

Add after the regular command plan in `main`:

```python
print("[quality-gate] adversarial CLI smoke")
scenario_results = run_adversarial_cli_smoke()
failed = [result for result in scenario_results if not result.ok]
if failed:
    lines = [
        f"{result.scenario_id}: exit {result.exit_code}/{result.expected_exit}; "
        f"signal={_excerpt(result.signal, 300)!r}; cleanup_ok={result.cleanup_ok}"
        for result in failed
    ]
    raise QualityGateFailure("adversarial CLI smoke failed:\n" + "\n".join(lines))
print(f"[quality-gate] PASS adversarial CLI smoke ({len(scenario_results)} scenarios)")
```

- [ ] **Step 6: Run focused tests and the script**

Run:

```bash
uv run pytest tests/test_quality_gate.py -q
uv run python scripts/quality_gate.py
```

Expected:
- Tests PASS.
- Script prints `PASS adversarial CLI smoke (6 scenarios)` and `COMPLETE`.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check scripts/quality_gate.py tests/test_quality_gate.py
git add scripts/quality_gate.py tests/test_quality_gate.py
git commit -m "feat: [quality-gate] add adversarial CLI smoke checks"
```

## Task 4: Document the Correction Loop

**Files:**
- Create: `docs/CORRECTION_LOOP.md`
- Modify: `docs/RELEASE_CHECKLIST.md`

- [ ] **Step 1: Create correction loop documentation**

Create `docs/CORRECTION_LOOP.md`:

```markdown
# Continuous Correction Loop

Use this loop for every non-trivial `loop-apidoc` defect, benchmark drift, or
pipeline quality issue.

## Rule

No correction is complete until the failure is captured as durable evidence:
a regression test, a benchmark fixture/expectation update, or a documented
follow-up explaining why executable coverage is not practical.

## Loop

1. Reproduce the failure with the smallest command that shows the wrong behavior.
2. Classify the failure boundary:
   - extraction contract or skill prompt;
   - manifest/preprocess;
   - plan builder;
   - generator;
   - validator;
   - benchmark expectation;
   - release/operator documentation.
3. Add the regression first:
   - unit/integration test for deterministic code;
   - benchmark extraction/expected update for document-shape regressions;
   - adversarial quality-gate scenario for CLI boundary behavior;
   - `docs/PIPELINE_FOLLOWUPS.md` entry for larger work that should not ship in
     the current patch.
4. Verify the regression fails for the intended reason.
5. Implement the smallest fix at the responsible boundary.
6. Run the focused test, then:
   - `uv run python scripts/quality_gate.py`
   - `uv run python scripts/quality_gate.py --strict-local` when benchmark
     sources are available or benchmark fixtures changed.
7. Update benchmark `notes.md`, expectation files, or follow-up docs with the
   decision and residual risks.

## Quality Gate Commands

Use the default gate for ordinary local validation and CI-safe checks:

```bash
uv run python scripts/quality_gate.py
```

Use strict-local mode before releases and after benchmark fixture changes on a
machine with all `benchmarks/<case>/sources/` directories present:

```bash
uv run python scripts/quality_gate.py --strict-local
```

Strict-local mode fails if benchmark cases skip because local sources are absent.

## Failure Record Template

Add this shape to the relevant benchmark `notes.md`, commit message body, or
`docs/PIPELINE_FOLLOWUPS.md` entry:

```markdown
## Finding

- Symptom:
- Reproduction command:
- Root cause:
- Fix boundary:
- Regression evidence:
- Quality gate:
- Residual risk:
```
```

- [ ] **Step 2: Update release checklist**

In `docs/RELEASE_CHECKLIST.md`, under `## Automated in CI`, add:

```markdown
- [ ] `uv run python scripts/quality_gate.py` passes in CI-safe mode.
```

Under `## Requires local benchmark sources (local sources)`, add:

```markdown
- [ ] `uv run python scripts/quality_gate.py --strict-local` passes — no
  benchmark source directory is missing and no benchmark case is skipped.
```

Under `## Invariant re-check`, add:

```markdown
- [ ] Any defect fixed in this release has a regression test, benchmark fixture,
  quality-gate scenario, or documented follow-up in `docs/PIPELINE_FOLLOWUPS.md`.
```

- [ ] **Step 3: Review docs for placeholders and contradictions**

Run:

```bash
rg -n "T[B]D|TO[D]O|implement[ ]later|fill[ ]in" docs/CORRECTION_LOOP.md docs/RELEASE_CHECKLIST.md
```

Expected: no output.

- [ ] **Step 4: Commit docs**

```bash
git add docs/CORRECTION_LOOP.md docs/RELEASE_CHECKLIST.md
git commit -m "docs: [quality-gate] document correction loop"
```

## Task 5: Optional CI Consolidation

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Decide whether to consolidate CI**

If `scripts/quality_gate.py` is stable and fast enough, replace separate `Lint`
and `Test` steps with:

```yaml
      - name: Quality gate
        run: uv run python scripts/quality_gate.py
```

Keep the existing comments about benchmark local sources by moving them next to
the new quality gate step.

- [ ] **Step 2: If changed, run YAML-adjacent verification**

Run:

```bash
uv run python scripts/quality_gate.py
```

Expected: PASS.

- [ ] **Step 3: Commit CI change if applied**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: [quality-gate] run repo quality gate"
```

If the separate CI steps are clearer, skip this task and leave `.github/workflows/ci.yml`
unchanged.

## Final Verification

After all implemented tasks:

```bash
uv run ruff check .
uv run pytest
uv run python scripts/quality_gate.py
uv run python scripts/quality_gate.py --strict-local
git status --short
```

Expected:
- ruff passes.
- pytest passes.
- default quality gate passes.
- strict-local quality gate passes on a machine with all benchmark sources.
- worktree contains only intentional committed changes.

Do not claim the correction loop is complete unless the final verification output
has been read and matches the expected signals.
