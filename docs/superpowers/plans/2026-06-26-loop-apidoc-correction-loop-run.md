# Loop API Doc — Correction Loop + Full `run` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the full `loop-apidoc run` command — manifest → extraction → plan → generate → validate → a max-3-round correction loop — into one run directory, with the spec's stop/exit-code behavior fully testable.

**Architecture:** A new pure `loop_apidoc/run/` package holds three layers: run-id minting (`runid.py`), issue classification (`correction.py` — maps each `IssueCode` to AUTO_FIX / RE_QUERY / UNFIXABLE and runs the loop over injected `regenerate`/`requery` closures so the loop logic is testable without NotebookLM), and orchestration (`pipeline.py` — wires the real seams and owns all run-dir file I/O). The CLI `run` command is a thin Typer wrapper that mints a UTC run-id, does an auth preflight, calls `run_pipeline`, and maps the outcome to an exit code. One supporting hardening task makes `scan_sources` survive unreadable files on real source trees.

**Tech Stack:** Python 3.12, Typer, Pydantic v2, pytest. Reuses existing seams: `run_extraction`, `build_normalization_plan`, `generate_outputs`, `validate_outputs`, `write_reports`, `NotebookLMAdapter`, `build_manifest`.

## Global Constraints

- Python ≥ 3.12; Pydantic v2; Typer for CLI; no new runtime dependencies.
- `from __future__ import annotations` at the top of every new module.
- Immutability: build new model instances; never mutate inputs in place.
- Defaults (spec §5): output language `zh-TW`, OpenAPI 3.1, **max correction rounds = 3**, no-speculation enabled.
- Rounds are content-correction attempts only; NotebookLM technical retries (`run_with_retries`) are counted separately and never consume a correction round (spec §11).
- No speculation: the correction loop may only fix conversion/format issues or re-query NotebookLM; it must never invent source-missing or conflicting content (spec §10).
- Secrets: never write Google cookies, browser state, or credentials into the run dir or logs (spec §11).
- All skill calls go through the existing adapter (which uses `scripts/run.py`); this plan adds no direct skill-script calls.
- New files target 200–400 lines, 800 max; one responsibility each.
- Conventional commits: `<type>: [run] <subject>`.

---

## File Structure

- `loop_apidoc/run/__init__.py` — package docstring + public exports (`run_pipeline`, `RunResult`, `RunStatus`, `make_run_id`).
- `loop_apidoc/run/models.py` — `RunStatus` enum, `CorrectionCategory` enum, `CorrectionOutcome`, `RunResult`.
- `loop_apidoc/run/runid.py` — `make_run_id(now) -> str` (pure, UTC-timestamp run id).
- `loop_apidoc/run/correction.py` — `classify_issue`, `annotate_fixability`, `run_correction_loop`.
- `loop_apidoc/run/pipeline.py` — `run_pipeline(...)` orchestration + all run-dir persistence.
- `loop_apidoc/cli.py` — add the `run` command (modify).
- `loop_apidoc/manifest/scanner.py` — harden `scan_sources` against OSError (modify).
- `loop_apidoc/manifest/models.py` — add `ProcessingStatus.UNREADABLE` + `Manifest.unreadable()` (modify).
- `tests/run/` — unit tests for runid, classification, correction loop.
- `tests/integration/test_run_pipeline.py` — §12.2 scenarios (3-round success, early stop, final failure) via fake adapter.
- `tests/manifest/test_scanner_hardening.py` — unreadable-file resilience.
- `tests/smoke/test_real_skill_smoke.py` — env-gated real-skill smoke marker (carry-forward).

---

## Task 1: Harden `scan_sources` against unreadable files

**Files:**
- Modify: `loop_apidoc/manifest/models.py`
- Modify: `loop_apidoc/manifest/scanner.py`
- Test: `tests/manifest/test_scanner_hardening.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ProcessingStatus.UNREADABLE` enum member; `Manifest.unreadable() -> list[LocalSource]`. Unreadable sources are recorded with `sha256=""`, `size_bytes=0`, `supported=False`, `status=ProcessingStatus.UNREADABLE`, never silently dropped (spec §11 "不支援檔案：加入 manifest issue，不靜默略過").

- [ ] **Step 1: Write the failing test**

```python
# tests/manifest/test_scanner_hardening.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.manifest.models import ProcessingStatus
from loop_apidoc.manifest.scanner import scan_sources


def _now() -> datetime:
    return datetime(2026, 6, 26, tzinfo=timezone.utc)


def test_broken_symlink_recorded_not_fatal(tmp_path: Path) -> None:
    (tmp_path / "good.md").write_text("# ok", encoding="utf-8")
    (tmp_path / "dangling.md").symlink_to(tmp_path / "missing-target.md")

    sources = scan_sources(tmp_path, scanned_at=_now())

    by_path = {s.relative_path: s for s in sources}
    assert by_path["good.md"].status is ProcessingStatus.PENDING
    assert by_path["dangling.md"].status is ProcessingStatus.UNREADABLE
    assert by_path["dangling.md"].sha256 == ""
    assert by_path["dangling.md"].supported is False


def test_unreadable_file_recorded(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "secret.md"
    target.write_text("data", encoding="utf-8")

    import loop_apidoc.manifest.scanner as scanner

    real_hash = scanner.hash_file

    def boom(path: Path) -> str:
        if path.name == "secret.md":
            raise OSError("permission denied")
        return real_hash(path)

    monkeypatch.setattr(scanner, "hash_file", boom)

    sources = scan_sources(tmp_path, scanned_at=_now())
    secret = next(s for s in sources if s.relative_path == "secret.md")
    assert secret.status is ProcessingStatus.UNREADABLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/manifest/test_scanner_hardening.py -v`
Expected: FAIL — `ProcessingStatus.UNREADABLE` does not exist / scanner raises OSError.

- [ ] **Step 3: Add the enum member and helper**

In `loop_apidoc/manifest/models.py`, extend `ProcessingStatus`:

```python
class ProcessingStatus(str, Enum):
    PENDING = "pending"
    UNSUPPORTED = "unsupported"
    DUPLICATE = "duplicate"
    UNREADABLE = "unreadable"
```

Add to `Manifest` (after `duplicates`):

