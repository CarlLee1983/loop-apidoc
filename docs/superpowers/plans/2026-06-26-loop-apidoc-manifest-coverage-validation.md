# manifest-coverage Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface local sources that cannot be incorporated into normalization (UNREADABLE, UNSUPPORTED) as validation issues, activating the previously-unused `manifest` parameter of `validate_outputs` (spec §6).

**Architecture:** A new pure function `check_manifest_coverage(manifest) -> list[Issue]` in its own module, wired into `validate_outputs` after the existing four §9 checks. Both the in-memory correction-loop path and the disk `validate_run_dir` path receive the manifest already, so wiring one function covers both.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, uv. Pure in-memory logic — no I/O.

## Global Constraints

- Python ≥ 3.12; Pydantic v2 models; never mutate inputs.
- All coverage issues use `IssueCode.SOURCE_UNVERIFIED` — do NOT add a new `IssueCode` enum value and do NOT modify `classify_issue`.
- Severity policy: `UNREADABLE` sources → `Severity.ERROR`; `UNSUPPORTED` sources → `Severity.WARNING`; `DUPLICATE` and `PENDING` sources → no issue.
- `Issue.location` is the source's `relative_path` (the §6 stable source identifier).
- Issue text is Traditional Chinese (Taiwan), matching the surrounding validator code.
- Do NOT modify `loader.py` / `validate_run_dir` — it already loads `manifest.json` and passes it to `validate_outputs`.
- Test commands use `uv run pytest` (this project uses `uv`; no bare `pytest`, no `pip`).
- Commit format: `<type>: [ <scope> ] <subject>`, scope `validate`. No attribution trailers.

---

### Task 1: `check_manifest_coverage` function

**Files:**
- Create: `loop_apidoc/validate/coverage.py`
- Test: `tests/validate/test_coverage.py`

**Interfaces:**
- Consumes:
  - `Manifest` from `loop_apidoc.manifest.models` with helper methods
    `unreadable() -> list[LocalSource]` and `unsupported() -> list[LocalSource]`
    (both already exist). `LocalSource` has `.relative_path: str` and
    `.source_format: SourceFormat` (a `str` Enum with `.value`).
  - `Issue`, `IssueCode`, `Severity` from `loop_apidoc.validate.models`.
    `Issue` fields: `code: IssueCode`, `severity: Severity`, `location: str`,
    `evidence: str`, `suggested_fix: str`, `auto_fixable: bool = False`.
- Produces:
  - `check_manifest_coverage(manifest: Manifest) -> list[Issue]` — consumed by Task 2.

- [ ] **Step 1: Write the failing tests**

Create `tests/validate/test_coverage.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.validate.coverage import check_manifest_coverage
from loop_apidoc.validate.models import IssueCode, Severity

_NOW = datetime(2026, 6, 26, tzinfo=timezone.utc)


def _source(relative_path: str, fmt: SourceFormat, status: ProcessingStatus) -> LocalSource:
    return LocalSource(
        relative_path=relative_path,
        mime_type=None,
        source_format=fmt,
        size_bytes=10,
        sha256="abc",
        scanned_at=_NOW,
        supported=status not in (ProcessingStatus.UNSUPPORTED, ProcessingStatus.UNREADABLE),
        status=status,
    )


def _manifest(*sources: LocalSource) -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=list(sources),
    )


def test_unreadable_source_is_error() -> None:
    manifest = _manifest(
        _source("broken.pdf", SourceFormat.PDF, ProcessingStatus.UNREADABLE)
    )
    issues = check_manifest_coverage(manifest)
    assert len(issues) == 1
    assert issues[0].code is IssueCode.SOURCE_UNVERIFIED
    assert issues[0].severity is Severity.ERROR
    assert issues[0].location == "broken.pdf"


def test_unsupported_source_is_warning() -> None:
    manifest = _manifest(
        _source("logo.png", SourceFormat.UNKNOWN, ProcessingStatus.UNSUPPORTED)
    )
    issues = check_manifest_coverage(manifest)
    assert len(issues) == 1
    assert issues[0].code is IssueCode.SOURCE_UNVERIFIED
    assert issues[0].severity is Severity.WARNING
    assert issues[0].location == "logo.png"
    assert "unknown" in issues[0].evidence


def test_duplicate_source_is_not_surfaced() -> None:
    dup = _source("copy.md", SourceFormat.MARKDOWN, ProcessingStatus.DUPLICATE)
    dup.duplicate_of = "orig.md"
    assert check_manifest_coverage(_manifest(dup)) == []


def test_clean_manifest_has_no_coverage_issues() -> None:
    manifest = _manifest(
        _source("api.md", SourceFormat.MARKDOWN, ProcessingStatus.PENDING)
    )
    assert check_manifest_coverage(manifest) == []


def test_empty_manifest_has_no_coverage_issues() -> None:
    assert check_manifest_coverage(_manifest()) == []


def test_mixed_statuses_count_and_severity() -> None:
    manifest = _manifest(
        _source("broken.pdf", SourceFormat.PDF, ProcessingStatus.UNREADABLE),
        _source("logo.png", SourceFormat.UNKNOWN, ProcessingStatus.UNSUPPORTED),
        _source("copy.md", SourceFormat.MARKDOWN, ProcessingStatus.DUPLICATE),
        _source("api.md", SourceFormat.MARKDOWN, ProcessingStatus.PENDING),
    )
    issues = check_manifest_coverage(manifest)
    assert len(issues) == 2
    severities = {i.location: i.severity for i in issues}
    assert severities == {"broken.pdf": Severity.ERROR, "logo.png": Severity.WARNING}
    assert all(i.code is IssueCode.SOURCE_UNVERIFIED for i in issues)
```

