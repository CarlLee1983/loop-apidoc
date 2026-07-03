# URL Source Coverage Checking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make missing URL-source pages a visible, deterministic `warning`-level preparation finding instead of a silent gap.

**Architecture:** The extraction agent writes a machine-readable `url_sources/coverage.json` (an "expected vs. fetched" ledger) following a new fetching SOP; the deterministic CLI adds one new `preparation` phase that compares expectation against results and emits `warning` findings. The phase activates only when the run has URL sources. No `error`-level findings are added, so the existing severity gate (only `error` FAILs a run) is unchanged.

**Tech Stack:** Python 3.11+, pydantic v2, typer, pytest. Managed with `uv` (no `pip`).

## Global Constraints

- Python `>=3.11`; managed with `uv` — run everything via `uv run` (e.g. `uv run pytest`). No `pip`.
- Core invariant: sources are the only ground truth. This feature only *surfaces* gaps — it never fills or infers content.
- All new findings are `warning` severity only. Do **not** add any `error`-severity finding; the run-FAIL gate (`ValidationReport.ok` / any `error`) stays untouched.
- Fail loudly on a malformed `coverage.json` (missing key / unknown enum value / invalid JSON) — mirror the pydantic boundary-validation pattern in `loop_apidoc/agentcli/input_schema.py`, and fail *before* any run directory is created (no orphan run dir).
- Pure-function rule: only the existing I/O modules write files. New code in `loop_apidoc/preparation/coverage.py` may read one file (the loader); `assess.py` stays pure. Do not add file writes elsewhere.
- Product output stays `zh-TW`; the `SKILL.md` / `reference/*.md` skill files stay **English** (token economy). Code comments in Traditional Chinese are fine.
- The new preparation phase must NOT appear when a run has no URL sources — existing tests assert exactly 4 phases for local-only runs (`tests/preparation/test_report.py`).

---

## File Structure

- `loop_apidoc/preparation/coverage.py` **(new)** — pydantic models for `coverage.json` (`UrlCoverage` + nested), the status/source/method enums, `CoverageInputError`, and `load_coverage(path)` (the only file-reading function). Sole responsibility: parse + validate the agent-written coverage ledger, fail loud on malformed input.
- `loop_apidoc/preparation/assess.py` **(modify)** — add pure `_assess_url_coverage(manifest, coverage)` phase builder; extend `assess_preparation(...)` with an optional `url_coverage` parameter and append the phase when the run has URL sources.
- `loop_apidoc/preparation/__init__.py` **(modify)** — export the new public names.
- `loop_apidoc/agentcli/assemble.py` **(modify)** — accept `url_coverage_path`, load+validate it at the top (before run-dir creation), pass parsed coverage into `assess_preparation`.
- `loop_apidoc/cli.py` **(modify)** — add the `--url-coverage` option to the `assemble` command and thread it through.
- `skills/loop-apidoc/reference/url-fetching.md` **(new)** — the fetching SOP (discovery → confirm → fetch → report), empty-shell heuristics, auth-required handling, `coverage.json` schema.
- `skills/loop-apidoc/SKILL.md` **(modify)** — one orchestration-layer pointer to the new reference file + a note to pass `--url-coverage`.
- Tests: `tests/preparation/test_coverage.py` (new), `tests/preparation/test_url_coverage.py` (new), additions to `tests/test_cli_assemble.py`.

---

## Task 1: Coverage schema + loader

**Files:**
- Create: `loop_apidoc/preparation/coverage.py`
- Modify: `loop_apidoc/preparation/__init__.py`
- Test: `tests/preparation/test_coverage.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `class UrlCoverage(BaseModel)` with fields `entry_url: str`, `confirmed_by_user: bool = False`, `expected: list[CoverageExpected] = []`, `results: list[CoverageResult] = []`.
  - `class CoverageExpected(BaseModel)`: `url: str`, `title: str | None = None`, `source: ExpectedSource`.
  - `class CoverageResult(BaseModel)`: `url: str`, `status: ResultStatus`, `file: str | None = None`, `method: FetchMethod | None = None`.
  - `class ExpectedSource(str, Enum)`: `NAV="nav"`, `SITEMAP="sitemap"`, `USER="user"`.
  - `class ResultStatus(str, Enum)`: `FETCHED="fetched"`, `FETCHED_RENDERED="fetched_rendered"`, `EMPTY_SUSPECT="empty_suspect"`, `FETCH_FAILED="fetch_failed"`, `AUTH_REQUIRED="auth_required"`, `SKIPPED_BY_USER="skipped_by_user"`.
  - `class FetchMethod(str, Enum)`: `DEFUDDLE="defuddle"`, `PLAYWRIGHT="playwright"`.
  - `class CoverageInputError(Exception)`.
  - `def load_coverage(path: Path) -> UrlCoverage` — read + validate; raise `CoverageInputError` on unreadable file, invalid JSON, missing required key, or unknown enum value.

- [ ] **Step 1: Write the failing tests**

Create `tests/preparation/test_coverage.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from loop_apidoc.preparation.coverage import (
    CoverageInputError,
    ResultStatus,
    UrlCoverage,
    load_coverage,
)