```python
    def unreadable(self) -> list[LocalSource]:
        return [s for s in self.local_sources if s.status is ProcessingStatus.UNREADABLE]
```

- [ ] **Step 4: Harden the scan loop**

Replace the `for path in files:` body in `loop_apidoc/manifest/scanner.py` so each file's hashing/stat is guarded. Also guard `is_file()` during listing against broken symlinks:

```python
    files = sorted(
        (p for p in root.rglob("*") if _is_regular_file(p)),
        key=lambda p: p.relative_to(root).as_posix(),
    )

    for path in files:
        relative_path = path.relative_to(root).as_posix()
        source_format = detect_format(path)
        supported = is_supported(source_format)

        try:
            sha256 = hash_file(path)
            size_bytes = path.stat().st_size
        except OSError:
            sources.append(
                LocalSource(
                    relative_path=relative_path,
                    mime_type=guess_mime_type(path),
                    source_format=source_format,
                    size_bytes=0,
                    sha256="",
                    scanned_at=scanned_at,
                    supported=False,
                    status=ProcessingStatus.UNREADABLE,
                    duplicate_of=None,
                )
            )
            continue

        if not supported:
            status = ProcessingStatus.UNSUPPORTED
            duplicate_of = None
        elif sha256 in seen_hashes:
            status = ProcessingStatus.DUPLICATE
            duplicate_of = seen_hashes[sha256]
        else:
            status = ProcessingStatus.PENDING
            duplicate_of = None
            seen_hashes[sha256] = relative_path

        sources.append(
            LocalSource(
                relative_path=relative_path,
                mime_type=guess_mime_type(path),
                source_format=source_format,
                size_bytes=size_bytes,
                sha256=sha256,
                scanned_at=scanned_at,
                supported=supported,
                status=status,
                duplicate_of=duplicate_of,
            )
        )

    return sources
```

Add a module-level helper above `scan_sources` so a broken symlink is listed (as unreadable) rather than skipped by `is_file()`:

```python
def _is_regular_file(path: Path) -> bool:
    try:
        if path.is_file():
            return True
        # Broken symlink: exists as an entry but target is gone.
        return path.is_symlink()
    except OSError:
        return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/manifest/test_scanner_hardening.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/manifest/scanner.py loop_apidoc/manifest/models.py tests/manifest/test_scanner_hardening.py
git commit -m "fix: [manifest] record unreadable files instead of aborting scan"
```

---

## Task 2: Run package skeleton — models + run id

**Files:**
- Create: `loop_apidoc/run/__init__.py`
- Create: `loop_apidoc/run/models.py`
- Create: `loop_apidoc/run/runid.py`
- Test: `tests/run/__init__.py`, `tests/run/test_runid.py`, `tests/run/test_models.py`

**Interfaces:**
- Produces:
  - `make_run_id(now: datetime) -> str` — formats UTC time as `%Y%m%dT%H%M%SZ` (e.g. `20260626T104300Z`).
  - `RunStatus(str, Enum)` — `PASSED = "passed"`, `FAILED = "failed"`, `EARLY_STOPPED = "early-stopped"`, `BLOCKED = "blocked"`.
  - `CorrectionCategory(str, Enum)` — `AUTO_FIX = "auto-fix"`, `RE_QUERY = "re-query"`, `UNFIXABLE = "unfixable"`.
  - `CorrectionOutcome(BaseModel)` — `plan: NormalizationPlan`, `result: GenerateResult`, `report: ValidationReport`, `rounds: int`, `status: RunStatus`.
  - `RunResult(BaseModel)` — `run_id: str`, `run_dir: str`, `report: ValidationReport`, `rounds: int`, `status: RunStatus`; property `ok -> bool` is `status == RunStatus.PASSED`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/run/__init__.py  (empty file)
```

```python
# tests/run/test_runid.py
from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.run.runid import make_run_id


def test_make_run_id_utc_format() -> None:
    now = datetime(2026, 6, 26, 10, 43, 0, tzinfo=timezone.utc)
    assert make_run_id(now) == "20260626T104300Z"
```

```python
# tests/run/test_models.py
from __future__ import annotations

from loop_apidoc.run.models import RunResult, RunStatus
from loop_apidoc.validate.models import ValidationReport


def test_run_result_ok_only_when_passed() -> None:
    report = ValidationReport(issues=[])
    passed = RunResult(
        run_id="r1", run_dir="/tmp/r1", report=report, rounds=0, status=RunStatus.PASSED
    )
    failed = RunResult(
        run_id="r1", run_dir="/tmp/r1", report=report, rounds=3, status=RunStatus.FAILED
    )
    assert passed.ok is True
    assert failed.ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/run/ -v`
Expected: FAIL — `loop_apidoc.run` module not found.

- [ ] **Step 3: Create the modules**

```python
# loop_apidoc/run/__init__.py
"""Full-run orchestration and correction loop (spec §3.2, §8, §10)."""

from loop_apidoc.run.models import (
    CorrectionCategory,
    CorrectionOutcome,
    RunResult,
    RunStatus,
)
from loop_apidoc.run.runid import make_run_id

__all__ = [
    "CorrectionCategory",
    "CorrectionOutcome",
    "RunResult",
    "RunStatus",
    "make_run_id",
]
```

```python
# loop_apidoc/run/runid.py
from __future__ import annotations

from datetime import datetime


def make_run_id(now: datetime) -> str:
    """Mint a filesystem-safe UTC run id, e.g. 20260626T104300Z."""
    return now.strftime("%Y%m%dT%H%M%SZ")
```

```python
# loop_apidoc/run/models.py
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.models import ValidationReport


class RunStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    EARLY_STOPPED = "early-stopped"
    BLOCKED = "blocked"


class CorrectionCategory(str, Enum):
    AUTO_FIX = "auto-fix"
    RE_QUERY = "re-query"
    UNFIXABLE = "unfixable"


class CorrectionOutcome(BaseModel):
    plan: NormalizationPlan
    result: GenerateResult
    report: ValidationReport
    rounds: int
    status: RunStatus


class RunResult(BaseModel):
    run_id: str
    run_dir: str
    report: ValidationReport
    rounds: int
    status: RunStatus

    @property
    def ok(self) -> bool:
        return self.status is RunStatus.PASSED