- [ ] **Step 2: Run the tests to verify they FAIL**

Run: `uv run pytest tests/validate/test_coverage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.validate.coverage'` (the module does not exist yet).

- [ ] **Step 3: Create the coverage module**

Create `loop_apidoc/validate/coverage.py`:

```python
from __future__ import annotations

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import Issue, IssueCode, Severity


def check_manifest_coverage(manifest: Manifest) -> list[Issue]:
    """§6 來源涵蓋檢查：把無法納入規格化的本機來源浮現為 issue。

    - UNREADABLE 來源 → ERROR（讀取失敗、零資訊的 coverage gap）。
    - UNSUPPORTED 來源 → WARNING（格式不支援，浮現但不阻擋）。
    - DUPLICATE／PENDING 不浮現。

    issue code 一律用 SOURCE_UNVERIFIED；location 用來源 relative_path
    （§6 穩定來源識別碼）。修正循環會將之分類為 UNFIXABLE。
    """
    issues: list[Issue] = []
    for source in manifest.unreadable():
        issues.append(
            Issue(
                code=IssueCode.SOURCE_UNVERIFIED,
                severity=Severity.ERROR,
                location=source.relative_path,
                evidence="來源無法讀取，內容未納入驗證",
                suggested_fix="確認檔案可讀取後重新掃描",
            )
        )
    for source in manifest.unsupported():
        issues.append(
            Issue(
                code=IssueCode.SOURCE_UNVERIFIED,
                severity=Severity.WARNING,
                location=source.relative_path,
                evidence=f"來源格式不受支援（{source.source_format.value}），未納入規格化",
                suggested_fix="轉為受支援格式（PDF／Markdown／Word／OpenAPI）或確認可略過",
            )
        )
    return issues
```

- [ ] **Step 4: Run the tests to verify they PASS**

Run: `uv run pytest tests/validate/test_coverage.py -v`
Expected: PASS — all 6 tests.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/validate/coverage.py tests/validate/test_coverage.py
git commit -m "feat: [ validate ] add manifest-coverage check for unreadable/unsupported sources"
```

---

### Task 2: Wire coverage into `validate_outputs`

**Files:**
- Modify: `loop_apidoc/validate/validator.py` (imports, `validate_outputs` body + docstring)
- Test: `tests/validate/test_validator.py`

**Interfaces:**
- Consumes: `check_manifest_coverage(manifest: Manifest) -> list[Issue]` from Task 1
  (`loop_apidoc.validate.coverage`).
- `validate_outputs(plan, result, manifest) -> ValidationReport` keeps its signature;
  only its body and docstring change.

- [ ] **Step 1: Write the failing aggregation test**

Append to `tests/validate/test_validator.py` (the helpers `_good_plan`, `build_result`, `_NOW` and imports `LocalSource`, `Manifest`, `ProcessingStatus`, `SourceFormat` already exist in this file):

```python
def test_unreadable_source_makes_report_not_ok():
    plan = _good_plan()
    manifest = Manifest(
        sources_root="./sources", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="broken.pdf", mime_type=None,
            source_format=SourceFormat.PDF, size_bytes=10, sha256="abc",
            scanned_at=_NOW, supported=False, status=ProcessingStatus.UNREADABLE)])
    report = validate_outputs(plan, build_result(plan, _manifest()), manifest)
    assert report.ok is False
    unverified = [i for i in report.errors() if i.location == "broken.pdf"]
    assert len(unverified) == 1


def test_unsupported_source_warns_but_report_stays_ok():
    plan = _good_plan()
    manifest = Manifest(
        sources_root="./sources", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="logo.png", mime_type=None,
            source_format=SourceFormat.UNKNOWN, size_bytes=10, sha256="abc",
            scanned_at=_NOW, supported=False, status=ProcessingStatus.UNSUPPORTED)])
    report = validate_outputs(plan, build_result(plan, _manifest()), manifest)
    assert report.ok is True
    assert any(i.location == "logo.png" for i in report.warnings())