def _valid_payload() -> dict:
    return {
        "entry_url": "https://docs.example.com/api/",
        "confirmed_by_user": True,
        "expected": [
            {"url": "https://docs.example.com/api/auth", "title": "驗證", "source": "nav"}
        ],
        "results": [
            {
                "url": "https://docs.example.com/api/auth",
                "status": "fetched",
                "file": "url_sources/auth.md",
                "method": "defuddle",
            }
        ],
    }


def _write(tmp_path: Path, data) -> Path:
    path = tmp_path / "coverage.json"
    path.write_text(
        data if isinstance(data, str) else json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_load_valid_coverage_round_trips(tmp_path):
    coverage = load_coverage(_write(tmp_path, _valid_payload()))
    assert isinstance(coverage, UrlCoverage)
    assert coverage.entry_url == "https://docs.example.com/api/"
    assert coverage.confirmed_by_user is True
    assert coverage.expected[0].source.value == "nav"
    assert coverage.results[0].status is ResultStatus.FETCHED


def test_confirmed_by_user_defaults_false_when_absent(tmp_path):
    payload = _valid_payload()
    del payload["confirmed_by_user"]
    coverage = load_coverage(_write(tmp_path, payload))
    assert coverage.confirmed_by_user is False


def test_load_rejects_unknown_status(tmp_path):
    payload = _valid_payload()
    payload["results"][0]["status"] = "totally_made_up"
    with pytest.raises(CoverageInputError):
        load_coverage(_write(tmp_path, payload))


def test_load_rejects_missing_entry_url(tmp_path):
    payload = _valid_payload()
    del payload["entry_url"]
    with pytest.raises(CoverageInputError):
        load_coverage(_write(tmp_path, payload))


def test_load_rejects_unknown_key(tmp_path):
    payload = _valid_payload()
    payload["results"][0]["bogus"] = 1
    with pytest.raises(CoverageInputError):
        load_coverage(_write(tmp_path, payload))


def test_load_rejects_invalid_json(tmp_path):
    with pytest.raises(CoverageInputError):
        load_coverage(_write(tmp_path, "{not json"))


def test_load_rejects_missing_file(tmp_path):
    with pytest.raises(CoverageInputError):
        load_coverage(tmp_path / "does-not-exist.json")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/preparation/test_coverage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'loop_apidoc.preparation.coverage'`.

- [ ] **Step 3: Write the implementation**

Create `loop_apidoc/preparation/coverage.py`:

```python
"""Load + validate the agent-written url_sources/coverage.json ledger.

This mirrors the pydantic boundary-validation pattern in
loop_apidoc/agentcli/input_schema.py: the agent writes coverage.json, and this
module fails loudly on a malformed ledger (missing key, unknown status, invalid
JSON) *before* the deterministic coverage phase runs — never silently accepting
a broken coverage report.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError


class CoverageInputError(Exception):
    """Raised when url_sources/coverage.json is unreadable or malformed."""


class ExpectedSource(str, Enum):
    NAV = "nav"
    SITEMAP = "sitemap"
    USER = "user"


class ResultStatus(str, Enum):
    FETCHED = "fetched"
    FETCHED_RENDERED = "fetched_rendered"
    EMPTY_SUSPECT = "empty_suspect"
    FETCH_FAILED = "fetch_failed"
    AUTH_REQUIRED = "auth_required"
    SKIPPED_BY_USER = "skipped_by_user"


class FetchMethod(str, Enum):
    DEFUDDLE = "defuddle"
    PLAYWRIGHT = "playwright"


class CoverageExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str | None = None
    source: ExpectedSource


class CoverageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    status: ResultStatus
    file: str | None = None
    method: FetchMethod | None = None


class UrlCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_url: str
    confirmed_by_user: bool = False
    expected: list[CoverageExpected] = []
    results: list[CoverageResult] = []


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(part) for part in err["loc"]) or "(root)"
    return f"{loc}: {err['msg']}"


def load_coverage(path: Path) -> UrlCoverage:
    """Read + validate coverage.json. Fail loud on any malformed input."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CoverageInputError(f"cannot read coverage file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CoverageInputError(f"coverage.json is not valid JSON: {exc}") from exc
    try:
        return UrlCoverage.model_validate(data)
    except ValidationError as exc:
        raise CoverageInputError(
            f"coverage.json schema error: {_first_error(exc)}"
        ) from exc
```

- [ ] **Step 4: Export the public names**

Edit `loop_apidoc/preparation/__init__.py` — add the coverage import and `__all__` entries. The file becomes:

```python
"""Pre-generation readiness checks for source-grounded API documentation runs."""

from loop_apidoc.preparation.assess import assess_preparation
from loop_apidoc.preparation.coverage import (
    CoverageInputError,
    UrlCoverage,
    load_coverage,
)
from loop_apidoc.preparation.models import (
    PreparationFinding,
    PreparationPhase,
    PreparationReport,
    PreparationSeverity,
    PreparationStatus,
)
from loop_apidoc.preparation.report import render_markdown, write_reports

__all__ = [
    "CoverageInputError",
    "PreparationFinding",
    "PreparationPhase",
    "PreparationReport",
    "PreparationSeverity",
    "PreparationStatus",
    "UrlCoverage",
    "assess_preparation",
    "load_coverage",
    "render_markdown",
    "write_reports",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/preparation/test_coverage.py -v`
Expected: PASS (7 passed).

- [ ] **Step 6: Lint**

Run: `uv run ruff check loop_apidoc/preparation/coverage.py loop_apidoc/preparation/__init__.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add loop_apidoc/preparation/coverage.py loop_apidoc/preparation/__init__.py tests/preparation/test_coverage.py
git commit -m "feat: [preparation] coverage.json schema + fail-loud loader"
```

---

## Task 2: URL coverage preparation phase

**Files:**
- Modify: `loop_apidoc/preparation/assess.py`
- Test: `tests/preparation/test_url_coverage.py`

**Interfaces:**
- Consumes: `UrlCoverage`, `ResultStatus` from `loop_apidoc.preparation.coverage` (Task 1). `Manifest` / `UrlSource` from `loop_apidoc.manifest.models`.
- Produces:
  - `def _assess_url_coverage(manifest: Manifest, coverage: UrlCoverage | None) -> PreparationPhase | None` — returns `None` when `manifest.url_sources` is empty; otherwise a phase with `id="url_coverage"`, `label="URL Coverage"`, all findings `warning`.
  - Extended `assess_preparation(*, manifest, inventory, endpoint_texts, plan, url_coverage: UrlCoverage | None = None) -> PreparationReport` — appends the url-coverage phase only when it is not `None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/preparation/test_url_coverage.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import Manifest, UrlSource
from loop_apidoc.plan.models import IntegrationContract, NormalizationPlan
from loop_apidoc.preparation import assess_preparation
from loop_apidoc.preparation.coverage import UrlCoverage

_NOW = datetime(2026, 7, 3, 8, 0, tzinfo=timezone.utc)


def _manifest_with_urls() -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        url_sources=[
            UrlSource(url="https://docs.example.com/api/", fetched_at=_NOW, http_status=200)
        ],
    )


def _manifest_local_only() -> Manifest:
    return Manifest(sources_root="./sources", generated_at=_NOW)


def _inventory() -> dict:
    return {"title": "Demo", "endpoints": [{"method": "GET", "path": "/ping"}], "missing": []}


def _endpoint() -> str:
    import json
    return json.dumps({"method": "GET", "path": "/ping", "responses": [], "missing": []})


def _plan() -> NormalizationPlan:
    return NormalizationPlan(notebook_url="", integration=IntegrationContract())


def _assess(manifest, coverage):
    return assess_preparation(
        manifest=manifest,
        inventory=_inventory(),
        endpoint_texts=[_endpoint()],
        plan=_plan(),
        url_coverage=coverage,
    )


def _url_phase(report):
    return next((p for p in report.phases if p.id == "url_coverage"), None)


def test_phase_absent_when_no_url_sources():
    report = _assess(_manifest_local_only(), None)
    assert _url_phase(report) is None
    assert [p.id for p in report.phases] == [
        "sources", "extraction", "normalization_plan", "integration_contract",
    ]


def test_full_coverage_has_phase_but_no_findings():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[{"url": "https://docs.example.com/api/auth", "source": "nav"}],
        results=[{"url": "https://docs.example.com/api/auth", "status": "fetched",
                  "file": "url_sources/auth.md", "method": "defuddle"}],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    assert phase is not None
    assert phase.findings == []


def test_missing_coverage_file_warns():
    phase = _url_phase(_assess(_manifest_with_urls(), None))
    assert phase is not None
    assert len(phase.findings) == 1
    assert phase.findings[0].severity.value == "warning"
    assert "coverage.json" in phase.findings[0].summary


def test_fetch_failed_and_empty_suspect_warn():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[
            {"url": "https://docs.example.com/api/a", "source": "nav"},
            {"url": "https://docs.example.com/api/b", "source": "nav"},
        ],
        results=[
            {"url": "https://docs.example.com/api/a", "status": "fetch_failed"},
            {"url": "https://docs.example.com/api/b", "status": "empty_suspect",
             "file": "url_sources/b.md", "method": "playwright"},
        ],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    summaries = " || ".join(f.summary for f in phase.findings)
    assert "https://docs.example.com/api/a" in summaries
    assert "https://docs.example.com/api/b" in summaries
    assert all(f.severity.value == "warning" for f in phase.findings)


def test_auth_required_without_file_warns_but_with_file_is_clean():
    with_file = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[{"url": "https://docs.example.com/api/secure", "source": "nav"}],
        results=[{"url": "https://docs.example.com/api/secure", "status": "auth_required",
                  "file": "secure.pdf"}],
    )
    assert _url_phase(_assess(_manifest_with_urls(), with_file)).findings == []

    without_file = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[{"url": "https://docs.example.com/api/secure", "source": "nav"}],
        results=[{"url": "https://docs.example.com/api/secure", "status": "auth_required"}],
    )
    findings = _url_phase(_assess(_manifest_with_urls(), without_file)).findings
    assert len(findings) == 1
    assert "secure" in findings[0].summary