```

Then update `loop_apidoc/run/__init__.py` to also export `run_pipeline` in Task 5 (left out now; add in Task 5).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/run/ -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/run/__init__.py loop_apidoc/run/models.py loop_apidoc/run/runid.py tests/run/
git commit -m "feat: [run] add run package skeleton with run-id and result models"
```

---

## Task 3: Issue classification + fixability annotation

**Files:**
- Create: `loop_apidoc/run/correction.py` (classification half only)
- Test: `tests/run/test_classify.py`

**Interfaces:**
- Consumes: `Issue`, `IssueCode`, `Severity`, `ValidationReport` (from `loop_apidoc.validate.models`); `CorrectionCategory` (Task 2).
- Produces:
  - `classify_issue(issue: Issue) -> CorrectionCategory` — pure mapping:
    - `OPENAPI_INVALID`, `OUTPUT_MISMATCH` → `AUTO_FIX`
    - `REQUIRED_INFO_MISSING` → `RE_QUERY`
    - `SOURCE_UNVERIFIED`, `SOURCE_CONFLICT`, `UNSUPPORTED_ASSERTION` → `UNFIXABLE` (fail-closed; never speculate)
  - `annotate_fixability(report: ValidationReport) -> ValidationReport` — returns a new report whose every issue has `auto_fixable = (classify_issue(issue) == AUTO_FIX)`; input untouched.
  - `actionable_codes(report: ValidationReport) -> list[Issue]` — error-severity issues whose category is `AUTO_FIX` or `RE_QUERY`.

- [ ] **Step 1: Write the failing test**

```python
# tests/run/test_classify.py
from __future__ import annotations

from loop_apidoc.run.correction import (
    actionable_codes,
    annotate_fixability,
    classify_issue,
)
from loop_apidoc.run.models import CorrectionCategory
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def _issue(code: IssueCode, severity: Severity = Severity.ERROR) -> Issue:
    return Issue(
        code=code,
        severity=severity,
        location="x",
        evidence="e",
        suggested_fix="f",
    )


def test_classify_each_code() -> None:
    assert classify_issue(_issue(IssueCode.OPENAPI_INVALID)) is CorrectionCategory.AUTO_FIX
    assert classify_issue(_issue(IssueCode.OUTPUT_MISMATCH)) is CorrectionCategory.AUTO_FIX
    assert classify_issue(_issue(IssueCode.REQUIRED_INFO_MISSING)) is CorrectionCategory.RE_QUERY
    assert classify_issue(_issue(IssueCode.SOURCE_UNVERIFIED)) is CorrectionCategory.UNFIXABLE
    assert classify_issue(_issue(IssueCode.SOURCE_CONFLICT)) is CorrectionCategory.UNFIXABLE
    assert classify_issue(_issue(IssueCode.UNSUPPORTED_ASSERTION)) is CorrectionCategory.UNFIXABLE


def test_annotate_fixability_does_not_mutate_input() -> None:
    report = ValidationReport(issues=[_issue(IssueCode.OPENAPI_INVALID)])
    annotated = annotate_fixability(report)
    assert annotated.issues[0].auto_fixable is True
    assert report.issues[0].auto_fixable is False  # unchanged


def test_actionable_codes_filters_unfixable_and_warnings() -> None:
    report = ValidationReport(
        issues=[
            _issue(IssueCode.REQUIRED_INFO_MISSING),
            _issue(IssueCode.SOURCE_CONFLICT),
            _issue(IssueCode.OPENAPI_INVALID, severity=Severity.WARNING),
        ]
    )
    codes = [i.code for i in actionable_codes(report)]
    assert codes == [IssueCode.REQUIRED_INFO_MISSING]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/run/test_classify.py -v`
Expected: FAIL — `loop_apidoc.run.correction` not found.

- [ ] **Step 3: Implement classification**

```python
# loop_apidoc/run/correction.py
from __future__ import annotations

from loop_apidoc.run.models import CorrectionCategory
from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)

_CATEGORY: dict[IssueCode, CorrectionCategory] = {
    IssueCode.OPENAPI_INVALID: CorrectionCategory.AUTO_FIX,
    IssueCode.OUTPUT_MISMATCH: CorrectionCategory.AUTO_FIX,
    IssueCode.REQUIRED_INFO_MISSING: CorrectionCategory.RE_QUERY,
    IssueCode.SOURCE_UNVERIFIED: CorrectionCategory.UNFIXABLE,
    IssueCode.SOURCE_CONFLICT: CorrectionCategory.UNFIXABLE,
    IssueCode.UNSUPPORTED_ASSERTION: CorrectionCategory.UNFIXABLE,
}


def classify_issue(issue: Issue) -> CorrectionCategory:
    """Map a validation issue to a correction strategy (spec §10).

    Fail-closed: anything not explicitly fixable is UNFIXABLE so the loop
    never speculates over source-missing or conflicting content.
    """
    return _CATEGORY.get(issue.code, CorrectionCategory.UNFIXABLE)


def annotate_fixability(report: ValidationReport) -> ValidationReport:
    """Return a new report with auto_fixable set per classification."""
    issues = [
        issue.model_copy(
            update={"auto_fixable": classify_issue(issue) is CorrectionCategory.AUTO_FIX}
        )
        for issue in report.issues
    ]
    return ValidationReport(issues=issues)


def actionable_codes(report: ValidationReport) -> list[Issue]:
    """Error-severity issues the loop can act on (auto-fix or re-query)."""
    return [
        issue
        for issue in report.issues
        if issue.severity is Severity.ERROR
        and classify_issue(issue)
        in (CorrectionCategory.AUTO_FIX, CorrectionCategory.RE_QUERY)
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/run/test_classify.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/run/correction.py tests/run/test_classify.py
git commit -m "feat: [run] classify validation issues into correction categories"
```

---

## Task 4: Correction loop

**Files:**
- Modify: `loop_apidoc/run/correction.py` (add `run_correction_loop`)
- Test: `tests/run/test_correction_loop.py`