```

Note: `build_result(plan, _manifest())` is built from a clean manifest (the generator does not depend on coverage), while the manifest passed as the third `validate_outputs` argument carries the unreadable/unsupported source. This isolates the coverage check as the cause of the new issue.

- [ ] **Step 2: Run the new tests to verify they FAIL**

Run: `uv run pytest tests/validate/test_validator.py::test_unreadable_source_makes_report_not_ok tests/validate/test_validator.py::test_unsupported_source_warns_but_report_stays_ok -v`
Expected: both FAIL — `test_unreadable...` fails on `assert report.ok is False` (currently no coverage check, so report is ok); `test_unsupported...` fails on `assert any(... logo.png ...)` (no warning emitted yet).

- [ ] **Step 3: Wire `check_manifest_coverage` into `validate_outputs`**

In `loop_apidoc/validate/validator.py`, add the import alongside the other `from loop_apidoc.validate.*` imports:

```python
from loop_apidoc.validate.coverage import check_manifest_coverage
```

Then replace the `validate_outputs` function (docstring + body) with:

```python
def validate_outputs(
    plan: NormalizationPlan, result: GenerateResult, manifest: Manifest
) -> ValidationReport:
    """Aggregate the §9 validation categories plus §6 manifest coverage.
    Pure; the correction loop reuses this seam.

    Manifest coverage surfaces local sources that could not be incorporated
    into normalization: UNREADABLE sources as errors, UNSUPPORTED sources as
    warnings (see check_manifest_coverage).
    """
    issues = []
    issues += check_structure(result.openapi, result.markdown)
    issues += check_completeness(plan)
    issues += check_consistency(result.openapi, result.markdown)
    issues += check_speculation(result.openapi, result.provenance)
    issues += check_manifest_coverage(manifest)
    return ValidationReport(issues=issues)
```

- [ ] **Step 4: Run the new tests to verify they PASS**

Run: `uv run pytest tests/validate/test_validator.py::test_unreadable_source_makes_report_not_ok tests/validate/test_validator.py::test_unsupported_source_warns_but_report_stays_ok -v`
Expected: PASS.

- [ ] **Step 5: Run the full validate + integration suites for regressions**

Run: `uv run pytest tests/validate tests/integration -q`
Expected: PASS. In particular `tests/validate/test_validator.py::test_good_outputs_validate_clean` still passes — its `_manifest()` uses a single PENDING source, which produces no coverage issue. If any pre-existing test fails because its manifest fixture carries an UNREADABLE/UNSUPPORTED source while asserting zero issues, update that assertion to expect the new coverage issue (do not weaken unrelated assertions).

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS (baseline 203 passed + 1 skipped; count rises by the 8 added tests).

- [ ] **Step 7: Commit**

```bash
git add loop_apidoc/validate/validator.py tests/validate/test_validator.py
git commit -m "feat: [ validate ] surface manifest coverage gaps in validate_outputs"
```

---

## Post-Implementation: memory update

Not a code task — do this after Task 2 lands. Update the plan-sequence memory at
`/Users/carl/.claude/projects/-Users-carl-Dev-CMG-Loop-ApiDoc/memory/loop-apidoc-plan-sequence.md`:
edit Plan 6 deferral #2 to note manifest-coverage validation is implemented
(`check_manifest_coverage`: UNREADABLE→ERROR, UNSUPPORTED→WARNING, DUPLICATE not surfaced,
code=SOURCE_UNVERIFIED; both correction-loop and standalone `validate` paths covered),
leaving URL-source coverage as future work.

---

## Self-Review

**Spec coverage:**
- New `check_manifest_coverage` module → Task 1. ✓
- UNREADABLE→ERROR, UNSUPPORTED→WARNING, DUPLICATE/PENDING not surfaced → Task 1 Steps 1, 3. ✓
- code=SOURCE_UNVERIFIED, location=relative_path → Task 1 (asserted in tests + impl). ✓
- Wire into `validate_outputs` after the four checks + docstring rewrite → Task 2 Step 3. ✓
- Both paths (in-memory + `validate_run_dir`) covered → automatic via the single `validate_outputs` seam (no loader change), exercised by Task 2's `validate_outputs` tests. ✓
- Correction-loop interaction (UNFIXABLE → early-stop; WARNING never blocks) → guaranteed by reusing SOURCE_UNVERIFIED + WARNING severity; Task 2's `test_unsupported_source_warns_but_report_stays_ok` proves WARNING does not block. ✓
- Regression protection for clean manifests → Task 2 Step 5. ✓
- Memory deferral #2 update → Post-Implementation section. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; every run step has an exact command + expected outcome. ✓

**Type consistency:** `check_manifest_coverage(manifest) -> list[Issue]` identical in Task 1 (definition) and Task 2 (call). `Issue`/`IssueCode.SOURCE_UNVERIFIED`/`Severity.ERROR`/`Severity.WARNING`, `Manifest.unreadable()`/`unsupported()`, `LocalSource.relative_path`/`source_format.value` all match `loop_apidoc/manifest/models.py` and `loop_apidoc/validate/models.py`. Test helpers `_good_plan`, `build_result`, `_manifest`, `_NOW` and the `LocalSource`/`Manifest`/`ProcessingStatus`/`SourceFormat` imports already exist in `tests/validate/test_validator.py` (verified). ✓