def test_expected_page_never_fetched_warns():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[
            {"url": "https://docs.example.com/api/seen", "source": "nav"},
            {"url": "https://docs.example.com/api/ghost", "source": "nav"},
        ],
        results=[{"url": "https://docs.example.com/api/seen", "status": "fetched",
                  "file": "url_sources/seen.md", "method": "defuddle"}],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    assert any("ghost" in f.summary for f in phase.findings)
    assert phase.metrics["not_fetched"] == 1


def test_unconfirmed_list_warns():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=False,
        expected=[{"url": "https://docs.example.com/api/auth", "source": "nav"}],
        results=[{"url": "https://docs.example.com/api/auth", "status": "fetched",
                  "file": "url_sources/auth.md", "method": "defuddle"}],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    assert any("confirm" in f.summary.lower() for f in phase.findings)


def test_skipped_by_user_is_not_a_finding():
    coverage = UrlCoverage(
        entry_url="https://docs.example.com/api/",
        confirmed_by_user=True,
        expected=[{"url": "https://docs.example.com/api/legacy", "source": "nav"}],
        results=[{"url": "https://docs.example.com/api/legacy", "status": "skipped_by_user"}],
    )
    phase = _url_phase(_assess(_manifest_with_urls(), coverage))
    assert phase.findings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/preparation/test_url_coverage.py -v`
Expected: FAIL — `assess_preparation()` got an unexpected keyword argument `url_coverage` (or `AttributeError`/no `url_coverage` phase).

- [ ] **Step 3: Add the imports and phase builder to `assess.py`**

Edit `loop_apidoc/preparation/assess.py`. Extend the manifest import (line 6) and add the coverage import beneath it:

```python
from loop_apidoc.manifest.models import Manifest, ProcessingStatus
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.preparation.coverage import ResultStatus, UrlCoverage
```

Then add this pure function directly above `def assess_preparation(` (after `_assess_integration`):

```python
def _assess_url_coverage(
    manifest: Manifest, coverage: UrlCoverage | None
) -> PreparationPhase | None:
    """比對「應抓 vs 實抓」的 URL 涵蓋率。僅在 run 有 URL 來源時啟用;
    全為 warning——遺漏是誠實回報的缺口,不擋 pipeline,但必須看得見。"""
    if not manifest.url_sources:
        return None

    findings: list[PreparationFinding] = []

    if coverage is None:
        findings.append(
            _finding(
                PreparationSeverity.WARNING,
                "url_sources/coverage.json is missing; URL coverage is unknown",
                "Follow reference/url-fetching.md, write url_sources/coverage.json, "
                "and pass it to assemble via --url-coverage.",
                target_file="url_sources/coverage.json",
            )
        )
        return _phase(
            "url_coverage",
            "URL Coverage",
            {
                "url_sources": len(manifest.url_sources),
                "expected": 0,
                "fetched": 0,
                "fetch_failed": 0,
                "empty_suspect": 0,
                "auth_required": 0,
                "not_fetched": 0,
            },
            findings,
        )

    if not coverage.confirmed_by_user:
        findings.append(
            _finding(
                PreparationSeverity.WARNING,
                "expected URL list was not confirmed by a human",
                "Review the discovered page list with the user, or accept it as "
                "machine-discovered only.",
                target_file="url_sources/coverage.json",
                field_path="/confirmed_by_user",
            )
        )

    fetched = fetch_failed = empty_suspect = auth_required = 0
    for result in coverage.results:
        if result.status in (ResultStatus.FETCHED, ResultStatus.FETCHED_RENDERED):
            fetched += 1
        elif result.status is ResultStatus.FETCH_FAILED:
            fetch_failed += 1
            findings.append(
                _finding(
                    PreparationSeverity.WARNING,
                    f"URL fetch failed: {result.url}",
                    "Re-fetch the page; if it is a JS SPA, render it with Playwright "
                    "before saving.",
                    evidence=result.url,
                    target_file="url_sources/coverage.json",
                )
            )
        elif result.status is ResultStatus.EMPTY_SUSPECT:
            empty_suspect += 1
            findings.append(
                _finding(
                    PreparationSeverity.WARNING,
                    f"URL fetched but looks empty: {result.url}",
                    "Re-fetch with Playwright rendering; do not fill the gap with "
                    "inferred content.",
                    evidence=result.url,
                    target_file="url_sources/coverage.json",
                )
            )
        elif result.status is ResultStatus.AUTH_REQUIRED:
            auth_required += 1
            if result.file is None:
                findings.append(
                    _finding(
                        PreparationSeverity.WARNING,
                        f"URL requires login and has no local alternative: {result.url}",
                        "Log in manually, save the page (HTML/PDF) into the local "
                        "sources, and reference it in results[].file.",
                        evidence=result.url,
                        target_file="url_sources/coverage.json",
                    )
                )
        # ResultStatus.SKIPPED_BY_USER → intentional drop, no finding.

    fetched_urls = {result.url for result in coverage.results}
    not_fetched = 0
    for expected in coverage.expected:
        if expected.url not in fetched_urls:
            not_fetched += 1
            findings.append(
                _finding(
                    PreparationSeverity.WARNING,
                    f"expected URL was never fetched: {expected.url}",
                    "Fetch the page per reference/url-fetching.md, or mark it "
                    "skipped_by_user if intentionally dropped.",
                    evidence=expected.url,
                    target_file="url_sources/coverage.json",
                )
            )

    return _phase(
        "url_coverage",
        "URL Coverage",
        {
            "url_sources": len(manifest.url_sources),
            "expected": len(coverage.expected),
            "fetched": fetched,
            "fetch_failed": fetch_failed,
            "empty_suspect": empty_suspect,
            "auth_required": auth_required,
            "not_fetched": not_fetched,
        },
        findings,
    )
```

- [ ] **Step 4: Wire the phase into `assess_preparation`**

Edit `loop_apidoc/preparation/assess.py` — replace the `assess_preparation` function (currently lines 301-318) with:

```python
def assess_preparation(
    *,
    manifest: Manifest,
    inventory: dict,
    endpoint_texts: list[str],
    plan: NormalizationPlan,
    url_coverage: UrlCoverage | None = None,
) -> PreparationReport:
    phases = [
        _assess_sources(manifest),
        _assess_extraction(inventory, endpoint_texts),
        _assess_plan(plan),
        _assess_integration(plan),
    ]
    url_phase = _assess_url_coverage(manifest, url_coverage)
    if url_phase is not None:
        phases.append(url_phase)
    return PreparationReport(
        status=_overall_status(phases),
        summary=_summary(phases),
        phases=phases,
    )
```

- [ ] **Step 5: Run the new + existing preparation tests**

Run: `uv run pytest tests/preparation/ -v`
Expected: PASS — new `test_url_coverage.py` tests pass AND the existing `test_report.py` (which asserts exactly 4 phases / `{"ready": 4}` for local-only runs) still passes, because the phase is skipped when there are no URL sources.

- [ ] **Step 6: Lint**

Run: `uv run ruff check loop_apidoc/preparation/assess.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add loop_apidoc/preparation/assess.py tests/preparation/test_url_coverage.py
git commit -m "feat: [preparation] URL coverage phase (warning-level omission checks)"
```

---

## Task 3: Wire coverage into assemble + CLI

**Files:**
- Modify: `loop_apidoc/agentcli/assemble.py:116-158`
- Modify: `loop_apidoc/cli.py:202-261`
- Test: `tests/test_cli_assemble.py`

**Interfaces:**
- Consumes: `load_coverage`, `CoverageInputError` from `loop_apidoc.preparation.coverage` (Task 1); the `url_coverage` parameter of `assess_preparation` (Task 2); the existing `AssembleInputError` in `assemble.py`.
- Produces:
  - `run_assemble_pipeline(..., url_coverage_path: Path | None = None)` — loads + validates coverage before creating the run dir; a malformed/unreadable coverage raises `AssembleInputError` (→ CLI exit 2, no orphan run dir).
  - CLI `assemble --url-coverage PATH` option threaded to `url_coverage_path`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli_assemble.py` (append at end; reuses the module's `_setup`, `runner`, `app`):

```python
def _coverage_payload() -> dict:
    return {
        "entry_url": "https://docs.example.com/api/",
        "confirmed_by_user": True,
        "expected": [
            {"url": "https://docs.example.com/api/ping", "title": "Ping", "source": "nav"}
        ],
        "results": [
            {"url": "https://docs.example.com/api/ping", "status": "fetched",
             "file": "url_sources/ping.md", "method": "defuddle"}
        ],
    }


def test_assemble_with_url_coverage_adds_phase(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps(_coverage_payload()), encoding="utf-8")
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--url", "https://docs.example.com/api/",
        "--url-coverage", str(coverage), "--json",
    ])
    assert res.exit_code in (0, 1)
    run_dir = Path(json.loads(res.stdout)["run_dir"])
    prep = json.loads((run_dir / "preparation-report.json").read_text(encoding="utf-8"))
    assert any(phase["id"] == "url_coverage" for phase in prep["phases"])


def test_assemble_malformed_coverage_exits_2_without_run_dir(tmp_path):
    sources, extraction, out = _setup(tmp_path)
    coverage = tmp_path / "coverage.json"
    coverage.write_text('{"results": [{"status": "bogus"}]}', encoding="utf-8")
    res = runner.invoke(app, [
        "assemble", "--sources", str(sources), "--extraction", str(extraction),
        "--output", str(out), "--url", "https://docs.example.com/api/",
        "--url-coverage", str(coverage),
    ])
    assert res.exit_code == 2
    # fail-loud before any run dir is created
    assert not out.exists() or not any(out.iterdir())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_assemble.py::test_assemble_with_url_coverage_adds_phase tests/test_cli_assemble.py::test_assemble_malformed_coverage_exits_2_without_run_dir -v`
Expected: FAIL — `No such option: --url-coverage`.

- [ ] **Step 3: Thread `url_coverage_path` through `run_assemble_pipeline`**

Edit `loop_apidoc/agentcli/assemble.py`. Add the coverage import near the other preparation import (line 23 area) — find `from loop_apidoc.preparation import assess_preparation` and add below it:

```python
from loop_apidoc.preparation.coverage import CoverageInputError, load_coverage
```

Add the parameter to the signature (after `urls`):

```python
def run_assemble_pipeline(
    *,
    sources_root: Path,
    extraction_dir: Path,
    output_root: Path,
    run_id: str,
    generated_at: datetime,
    urls: list[str] | None = None,
    url_coverage_path: Path | None = None,
) -> RunResult:
```

Load coverage at the top of the body, right after `load_extraction_inputs(...)` and before the run-dir creation (so a malformed ledger fails loud with no orphan dir):

```python
    inventory, endpoint_texts, integration = load_extraction_inputs(extraction_dir)
    url_coverage = None
    if url_coverage_path is not None:
        try:
            url_coverage = load_coverage(url_coverage_path)
        except CoverageInputError as exc:
            raise AssembleInputError(str(exc)) from exc
```

Pass it into `assess_preparation`:

```python
    preparation_report = assess_preparation(
        manifest=manifest,
        inventory=inventory,
        endpoint_texts=endpoint_texts,
        plan=plan,
        url_coverage=url_coverage,
    )
```

- [ ] **Step 4: Add the `--url-coverage` CLI option**

Edit `loop_apidoc/cli.py`. In the `assemble` command signature, add an option right after the `url` option (line 215):

```python
    url_coverage: Path = typer.Option(
        None, "--url-coverage",
        help="agent 產出的 url_sources/coverage.json 路徑;有 URL 來源時檢核撈取涵蓋率",
    ),
```

Then pass it into the call (in the `run_assemble_pipeline(...)` invocation, after `urls=list(url),`):

```python
        result = run_assemble_pipeline(
            sources_root=sources,
            extraction_dir=extraction,
            output_root=output,
            run_id=make_run_id(now),
            generated_at=now,
            urls=list(url),
            url_coverage_path=url_coverage,
        )
```

(The existing `except AssembleInputError` block already maps this to exit code 2 — no new except needed.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_assemble.py -v`
Expected: PASS — the two new tests pass and all existing assemble tests still pass.

- [ ] **Step 6: Lint**

Run: `uv run ruff check loop_apidoc/agentcli/assemble.py loop_apidoc/cli.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add loop_apidoc/agentcli/assemble.py loop_apidoc/cli.py tests/test_cli_assemble.py
git commit -m "feat: [assemble] --url-coverage option feeds URL coverage phase"
```

---

## Task 4: URL fetching SOP + SKILL pointer

**Files:**
- Create: `skills/loop-apidoc/reference/url-fetching.md`
- Modify: `skills/loop-apidoc/SKILL.md`

**Interfaces:**
- Consumes: the `coverage.json` schema realized in Task 1 (`UrlCoverage`), the CLI `--url-coverage` flag from Task 3. The SOP text must match those exactly (status/source/method enum values, the flag name).
- Produces: skill guidance only — no code. Validated in the next real e2e (§7 of the spec).

- [ ] **Step 1: Write the SOP reference file**

Create `skills/loop-apidoc/reference/url-fetching.md`:

````markdown
# URL fetching SOP (coverage-checked)

Use this when any source is a public URL. The goal is not "how to fetch" but
**"how to know you fetched everything"**: make omissions visible as checkable
findings, matching the pipeline's fail-closed spirit. Write the result to
`<WORK>/url_sources/coverage.json` and pass it to assemble via `--url-coverage`.

## 1. Discovery

1. Fetch the entry page. If it is a JS SPA shell (see §5), render it with the
   Playwright MCP first, then parse.
2. Treat the **navigation tree (sidebar / menu) as the authoritative "should-fetch"
   list** — every page it lists should be fetched; do not chase links outside it
   (avoids unbounded crawl).
3. If the site exposes `sitemap.xml`, cross-check the entry-path subtree against the
   nav tree to catch gaps. If there is none, do not force it.

## 2. Confirm (human in the loop)

Before fetching, show the should-fetch list (page title + URL + level) to the user
to add/remove. Pages the user removes are recorded as `skipped_by_user`. In
non-interactive contexts (e.g. CI), skip confirmation, use the discovered list as-is,
and set `confirmed_by_user: false` in coverage.json.

## 3. Fetch

- Fetch each page with defuddle-cli first (saves tokens). On an empty-shell hit or
  suspiciously short body → upgrade to Playwright rendering and re-fetch.
- Save each page under `<WORK>/url_sources/` and record the method (`defuddle` /
  `playwright`) and result status.
- If it is still a shell after re-fetch → keep the `empty_suspect` status. **Never**
  fill it with inferred content.

## 4. Report (coverage)

After fetching, write `<WORK>/url_sources/coverage.json` (schema in §6). Then run
assemble with `--url-coverage "<WORK>/url_sources/coverage.json"`. The preparation
stage compares expected vs. results and emits `warning`-level findings for gaps
(fetch failures, empty shells, unfetched expected pages, auth-required pages without
a local alternative, an unconfirmed list, or a missing coverage.json).

## 5. Empty-shell heuristics

Any one hit → treat as a suspected shell and re-fetch with rendering:

- Main-body word count (after stripping nav/footer) below threshold.
- Page is only a loading/skeleton marker or an empty `<div id="root">`-style container.
- Body length is wildly out of proportion to the `<title>` / nav-menu scale.

## 6. Login-gated resources

Security red line: **the pipeline and the agent never handle or record credentials.**

- **Interactive session**: open a real browser with the Playwright MCP and have the
  **user log in by hand** (including 2FA); then, in the same session, fetch the
  confirmed list page by page.
- **Non-interactive, or login too complex** (enterprise SSO, device binding): mark the
  page `auth_required`; the user logs in themselves and saves the page (HTML/PDF) into
  the local sources, which the pipeline treats as an ordinary local file. Reference
  that saved file in `results[].file` so the coverage check counts it as covered.
- No credential automation (env token / cookie injection) — YAGNI.

## 7. coverage.json schema

```json
{
  "entry_url": "https://docs.example.com/api/",
  "confirmed_by_user": true,
  "expected": [
    { "url": "https://docs.example.com/api/auth", "title": "驗證", "source": "nav" }
  ],
  "results": [
    {
      "url": "https://docs.example.com/api/auth",
      "status": "fetched",
      "file": "url_sources/auth.md",
      "method": "defuddle"
    }
  ]
}
```

- `expected[].source`: `nav` | `sitemap` | `user`
- `results[].status`: `fetched` | `fetched_rendered` | `empty_suspect` | `fetch_failed` |
  `auth_required` | `skipped_by_user`
- `results[].method`: `defuddle` | `playwright`
  (`auth_required` / `fetch_failed` / `skipped_by_user` may omit `file` / `method`).

A malformed coverage.json (missing key, unknown status) fails assemble loudly (exit 2).
````

- [ ] **Step 2: Add the reference pointer in SKILL.md (reference list)**

Edit `skills/loop-apidoc/SKILL.md`. After the `reference/assemble-and-correction.md` bullet (lines 17-18), add a third bullet:

```markdown
- **`reference/url-fetching.md`** — the coverage-checked URL fetching SOP + `coverage.json`
  schema (load when any source is a public URL, before fetching).
```

- [ ] **Step 3: Update the "Public URLs" fetch line in SKILL.md**

Edit `skills/loop-apidoc/SKILL.md`. Replace the existing `- **Public URLs** →` bullet (lines 71-73) with:

```markdown
- **Public URLs** → follow **`reference/url-fetching.md`** (discover → confirm → fetch →
  report). Save readable text/HTML/Markdown under `<WORK>/url_sources/`, point subagents
  there (no re-fetching), and write `<WORK>/url_sources/coverage.json`. Pass the original
  URLs to `manifest`/`assemble` via `--url` and the coverage file via
  `--url-coverage "<WORK>/url_sources/coverage.json"`. Cite the original URL + anchor.
```

- [ ] **Step 4: Verify the skill files are internally consistent**

Run: `grep -n "url-fetching\|url-coverage\|coverage.json" skills/loop-apidoc/SKILL.md skills/loop-apidoc/reference/url-fetching.md`
Expected: the SKILL.md references resolve to the new file; the flag name `--url-coverage` and the enum values match Tasks 1/3 exactly.

- [ ] **Step 5: Commit**

```bash
git add skills/loop-apidoc/reference/url-fetching.md skills/loop-apidoc/SKILL.md
git commit -m "docs: [skill] coverage-checked URL fetching SOP + SKILL pointer"
```

---

## Final Verification

- [ ] **Run the full test suite**

Run: `uv run pytest`
Expected: all tests pass (existing suite + new coverage/url-coverage/assemble tests).

- [ ] **Lint the whole change**

Run: `uv run ruff check .`
Expected: no errors.

---

## Spec Coverage Map

| Spec section | Task |
| --- | --- |
| §3 fetching SOP (discovery/confirm/fetch/report/heuristics/auth) | Task 4 (`reference/url-fetching.md`) |
| §4 `coverage.json` schema | Task 1 (pydantic models) + Task 4 (documented) |
| §5 preparation URL-coverage phase (4 warning rows) + `not_fetched` silent-omission check | Task 2 |
| §5 phase only when URL sources present; no error findings; severity gate unchanged | Task 2 (returns `None` for local-only) |
| §6 out of scope (no credential automation, no crawler, no in-CLI browser) | honored — rendering stays agent-side via Playwright MCP; loader is read-only |
| §7 tests: phase state combinations | Task 2 tests |
| §7 tests: coverage.json boundary fails loud | Task 1 tests |
| §7 SOP e2e human validation | noted in Task 4 (post-merge e2e, not automatable here) |
| §2 assemble reads coverage.json deterministically | Task 3 (`--url-coverage` wiring) |