**Interfaces:**
- Consumes: `validate_outputs` is NOT called inside the loop directly; instead a `validate` callable is injected so the loop is pure and testable. Closures injected by the pipeline (Task 5):
  - `regenerate: Callable[[NormalizationPlan], GenerateResult]`
  - `requery: Callable[[NormalizationPlan, ValidationReport], NormalizationPlan]`
  - `validate: Callable[[NormalizationPlan, GenerateResult], ValidationReport]`
- Produces:
  - `run_correction_loop(plan, result, *, regenerate, requery, validate, max_rounds=3) -> CorrectionOutcome`

  Algorithm (spec §10):
  1. `report = validate(plan, result)`; if `report.ok` → `PASSED`, rounds=0.
  2. Loop while not ok and rounds < max_rounds:
     - `actionable = actionable_codes(report)`; if empty → `EARLY_STOPPED` (all remaining are source-missing/conflict).
     - `rounds += 1`.
     - if any actionable issue classifies as `RE_QUERY` → `plan = requery(plan, report)`.
     - `result = regenerate(plan)`.
     - `report = validate(plan, result)`; if `report.ok` → `PASSED`, stop.
  3. After loop, status is `PASSED` if `report.ok` else `FAILED`.
  4. The returned `report` is passed through `annotate_fixability`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/run/test_correction_loop.py
from __future__ import annotations

from loop_apidoc.run.correction import run_correction_loop
from loop_apidoc.run.models import RunStatus
from loop_apidoc.generate.models import GenerateResult, ProvenanceDocument
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def _plan() -> NormalizationPlan:
    return NormalizationPlan(notebook_url="nb://x")


def _result() -> GenerateResult:
    return GenerateResult(
        openapi={"openapi": "3.1.0"},
        markdown="# doc",
        provenance=ProvenanceDocument(notebook_url="nb", entries=[]),
    )


def _missing_report() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.REQUIRED_INFO_MISSING,
                severity=Severity.ERROR,
                location="paths./x.get",
                evidence="no responses",
                suggested_fix="add responses",
            )
        ]
    )


def _conflict_report() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.SOURCE_CONFLICT,
                severity=Severity.ERROR,
                location="paths./x.get",
                evidence="two sources disagree",
                suggested_fix="resolve at source",
            )
        ]
    )


def test_passes_on_first_validation() -> None:
    outcome = run_correction_loop(
        _plan(),
        _result(),
        regenerate=lambda p: _result(),
        requery=lambda p, r: p,
        validate=lambda p, r: ValidationReport(issues=[]),
    )
    assert outcome.status is RunStatus.PASSED
    assert outcome.rounds == 0


def test_recovers_within_three_rounds() -> None:
    reports = [_missing_report(), _missing_report(), ValidationReport(issues=[])]
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
        _plan(), _result(), regenerate=lambda p: _result(), requery=requery, validate=validate
    )
    assert outcome.status is RunStatus.PASSED
    assert outcome.rounds == 2
    assert requeries["n"] == 2


def test_final_failure_after_three_rounds() -> None:
    outcome = run_correction_loop(
        _plan(),
        _result(),
        regenerate=lambda p: _result(),
        requery=lambda p, r: p,
        validate=lambda p, r: _missing_report(),
    )
    assert outcome.status is RunStatus.FAILED
    assert outcome.rounds == 3


def test_early_stop_on_unfixable_only() -> None:
    requeries = {"n": 0}

    def requery(p, r):
        requeries["n"] += 1
        return p

    outcome = run_correction_loop(
        _plan(),
        _result(),
        regenerate=lambda p: _result(),
        requery=requery,
        validate=lambda p, r: _conflict_report(),
    )
    assert outcome.status is RunStatus.EARLY_STOPPED
    assert outcome.rounds == 0
    assert requeries["n"] == 0  # no NotebookLM quota wasted
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/run/test_correction_loop.py -v`
Expected: FAIL — `run_correction_loop` not defined.

- [ ] **Step 3: Implement the loop**

Append to `loop_apidoc/run/correction.py`:

```python
from collections.abc import Callable

from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.run.models import CorrectionOutcome, RunStatus


def run_correction_loop(
    plan: NormalizationPlan,
    result: GenerateResult,
    *,
    regenerate: Callable[[NormalizationPlan], GenerateResult],
    requery: Callable[[NormalizationPlan, ValidationReport], NormalizationPlan],
    validate: Callable[[NormalizationPlan, GenerateResult], ValidationReport],
    max_rounds: int = 3,
) -> CorrectionOutcome:
    """Run the spec §10 correction loop over injected I/O closures.

    Rounds count post-generation correction attempts (max 3). Stops early when
    the only remaining errors are source-missing/conflict (no quota waste).
    """
    report = validate(plan, result)
    rounds = 0

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

    status = RunStatus.PASSED if report.ok else RunStatus.FAILED
    return CorrectionOutcome(
        plan=plan,
        result=result,
        report=annotate_fixability(report),
        rounds=rounds,
        status=status,
    )
```

Note: move the `from collections.abc import Callable` and `GenerateResult`/`NormalizationPlan`/`CorrectionOutcome`/`RunStatus` imports to the top of the file with the existing imports rather than mid-file (consolidate during this step).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/run/test_correction_loop.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the whole run-package suite**

Run: `uv run pytest tests/run/ -v`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/run/correction.py tests/run/test_correction_loop.py
git commit -m "feat: [run] correction loop with early-stop and max-3-round behavior"
```

---

## Task 5: Pipeline orchestration

**Files:**
- Create: `loop_apidoc/run/pipeline.py`
- Modify: `loop_apidoc/run/__init__.py` (export `run_pipeline`)
- Test: `tests/integration/test_run_pipeline.py`

**Interfaces:**
- Consumes: `build_manifest`, `NotebookLMAdapter`, `ExtractionStore`, `run_extraction`, `build_normalization_plan`, `generate_outputs`, `validate_outputs`, `write_reports`, `make_run_id`, `run_correction_loop`, `annotate_fixability`.
- Produces:
  - `run_pipeline(*, notebook_url, sources_root, output_root, adapter, run_id, urls=None, max_rounds=3) -> RunResult`

  Responsibilities (sole file-I/O owner besides the seams it calls):
  1. `run_dir = output_root / run_id`; `run_dir.mkdir(parents=True, exist_ok=True)`.
  2. Build manifest (`build_manifest(sources_root, urls or [], generated_at=...)`). Persist to `run_dir/manifest.json`. *Note:* `generated_at` is passed in by the caller; pipeline does not call `datetime.now` (keeps it deterministic/testable). Add a `generated_at: datetime` parameter.
  3. Auth preflight: `status = adapter.auth_status()`; if not `status.authenticated`, return `RunResult(status=RunStatus.BLOCKED, ...)` with a one-issue report (`SOURCE_UNVERIFIED`, location `notebooklm.auth`, evidence = login required). Do NOT proceed to extraction (spec §11).
  4. Extraction: `store = ExtractionStore(run_dir / "extraction")`; `extraction = run_extraction(adapter, notebook_url, store)`.
  5. Plan: `plan = build_normalization_plan(extraction, manifest)`; persist to `run_dir/plan/normalization-plan.json`.
  6. Generate: `result = generate_outputs(plan, manifest, run_dir)`.
  7. Correction loop with closures:
     - `regenerate = lambda p: generate_outputs(p, manifest, run_dir)`
     - `validate = lambda p, r: validate_outputs(p, r, manifest)`
     - `requery = lambda p, r: build_normalization_plan(run_extraction(adapter, notebook_url, store), manifest)`
  8. After loop: `write_reports(outcome.report, run_dir / "validation")`. Also persist the final plan again (it may have changed via re-query).
  9. Return `RunResult(run_id, str(run_dir), report=outcome.report, rounds=outcome.rounds, status=outcome.status)`.

  Errors: `AuthRequired` / `NotebookInaccessible` raised by the adapter inside extraction propagate to the CLI (Task 6 maps them). The pipeline itself only catches nothing — preflight handles the common auth case; accessibility surfaces on first query (documented limitation).

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_run_pipeline.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.runner import CommandResult
from loop_apidoc.run.models import RunStatus
from loop_apidoc.run.pipeline import run_pipeline


def _now() -> datetime:
    return datetime(2026, 6, 26, 10, 43, 0, tzinfo=timezone.utc)


_SEPARATOR = "=" * 60
_FOLLOW_UP = "EXTREMELY IMPORTANT: Is that ALL you need to know?"


def _frame_answer(question: str, answer: str) -> str:
    # Matches loop_apidoc.notebooklm.parsing.parse_ask_answer expectations.
    return (
        f"Question: {question}\n"
        f"{_SEPARATOR}\n"
        f"{answer}\n"
        f"{_FOLLOW_UP}\n"
    )


class _ScriptedRunner:
    """Returns canned stdout per skill invocation, matching the run.py contract."""

    def __init__(self, *, auth_ok: bool, answers: list[str]) -> None:
        self._auth_ok = auth_ok
        self._answers = list(answers)
        self._idx = 0

    def __call__(self, argv: list[str]) -> CommandResult:
        joined = " ".join(argv)
        if "auth_manager.py" in joined:
            line = "Authenticated: Yes" if self._auth_ok else "Authenticated: No"
            return CommandResult(argv=argv, returncode=0, stdout=line, stderr="")
        # ask_question.py — emit the documented Question/separator/follow-up framing.
        answer = self._answers[min(self._idx, len(self._answers) - 1)]
        self._idx += 1
        return CommandResult(
            argv=argv, returncode=0, stdout=_frame_answer("q", answer), stderr=""
        )


def _adapter(runner) -> NotebookLMAdapter:
    return NotebookLMAdapter(SkillConfig(skill_root=Path("notebooklm-skill")), runner)


def test_pipeline_blocks_when_not_authenticated(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "api.md").write_text("# API", encoding="utf-8")
    runner = _ScriptedRunner(auth_ok=False, answers=[])
    result = run_pipeline(
        notebook_url="nb://x",
        sources_root=tmp_path / "src",
        output_root=tmp_path / "out",
        adapter=_adapter(runner),
        run_id="20260626T104300Z",
        generated_at=_now(),
    )
    assert result.status is RunStatus.BLOCKED
    assert not (tmp_path / "out" / "20260626T104300Z" / "openapi.yaml").exists()


def test_pipeline_writes_run_dir_layout(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "api.md").write_text("# API", encoding="utf-8")
    # Minimal answers: enough that extraction completes; content drives a
    # source-missing failure but the run-dir must still be fully materialized.
    runner = _ScriptedRunner(auth_ok=True, answers=["No structured data available."])
    result = run_pipeline(
        notebook_url="nb://x",
        sources_root=tmp_path / "src",
        output_root=tmp_path / "out",
        adapter=_adapter(runner),
        run_id="20260626T104300Z",
        generated_at=_now(),
    )
    run_dir = tmp_path / "out" / "20260626T104300Z"
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "extraction" / "queries.jsonl").exists()
    assert (run_dir / "plan" / "normalization-plan.json").exists()
    assert (run_dir / "openapi.yaml").exists()
    assert (run_dir / "api-guide.zh-TW.md").exists()
    assert (run_dir / "provenance.json").exists()
    assert (run_dir / "validation" / "report.json").exists()
    assert (run_dir / "validation" / "report.md").exists()
    assert result.status in (RunStatus.PASSED, RunStatus.FAILED, RunStatus.EARLY_STOPPED)
    # manifest.json is valid JSON
    json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_run_pipeline.py -v`
Expected: FAIL — `run_pipeline` not found.

- [ ] **Step 3: Implement the pipeline**

```python
# loop_apidoc/run/pipeline.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loop_apidoc.extraction.orchestrator import run_extraction
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.generate.writer import generate_outputs
from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.run.correction import annotate_fixability, run_correction_loop
from loop_apidoc.run.models import RunResult, RunStatus
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport
from loop_apidoc.validate.report import write_reports
from loop_apidoc.validate.validator import validate_outputs


def _auth_blocked_report() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.SOURCE_UNVERIFIED,
                severity=Severity.ERROR,
                location="notebooklm.auth",
                evidence="NotebookLM 未驗證；請先登入。",
                suggested_fix="執行 notebooklm-skill 登入流程後重試。",
            )
        ]
    )


def run_pipeline(
    *,
    notebook_url: str,
    sources_root: Path,
    output_root: Path,
    adapter: NotebookLMAdapter,
    run_id: str,
    generated_at: datetime,
    urls: list[str] | None = None,
    max_rounds: int = 3,
) -> RunResult:
    """Run the full source-grounded doc pipeline into output_root/run_id."""
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [], generated_at=generated_at
    )
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    status = adapter.auth_status()
    if not status.authenticated:
        report = annotate_fixability(_auth_blocked_report())
        write_reports(report, run_dir / "validation")
        return RunResult(
            run_id=run_id,
            run_dir=str(run_dir),
            report=report,
            rounds=0,
            status=RunStatus.BLOCKED,
        )

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

    outcome = run_correction_loop(
        plan,
        result,
        regenerate=regenerate,
        requery=requery,
        validate=validate,
        max_rounds=max_rounds,
    )

    write_reports(outcome.report, run_dir / "validation")
    return RunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        report=outcome.report,
        rounds=outcome.rounds,
        status=outcome.status,
    )


def _persist_plan(run_dir: Path, plan) -> None:
    plan_dir = run_dir / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "normalization-plan.json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8"
    )
```

Add `run_pipeline` to `loop_apidoc/run/__init__.py` exports:

```python
from loop_apidoc.run.pipeline import run_pipeline
```
and add `"run_pipeline"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_run_pipeline.py -v`
Expected: PASS (2 passed). If extraction needs more canned answers than provided, the `_ScriptedRunner` repeats its last answer (already handled by `min(...)`).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/run/pipeline.py loop_apidoc/run/__init__.py tests/integration/test_run_pipeline.py
git commit -m "feat: [run] orchestrate full pipeline into a run directory"
```

---

## Task 6: `run` CLI command

**Files:**
- Modify: `loop_apidoc/cli.py`
- Test: `tests/test_cli_run.py`

**Interfaces:**
- Consumes: `run_pipeline`, `make_run_id`, `RunStatus`, `NotebookLMAdapter`, `SkillConfig`, `subprocess_runner`, NotebookLM error types.
- Produces: `loop-apidoc run --notebook-url ... --sources ... --output ...` command.

  Behavior:
  - Mint `run_id = make_run_id(datetime.now(timezone.utc))`; `generated_at` = same `now`.
  - Build a real adapter. Note `subprocess_runner` is a **factory** `(config, timeout_seconds=...) -> ProcessRunner` — call it to get the runner: `NotebookLMAdapter(config, subprocess_runner(config))`. Add a `--skill-root` option mirroring `doctor` (envvar `LOOP_APIDOC_SKILL_ROOT`).
  - Call `run_pipeline(...)`. Catch `AuthRequired` / `NotebookInaccessible` / `MalformedOutput` / `SkillSetupError` / `SkillError` and print a clear message; exit non-zero.
  - On return, print a status line (run dir, rounds, error/warning counts).
  - Exit code: `0` only when `result.status is RunStatus.PASSED`; otherwise `1`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_run.py
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import loop_apidoc.cli as cli
from loop_apidoc.run.models import RunResult, RunStatus
from loop_apidoc.validate.models import ValidationReport

runner = CliRunner()


def test_run_exit_zero_on_pass(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.md").write_text("# x", encoding="utf-8")

    def fake_pipeline(**kwargs) -> RunResult:
        return RunResult(
            run_id="rid",
            run_dir=str(tmp_path / "out" / "rid"),
            report=ValidationReport(issues=[]),
            rounds=0,
            status=RunStatus.PASSED,
        )

    monkeypatch.setattr(cli, "run_pipeline", fake_pipeline)
    result = runner.invoke(
        cli.app,
        [
            "run",
            "--notebook-url",
            "nb://x",
            "--sources",
            str(tmp_path / "src"),
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0


def test_run_exit_one_on_failure(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.md").write_text("# x", encoding="utf-8")

    def fake_pipeline(**kwargs) -> RunResult:
        return RunResult(
            run_id="rid",
            run_dir=str(tmp_path / "out" / "rid"),
            report=ValidationReport(issues=[]),
            rounds=3,
            status=RunStatus.FAILED,
        )

    monkeypatch.setattr(cli, "run_pipeline", fake_pipeline)
    result = runner.invoke(
        cli.app,
        [
            "run",
            "--notebook-url",
            "nb://x",
            "--sources",
            str(tmp_path / "src"),
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_run.py -v`
Expected: FAIL — no `run` command / `cli.run_pipeline` attribute.

- [ ] **Step 3: Add the command to `loop_apidoc/cli.py`**

Add imports near the top:

```python
from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.errors import NotebookLMError
from loop_apidoc.notebooklm.runner import subprocess_runner
from loop_apidoc.run.models import RunStatus
from loop_apidoc.run.pipeline import run_pipeline
from loop_apidoc.run.runid import make_run_id
```

Add the command (after `validate`):

```python
@app.command()
def run(
    notebook_url: str = typer.Option(
        ..., "--notebook-url", help="NotebookLM 分享連結"
    ),
    sources: Path = typer.Option(
        ...,
        "--sources",
        help="本機來源目錄",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    output: Path = typer.Option(
        ..., "--output", help="輸出根目錄（將建立 <run-id> 子目錄）"
    ),
    url: list[str] = typer.Option([], "--url", help="公開來源 URL，可重複指定"),
    skill_root: Path = typer.Option(
        Path("notebooklm-skill"),
        "--skill-root",
        envvar="LOOP_APIDOC_SKILL_ROOT",
        help="notebooklm-skill checkout 目錄",
    ),
) -> None:
    """執行完整流程：manifest → 擷取 → 規劃 → 生成 → 驗證 → 修正（最多三輪）。"""
    now = datetime.now(timezone.utc)
    config = SkillConfig(skill_root=skill_root)
    adapter = NotebookLMAdapter(config, subprocess_runner(config))
    try:
        result = run_pipeline(
            notebook_url=notebook_url,
            sources_root=sources,
            output_root=output,
            adapter=adapter,
            run_id=make_run_id(now),
            generated_at=now,
            urls=list(url),
        )
    except NotebookLMError as exc:
        typer.echo(f"執行中止：{exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"狀態 {result.status.value}：修正 {result.rounds} 輪，"
        f"error {len(result.report.errors())}，warning {len(result.report.warnings())}；"
        f"輸出於 {result.run_dir}"
    )
    raise typer.Exit(code=0 if result.ok else 1)
```

Note: `SkillConfig` and `datetime`/`timezone` are already imported in `cli.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_run.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Verify the command appears in help**

Run: `uv run loop-apidoc --help`
Expected: lists `run` alongside `doctor`, `manifest`, `validate`.

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/cli.py tests/test_cli_run.py
git commit -m "feat: [run] wire loop-apidoc run command with exit code"
```

---

## Task 7: Integration scenarios — 3-round success, early stop, final failure

**Files:**
- Modify: `tests/integration/test_run_pipeline.py` (add scenario tests driven through `run_correction_loop` via the pipeline's closures)
- Create: `tests/integration/test_correction_scenarios.py`

**Interfaces:**
- Consumes: `run_correction_loop` with hand-built closures that emulate improving / static / conflict-only NotebookLM behavior (spec §12.2 — "三輪修正成功、提前停止及最終失敗").
- Produces: no new product code; this task proves the spec §10 stop behavior end-to-end with realistic plan/result/report objects.

- [ ] **Step 1: Write the scenario tests**

```python
# tests/integration/test_correction_scenarios.py
from __future__ import annotations

from loop_apidoc.run.correction import run_correction_loop
from loop_apidoc.run.models import RunStatus
from loop_apidoc.generate.models import GenerateResult, ProvenanceDocument
from loop_apidoc.plan.models import EndpointEntry, NormalizationPlan, SourceCitation
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def _result() -> GenerateResult:
    return GenerateResult(
        openapi={"openapi": "3.1.0", "paths": {}},
        markdown="# doc",
        provenance=ProvenanceDocument(notebook_url="nb", entries=[]),
    )


def _missing() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.REQUIRED_INFO_MISSING,
                severity=Severity.ERROR,
                location="paths./x.get",
                evidence="missing responses",
                suggested_fix="re-query stage 06",
            )
        ]
    )


def _ok() -> ValidationReport:
    return ValidationReport(issues=[])


def _conflict() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.SOURCE_CONFLICT,
                severity=Severity.ERROR,
                location="paths./x.get",
                evidence="sources disagree",
                suggested_fix="resolve at source",
            )
        ]
    )


def test_three_round_success() -> None:
    # Fails round 1 and 2, passes on round 3 (rounds==2 since round 0 is initial).
    seq = [_missing(), _missing(), _ok()]
    i = {"n": 0}

    def validate(p, r):
        rep = seq[i["n"]]
        i["n"] += 1
        return rep

    outcome = run_correction_loop(
        NormalizationPlan(notebook_url="nb"),
        _result(),
        regenerate=lambda p: _result(),
        requery=lambda p, r: p,
        validate=validate,
    )
    assert outcome.status is RunStatus.PASSED
    assert outcome.rounds == 2


def test_final_failure_persists_artifacts_state() -> None:
    outcome = run_correction_loop(
        NormalizationPlan(notebook_url="nb"),
        _result(),
        regenerate=lambda p: _result(),
        requery=lambda p, r: p,
        validate=lambda p, r: _missing(),
    )
    assert outcome.status is RunStatus.FAILED
    assert outcome.rounds == 3
    # Report carries fixability annotation for downstream rendering.
    assert outcome.report.issues[0].auto_fixable is False


def test_early_stop_conflict_only_no_rounds() -> None:
    outcome = run_correction_loop(
        NormalizationPlan(notebook_url="nb"),
        _result(),
        regenerate=lambda p: _result(),
        requery=lambda p, r: p,
        validate=lambda p, r: _conflict(),
    )
    assert outcome.status is RunStatus.EARLY_STOPPED
    assert outcome.rounds == 0
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_correction_scenarios.py -v`
Expected: PASS (3 passed). (No product code changes — these lock the §12.2 behavior.)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_correction_scenarios.py
git commit -m "test: [run] cover three-round success, early stop, final failure"
```

---

## Task 8: Real-skill smoke test marker (carry-forward) + timeout stderr

**Files:**
- Create: `tests/smoke/__init__.py`, `tests/smoke/test_real_skill_smoke.py`
- Modify: `pyproject.toml` (register `smoke` marker)
- Modify: `loop_apidoc/notebooklm/runner.py` (fold `exc.stderr` into timeout `CommandResult`)
- Test: `tests/notebooklm/test_runner_timeout.py`

**Interfaces:**
- Consumes: `subprocess_runner`, `NotebookLMAdapter` for a real, env-gated query (spec §12.3 — "需由明確命令觸發，不納入一般單元測試").
- Produces: a `@pytest.mark.smoke` test, skipped unless `LOOP_APIDOC_SMOKE=1`, that asserts the documented `Question:` / `=`×60 separator framing and that an ask returns a non-empty answer.

- [ ] **Step 1: Register the marker**

In `pyproject.toml`, under the pytest config, add the `smoke` marker (create the `[tool.pytest.ini_options]` `markers` list if absent):

```toml
[tool.pytest.ini_options]
markers = [
    "smoke: real NotebookLM skill smoke tests; run only with LOOP_APIDOC_SMOKE=1",
]
```

(Preserve any existing keys in that table.)

- [ ] **Step 2: Write the timeout-stderr test (failing)**

First inspect the current timeout branch:

Run: `sed -n '1,60p' loop_apidoc/notebooklm/runner.py`

```python
# tests/notebooklm/test_runner_timeout.py
from __future__ import annotations

import subprocess
from pathlib import Path

import loop_apidoc.notebooklm.runner as runner_mod
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.runner import subprocess_runner


def test_timeout_preserves_stderr(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0] if args else "x", timeout=1, output="partial", stderr="boom"
        )

    monkeypatch.setattr(runner_mod.subprocess, "run", fake_run)
    runner = subprocess_runner(SkillConfig(skill_root=Path("notebooklm-skill")))
    result = runner(["python", "scripts/run.py", "ask_question.py"])
    assert result.returncode != 0
    assert "boom" in result.stderr
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/notebooklm/test_runner_timeout.py -v`
Expected: FAIL — current timeout branch likely drops `exc.stderr`.

- [ ] **Step 4: Fold stderr into the timeout result**

In `loop_apidoc/notebooklm/runner.py`, in the `except subprocess.TimeoutExpired as exc:` branch, include `exc.stderr` in the returned `CommandResult.stderr` (decode/handle `None` → `""`). Match the existing surrounding style; e.g.:

```python
        except subprocess.TimeoutExpired as exc:
            extra = exc.stderr or ""
            if isinstance(extra, bytes):
                extra = extra.decode("utf-8", errors="replace")
            message = "Timeout waiting for answer"
            if extra:
                message = f"{message}: {extra}"
            return CommandResult(
                argv=argv,
                returncode=124,
                stdout=exc.stdout or "",
                stderr=message,
            )
```

The behavioral requirement: timeout yields a non-zero `CommandResult` (returncode 124, `argv` preserved) whose `stderr` keeps the existing "Timeout waiting for answer" text **and** appends the subprocess stderr when present.

- [ ] **Step 5: Write the smoke test (skipped by default)**

```python
# tests/smoke/__init__.py  (empty file)
```

```python
# tests/smoke/test_real_skill_smoke.py
from __future__ import annotations

import os
from pathlib import Path

import pytest

from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.config import SkillConfig
from loop_apidoc.notebooklm.runner import subprocess_runner

pytestmark = pytest.mark.smoke

_ENABLED = os.environ.get("LOOP_APIDOC_SMOKE") == "1"
_NOTEBOOK = os.environ.get("LOOP_APIDOC_SMOKE_NOTEBOOK", "")
_SKILL_ROOT = os.environ.get("LOOP_APIDOC_SKILL_ROOT", "notebooklm-skill")


@pytest.mark.skipif(not _ENABLED, reason="set LOOP_APIDOC_SMOKE=1 to run real-skill smoke")
def test_real_ask_returns_answer() -> None:
    assert _NOTEBOOK, "set LOOP_APIDOC_SMOKE_NOTEBOOK to a test notebook url"
    adapter = NotebookLMAdapter(
        SkillConfig(skill_root=Path(_SKILL_ROOT)), subprocess_runner
    )
    status = adapter.auth_status()
    assert status.authenticated, "skill must be authenticated for smoke test"
    result = adapter.ask("What endpoints exist?", _NOTEBOOK)
    assert result.answer.strip(), "expected a non-empty answer body"
    # Documented framing: the raw stdout wraps the question + a 60-char rule.
    assert "Question:" in result.raw_stdout
    assert "=" * 60 in result.raw_stdout
```

- [ ] **Step 6: Run the timeout test + confirm smoke is collected-but-skipped**

Run: `uv run pytest tests/notebooklm/test_runner_timeout.py tests/smoke/ -v`
Expected: timeout test PASS; smoke test SKIPPED.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml loop_apidoc/notebooklm/runner.py tests/notebooklm/test_runner_timeout.py tests/smoke/
git commit -m "test: [run] add env-gated real-skill smoke marker; keep timeout stderr"
```

---

## Task 9: Full-suite verification + plan-sequence memory update

**Files:**
- No product code; verification + docs/memory.

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all tests pass (Plan 5 left 182; this plan adds ~20+). Note the new total.

- [ ] **Step 2: Confirm the CLI end-to-end help is coherent**

Run: `uv run loop-apidoc --help` and `uv run loop-apidoc run --help`
Expected: `run` documents `--notebook-url`, `--sources`, `--output`, `--url`, `--skill-root`.

- [ ] **Step 3: Update the plan-sequence memory**

Edit `/Users/carl/.claude/projects/-Users-carl-Dev-CMG-Loop-ApiDoc/memory/loop-apidoc-plan-sequence.md`: mark Plan 6 DONE with the merge commit, final test count, the `run_pipeline` seam signature, and any deferred carry-forwards (e.g. Notebook-accessibility preflight relies on first query; requery re-runs full extraction rather than per-stage targeting).

- [ ] **Step 4: Commit any doc updates**

```bash
git add docs
git commit -m "docs: [run] note Plan 6 completion and run command usage"
```

---

## Self-Review

**Spec coverage:**
- §3.2 full CLI flow (manifest→preflight→extract→plan→generate→validate→correct→report+exit) → Tasks 5, 6.
- §5 `run` command + defaults (zh-TW, OpenAPI 3.1, max 3 rounds, no-speculation) → Tasks 4, 6 (Global Constraints).
- §8 run directory layout (manifest/extraction/plan/openapi/markdown/provenance/validation) → Task 5 (+integration assertions).
- §10 correction loop (read report → classify → fix only fixable → regenerate → full re-validate; max 3; early stop on source-only; final failure keeps artifacts + non-zero exit) → Tasks 3, 4, 7.
- §9.5 every issue carries auto-fixable flag → Task 3 `annotate_fixability`.
- §11 auth-not-verified stops with login instructions; transient retries separate from rounds → Task 5 preflight + Global Constraints; unsupported/unreadable files recorded not dropped → Task 1; skill output anomalies preserved → Task 8 stderr.
- §12.2 three-round success / early stop / final failure → Task 7. §12.3 real smoke by explicit command → Task 8.
- §13 completion: single CLI command, exit 0 on success / non-zero otherwise → Task 6.

**Placeholder scan:** No TBD/“handle edge cases”/“similar to Task N” — all steps carry concrete code/commands.

**Type consistency:** `RunStatus`, `CorrectionCategory`, `CorrectionOutcome`, `RunResult` defined in Task 2 and used identically in Tasks 3–6. `run_correction_loop` signature (regenerate/requery/validate/max_rounds) consistent between Task 4 definition and Task 5 usage. `run_pipeline` keyword-only signature consistent between Tasks 5 and 6. `make_run_id` format consistent (Task 2 ↔ Task 6).

**Known deferrals (documented, not gaps):** Notebook-accessibility is surfaced by the first extraction query rather than a dedicated preflight probe (avoids spending a query just to check); `requery` re-runs full `run_extraction` rather than targeting only the stages implicated by issue locations — correct but quota-heavier; per-stage targeting is a future refinement.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-26-loop-apidoc-correction-loop-run.md`.
