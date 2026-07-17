# Batch Freshness Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `check-freshness-batch` — run the freshness gate over many docsets from a watchlist file and emit one aggregated report with a deterministic 0/1/2 exit code.

**Architecture:** Extend the existing `loop_apidoc/freshness/` package. A new `batch.py` loads a `freshness-watchlist.json` (fail-loud) and fans the existing `check_freshness` over each item (per-item errors captured, not fatal), aggregating into a `BatchReport`. `report.py` gains a batch renderer/writer; one new CLI command drives it.

**Tech Stack:** Python ≥3.11, uv, pydantic v2, httpx, typer, pytest.

## Global Constraints

- Python `>=3.11`, `uv` (no pip). Tests: `uv run pytest`. Lint: `uv run ruff check .`.
- Never fabricate: an item that cannot be checked is `error`/`inconclusive`, never `unchanged`.
- Pure functions except the designated write exits. `batch.py` writes nothing; only `report.py`'s new `write_batch_reports` writes.
- pydantic models use `model_config = ConfigDict(extra="forbid")`.
- Reuse `check_freshness(fingerprint, *, sources_root=None, client=None, max_bytes=...)` unchanged — do NOT reimplement signal/compare logic.
- Watchlist relative paths resolve against the **watchlist file's own directory**.
- Aggregate verdict → exit code via the EXISTING `EXIT_CODES` map: any item `changed`→`changed`/1; else any `inconclusive`/`error`→`inconclusive`/2; else `unchanged`/0.
- Product strings zh-TW; code identifiers/plan English.
- Tests inject `httpx.Client(transport=httpx.MockTransport(...))`; no real network.

## Existing interfaces this plan builds on (already shipped in 0.12.0)

- `loop_apidoc/freshness/models.py`: `FreshnessVerdict` (`unchanged`/`changed`/`inconclusive`), `FreshnessInputError`, `EXIT_CODES: dict[FreshnessVerdict, int]`, `SourceFingerprint`, `SourceResult` (has `.id`, `.reason`), `FreshnessReport` (has `.verdict`, `.openapi_version`, `.changed: list[SourceResult]`, `.inconclusive: list[SourceResult]`).
- `loop_apidoc/freshness/check.py`: `check_freshness(fingerprint, *, sources_root=None, client=None, max_bytes=...) -> FreshnessReport`.
- `loop_apidoc/freshness/report.py`: `render_markdown`, `write_reports`.

---

## File Structure

- Modify `loop_apidoc/freshness/models.py` — add watchlist + batch-report models.
- Create `loop_apidoc/freshness/batch.py` — `load_watchlist` + `scan_watchlist`.
- Modify `loop_apidoc/freshness/report.py` — add `render_batch_markdown` + `write_batch_reports`.
- Modify `loop_apidoc/cli.py` — add `check-freshness-batch` command.
- Create `tests/test_freshness_batch.py`, `tests/test_freshness_batch_report.py`, `tests/test_cli_freshness_batch.py`.
- Modify `skills/loop-apidoc/reference/freshness-scheduling.md`, `CLAUDE.md`, `AGENTS.md`, `README.md`, `README.en.md`, `docs/operator-manual.html`.

---

## Task 1: Watchlist + batch-report models

**Files:**
- Modify: `loop_apidoc/freshness/models.py` (append after `EXIT_CODES`)
- Test: `tests/test_freshness_batch_models.py`

**Interfaces:**
- Consumes: `FreshnessVerdict` (existing).
- Produces:
  - `class WatchlistItem(BaseModel)`: `label: str`, `fingerprint: str`, `sources: str | None = None`, `run_dir: str | None = None`.
  - `class Watchlist(BaseModel)`: `schema_version: int = 1`, `items: list[WatchlistItem] = []`.
  - `class BatchItemStatus(str, Enum)`: `UNCHANGED="unchanged"`, `CHANGED="changed"`, `INCONCLUSIVE="inconclusive"`, `ERROR="error"`.
  - `class BatchItemResult(BaseModel)`: `label: str`, `status: BatchItemStatus`, `openapi_version: str | None = None`, `reason: str | None = None`, `run_dir: str | None = None`.
  - `class BatchReport(BaseModel)`: `verdict: FreshnessVerdict`, `total: int`, `changed_count: int`, `attention_count: int`, `unchanged_count: int`, `items: list[BatchItemResult] = []`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_freshness_batch_models.py
import pytest
from pydantic import ValidationError

from loop_apidoc.freshness.models import (
    BatchItemResult,
    BatchItemStatus,
    BatchReport,
    FreshnessVerdict,
    Watchlist,
    WatchlistItem,
)


def test_watchlist_roundtrip_and_optional_fields():
    wl = Watchlist(items=[
        WatchlistItem(label="a", fingerprint="a/fp.json", sources="a/src", run_dir="out/a"),
        WatchlistItem(label="b", fingerprint="b/fp.json"),
    ])
    assert wl.schema_version == 1
    restored = Watchlist.model_validate_json(wl.model_dump_json())
    assert restored == wl
    assert restored.items[1].sources is None


def test_watchlist_item_forbids_extra():
    with pytest.raises(ValidationError):
        WatchlistItem.model_validate({"label": "a", "fingerprint": "f", "bogus": 1})


def test_batch_report_shape():
    r = BatchReport(
        verdict=FreshnessVerdict.CHANGED, total=2, changed_count=1,
        attention_count=0, unchanged_count=1,
        items=[BatchItemResult(label="a", status=BatchItemStatus.CHANGED, reason="version 1 -> 2")],
    )
    assert r.items[0].status is BatchItemStatus.CHANGED
    assert BatchItemStatus.ERROR.value == "error"
    assert BatchReport.model_validate_json(r.model_dump_json()) == r
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_freshness_batch_models.py -v`
Expected: FAIL — `cannot import name 'Watchlist'`.

- [ ] **Step 3: Write minimal implementation**

Append to `loop_apidoc/freshness/models.py`:

```python
class WatchlistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    fingerprint: str
    sources: str | None = None
    run_dir: str | None = None


class Watchlist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    items: list[WatchlistItem] = Field(default_factory=list)


class BatchItemStatus(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"


class BatchItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    status: BatchItemStatus
    openapi_version: str | None = None
    reason: str | None = None
    run_dir: str | None = None


class BatchReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: FreshnessVerdict
    total: int
    changed_count: int
    attention_count: int
    unchanged_count: int
    items: list[BatchItemResult] = Field(default_factory=list)
```

(`BaseModel`, `ConfigDict`, `Field`, `Enum`, and `FreshnessVerdict` are already imported/defined in this file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_freshness_batch_models.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/freshness/models.py tests/test_freshness_batch_models.py
git commit -m "feat: watchlist and batch-report models"
```

---

## Task 2: load_watchlist + scan_watchlist

**Files:**
- Create: `loop_apidoc/freshness/batch.py`
- Test: `tests/test_freshness_batch.py`

**Interfaces:**
- Consumes: `Watchlist`, `WatchlistItem`, `BatchItemResult`, `BatchItemStatus`, `BatchReport`, `FreshnessVerdict`, `FreshnessInputError`, `SourceFingerprint` (models); `check_freshness` (check).
- Produces:
  - `def load_watchlist(path: Path) -> Watchlist` — reads + validates the watchlist JSON; raises `FreshnessInputError` on unreadable file, invalid JSON, or schema violation.
  - `def scan_watchlist(watchlist: Watchlist, *, base_dir: Path, client: httpx.Client | None = None, max_bytes: int = 5 * 1024 * 1024) -> BatchReport` — for each item: resolve `fingerprint`/`sources` relative to `base_dir`, load the fingerprint, run `check_freshness`, map to a `BatchItemResult`. Any per-item exception (`FreshnessInputError`, `OSError`, `ValueError`) → `BatchItemResult(status=ERROR, reason=...)`, scan continues. Creates/closes one shared `httpx.Client` only when `client is None` and the watchlist has at least one item. Aggregates the verdict per the exit-code rule.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_freshness_batch.py
import json
from pathlib import Path

import httpx

from loop_apidoc.freshness.models import (
    BatchItemStatus,
    FreshnessVerdict,
    SourceFingerprint,
    Watchlist,
    WatchlistItem,
)
from loop_apidoc.freshness.batch import load_watchlist, scan_watchlist
from loop_apidoc.freshness.signals import hash_bytes


def _local_fp_file(dir_: Path, name: str, sha: str) -> Path:
    fp = SourceFingerprint(
        openapi_version="1.0.0",
        sources=[{"id": "spec.pdf", "kind": "local_file", "signal": {"sha256": sha}}],
    )
    p = dir_ / name
    p.write_text(fp.model_dump_json(indent=2), encoding="utf-8")
    return p


def _write_watchlist(dir_: Path, items: list[dict]) -> Path:
    p = dir_ / "freshness-watchlist.json"
    p.write_text(json.dumps({"schema_version": 1, "items": items}), encoding="utf-8")
    return p


def test_load_watchlist_fail_loud(tmp_path: Path):
    import pytest
    from loop_apidoc.freshness.models import FreshnessInputError
    with pytest.raises(FreshnessInputError):
        load_watchlist(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"; bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(FreshnessInputError):
        load_watchlist(bad)


def test_scan_all_unchanged(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir(); (src / "spec.pdf").write_bytes(b"hello")
    _local_fp_file(tmp_path, "a.json", hash_bytes(b"hello"))
    wl = Watchlist(items=[WatchlistItem(label="a", fingerprint="a.json", sources="src")])
    report = scan_watchlist(wl, base_dir=tmp_path)
    assert report.verdict is FreshnessVerdict.UNCHANGED
    assert report.total == 1 and report.unchanged_count == 1
    assert report.items[0].status is BatchItemStatus.UNCHANGED


def test_scan_one_changed_is_1(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir(); (src / "spec.pdf").write_bytes(b"NEW")
    _local_fp_file(tmp_path, "a.json", hash_bytes(b"hello"))
    wl = Watchlist(items=[WatchlistItem(label="a", fingerprint="a.json", sources="src")])
    report = scan_watchlist(wl, base_dir=tmp_path)
    assert report.verdict is FreshnessVerdict.CHANGED
    assert report.changed_count == 1
    assert "hash changed" in (report.items[0].reason or "")


def test_scan_missing_fingerprint_is_error_and_2(tmp_path: Path):
    wl = Watchlist(items=[WatchlistItem(label="ghost", fingerprint="nope.json")])
    report = scan_watchlist(wl, base_dir=tmp_path)
    assert report.items[0].status is BatchItemStatus.ERROR
    assert report.verdict is FreshnessVerdict.INCONCLUSIVE  # error aggregates to inconclusive
    assert report.attention_count == 1


def test_scan_changed_dominates_error(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir(); (src / "spec.pdf").write_bytes(b"NEW")
    _local_fp_file(tmp_path, "a.json", hash_bytes(b"hello"))
    wl = Watchlist(items=[
        WatchlistItem(label="a", fingerprint="a.json", sources="src"),
        WatchlistItem(label="ghost", fingerprint="nope.json"),
    ])
    report = scan_watchlist(wl, base_dir=tmp_path)
    assert report.verdict is FreshnessVerdict.CHANGED  # changed dominates
    assert report.changed_count == 1 and report.attention_count == 1


def test_scan_relative_paths_resolved_against_base_dir(tmp_path: Path):
    sub = tmp_path / "watch"; sub.mkdir()
    src = sub / "src"; src.mkdir(); (src / "spec.pdf").write_bytes(b"hello")
    _local_fp_file(sub, "a.json", hash_bytes(b"hello"))
    wl = Watchlist(items=[WatchlistItem(label="a", fingerprint="a.json", sources="src")])
    report = scan_watchlist(wl, base_dir=sub)
    assert report.items[0].status is BatchItemStatus.UNCHANGED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_freshness_batch.py -v`
Expected: FAIL — `ModuleNotFoundError: loop_apidoc.freshness.batch`.

- [ ] **Step 3: Write minimal implementation**

```python
# loop_apidoc/freshness/batch.py
from __future__ import annotations

import json
from pathlib import Path

import httpx
from pydantic import ValidationError

from loop_apidoc.freshness.check import check_freshness
from loop_apidoc.freshness.models import (
    BatchItemResult,
    BatchItemStatus,
    BatchReport,
    FreshnessInputError,
    FreshnessReport,
    FreshnessVerdict,
    SourceFingerprint,
    Watchlist,
    WatchlistItem,
)

_VERDICT_TO_STATUS = {
    FreshnessVerdict.UNCHANGED: BatchItemStatus.UNCHANGED,
    FreshnessVerdict.CHANGED: BatchItemStatus.CHANGED,
    FreshnessVerdict.INCONCLUSIVE: BatchItemStatus.INCONCLUSIVE,
}


def load_watchlist(path: Path) -> Watchlist:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FreshnessInputError(f"cannot read watchlist {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FreshnessInputError(f"watchlist is not valid JSON: {exc}") from exc
    try:
        return Watchlist.model_validate(data)
    except ValidationError as exc:
        raise FreshnessInputError(f"watchlist schema error: {exc}") from exc


def _summarize(report: FreshnessReport) -> str | None:
    flagged = report.changed + report.inconclusive
    if not flagged:
        return None
    return "; ".join(f"{r.id}: {r.reason}" for r in flagged if r.reason) or None


def _scan_item(item: WatchlistItem, base_dir: Path, client: httpx.Client, max_bytes: int) -> BatchItemResult:
    try:
        fp_path = base_dir / item.fingerprint
        fingerprint = SourceFingerprint.model_validate_json(fp_path.read_text(encoding="utf-8"))
        sources_root = (base_dir / item.sources) if item.sources else None
        report = check_freshness(fingerprint, sources_root=sources_root, client=client, max_bytes=max_bytes)
    except (FreshnessInputError, OSError, ValueError) as exc:
        return BatchItemResult(label=item.label, status=BatchItemStatus.ERROR, reason=str(exc), run_dir=item.run_dir)
    return BatchItemResult(
        label=item.label,
        status=_VERDICT_TO_STATUS[report.verdict],
        openapi_version=report.openapi_version,
        reason=_summarize(report),
        run_dir=item.run_dir,
    )


def scan_watchlist(
    watchlist: Watchlist,
    *,
    base_dir: Path,
    client: httpx.Client | None = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> BatchReport:
    active_client = client
    owns_client = False
    if active_client is None and watchlist.items:
        active_client = httpx.Client(timeout=20, follow_redirects=True, trust_env=False)
        owns_client = True

    results: list[BatchItemResult] = []
    try:
        for item in watchlist.items:
            results.append(_scan_item(item, base_dir, active_client, max_bytes))
    finally:
        if owns_client and active_client is not None:
            active_client.close()

    changed = sum(1 for r in results if r.status is BatchItemStatus.CHANGED)
    unchanged = sum(1 for r in results if r.status is BatchItemStatus.UNCHANGED)
    attention = sum(1 for r in results if r.status in (BatchItemStatus.INCONCLUSIVE, BatchItemStatus.ERROR))
    if changed:
        verdict = FreshnessVerdict.CHANGED
    elif attention:
        verdict = FreshnessVerdict.INCONCLUSIVE
    else:
        verdict = FreshnessVerdict.UNCHANGED

    return BatchReport(
        verdict=verdict,
        total=len(results),
        changed_count=changed,
        attention_count=attention,
        unchanged_count=unchanged,
        items=results,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_freshness_batch.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/freshness/batch.py tests/test_freshness_batch.py
git commit -m "feat: load and scan a freshness watchlist"
```

---

## Task 3: Batch report rendering

**Files:**
- Modify: `loop_apidoc/freshness/report.py` (append)
- Test: `tests/test_freshness_batch_report.py`

**Interfaces:**
- Consumes: `BatchReport`, `BatchItemResult`.
- Produces:
  - `def render_batch_markdown(report: BatchReport) -> str` — zh-TW headline (verdict + totals) + a table `| label | 判定 | OpenAPI 版本 | 摘要/原因 |`.
  - `def write_batch_reports(report: BatchReport, report_dir: Path) -> tuple[Path, Path]` — writes `freshness-scan.json` and `freshness-scan.md`, returns their paths, creates `report_dir` if missing.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_freshness_batch_report.py
from pathlib import Path

from loop_apidoc.freshness.models import (
    BatchItemResult,
    BatchItemStatus,
    BatchReport,
    FreshnessVerdict,
)
from loop_apidoc.freshness.report import render_batch_markdown, write_batch_reports


def _report():
    return BatchReport(
        verdict=FreshnessVerdict.CHANGED, total=2, changed_count=1, attention_count=1, unchanged_count=0,
        items=[
            BatchItemResult(label="stripe", status=BatchItemStatus.CHANGED, openapi_version="1.0.0",
                            reason="https://api/x: version 1.0.0 -> 2.0.0"),
            BatchItemResult(label="ghost", status=BatchItemStatus.ERROR, reason="fingerprint not found"),
        ],
    )


def test_render_batch_markdown_lists_items_and_reasons():
    md = render_batch_markdown(_report())
    assert "changed" in md
    assert "stripe" in md and "ghost" in md
    assert "version 1.0.0 -> 2.0.0" in md


def test_write_batch_reports(tmp_path: Path):
    j, m = write_batch_reports(_report(), tmp_path)
    assert j.name == "freshness-scan.json" and m.name == "freshness-scan.md"
    assert '"verdict": "changed"' in j.read_text(encoding="utf-8")
    assert m.read_text(encoding="utf-8").startswith("#")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_freshness_batch_report.py -v`
Expected: FAIL — `cannot import name 'render_batch_markdown'`.

- [ ] **Step 3: Write minimal implementation**

Append to `loop_apidoc/freshness/report.py` (add `BatchItemResult`, `BatchReport` to the existing `from loop_apidoc.freshness.models import ...` line):

```python
def _batch_rows(items: list[BatchItemResult]) -> list[str]:
    return [
        f"| {i.label} | {i.status.value} | `{i.openapi_version or '-'}` | {i.reason or '-'} |"
        for i in items
    ]


def render_batch_markdown(report: BatchReport) -> str:
    lines = [
        "# 來源新鮮度批次巡檢",
        "",
        f"- 判定:**{report.verdict.value}**",
        f"- 來源總數:{report.total};變動:{report.changed_count};"
        f"需注意(無法判定/錯誤):{report.attention_count};未變:{report.unchanged_count}",
    ]
    if report.items:
        lines += [
            "",
            "| 項目 | 判定 | OpenAPI 版本 | 摘要/原因 |",
            "| --- | --- | --- | --- |",
            *_batch_rows(report.items),
        ]
    return "\n".join(lines) + "\n"


def write_batch_reports(report: BatchReport, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "freshness-scan.json"
    md_path = report_dir / "freshness-scan.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_batch_markdown(report), encoding="utf-8")
    return (json_path, md_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_freshness_batch_report.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/freshness/report.py tests/test_freshness_batch_report.py
git commit -m "feat: batch freshness scan report rendering"
```

---

## Task 4: CLI `check-freshness-batch`

**Files:**
- Modify: `loop_apidoc/cli.py` (add after the `check-freshness` command)
- Test: `tests/test_cli_freshness_batch.py`

**Interfaces:**
- Consumes: `load_watchlist`, `scan_watchlist` (batch), `render_batch_markdown`, `write_batch_reports` (report), `EXIT_CODES`, `FreshnessInputError` (models).
- Produces one Typer command: `check-freshness-batch --watchlist <path> [--json] [--report-dir <dir>]` — loads the watchlist (fail-loud → exit 2), scans (base_dir = the watchlist file's parent), optionally writes reports, prints `model_dump_json(indent=2)` when `--json` else `render_batch_markdown`, then `raise typer.Exit(code=EXIT_CODES[report.verdict])`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_freshness_batch.py
import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.freshness.models import SourceFingerprint
from loop_apidoc.freshness.signals import hash_bytes

runner = CliRunner()


def _setup(tmp_path: Path, body: bytes, baseline_sha: str) -> Path:
    src = tmp_path / "src"; src.mkdir(); (src / "spec.pdf").write_bytes(body)
    fp = SourceFingerprint(openapi_version="1.0.0",
                           sources=[{"id": "spec.pdf", "kind": "local_file", "signal": {"sha256": baseline_sha}}])
    (tmp_path / "a.json").write_text(fp.model_dump_json(), encoding="utf-8")
    wl = tmp_path / "freshness-watchlist.json"
    wl.write_text(json.dumps({"schema_version": 1,
                              "items": [{"label": "a", "fingerprint": "a.json", "sources": "src"}]}),
                  encoding="utf-8")
    return wl


def test_batch_unchanged_exit_0(tmp_path: Path):
    wl = _setup(tmp_path, b"hello", hash_bytes(b"hello"))
    res = runner.invoke(app, ["check-freshness-batch", "--watchlist", str(wl), "--json"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["verdict"] == "unchanged"


def test_batch_changed_exit_1(tmp_path: Path):
    wl = _setup(tmp_path, b"NEW", hash_bytes(b"hello"))
    res = runner.invoke(app, ["check-freshness-batch", "--watchlist", str(wl)])
    assert res.exit_code == 1


def test_batch_error_item_exit_2(tmp_path: Path):
    wl = tmp_path / "freshness-watchlist.json"
    wl.write_text(json.dumps({"schema_version": 1, "items": [{"label": "ghost", "fingerprint": "nope.json"}]}),
                  encoding="utf-8")
    res = runner.invoke(app, ["check-freshness-batch", "--watchlist", str(wl)])
    assert res.exit_code == 2


def test_batch_bad_watchlist_exit_2(tmp_path: Path):
    wl = tmp_path / "wl.json"; wl.write_text("{not json", encoding="utf-8")
    res = runner.invoke(app, ["check-freshness-batch", "--watchlist", str(wl)])
    assert res.exit_code == 2


def test_batch_report_dir_writes_files(tmp_path: Path):
    wl = _setup(tmp_path, b"hello", hash_bytes(b"hello"))
    rd = tmp_path / "out"
    res = runner.invoke(app, ["check-freshness-batch", "--watchlist", str(wl), "--report-dir", str(rd)])
    assert res.exit_code == 0
    assert (rd / "freshness-scan.json").exists() and (rd / "freshness-scan.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_freshness_batch.py -v`
Expected: FAIL — no such command `check-freshness-batch`.

- [ ] **Step 3: Write minimal implementation**

Add to `loop_apidoc/cli.py` after the `check-freshness` command (imports local to the function body, matching the file's style):

```python
@app.command(name="check-freshness-batch")
def check_freshness_batch_command(
    watchlist: Path = typer.Option(..., "--watchlist", exists=True, readable=True, help="巡檢清單 freshness-watchlist.json"),
    json_output: bool = typer.Option(False, "--json", help="輸出機器可讀 JSON"),
    report_dir: Path | None = typer.Option(None, "--report-dir", help="另存 freshness-scan.{json,md}"),
) -> None:
    """對巡檢清單逐項比對來源新鮮度,彙總成一份報表(退出碼 0/1/2)。"""
    from loop_apidoc.freshness.batch import load_watchlist, scan_watchlist
    from loop_apidoc.freshness.models import EXIT_CODES, FreshnessInputError
    from loop_apidoc.freshness.report import render_batch_markdown, write_batch_reports

    try:
        loaded = load_watchlist(watchlist)
    except FreshnessInputError as exc:
        typer.echo(f"check-freshness-batch error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    report = scan_watchlist(loaded, base_dir=watchlist.parent)

    if report_dir is not None:
        write_batch_reports(report, report_dir)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_batch_markdown(report))
    raise typer.Exit(code=EXIT_CODES[report.verdict])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_freshness_batch.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the full suite + lint**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/cli.py tests/test_cli_freshness_batch.py
git commit -m "feat: check-freshness-batch CLI command"
```

---

## Task 5: Skill + example docs for the batch scan

**Files:**
- Modify: `skills/loop-apidoc/reference/freshness-scheduling.md`
- Modify: `examples/freshness-scheduling/README.md`

**Interfaces:**
- Consumes: nothing (documentation).
- Produces: a batch-scan section in the skill reference + a note in the example README.

- [ ] **Step 1: Add a batch-scan section to the skill reference**

In `skills/loop-apidoc/reference/freshness-scheduling.md`, before the `## v1 limits` section, add a `## Batch scan (many docsets)` section documenting:
- The purpose: one scheduled pass over many docsets → one aggregated report.
- The watchlist file shape (`freshness-watchlist.json` with `items[]` of `label`/`fingerprint`/optional `sources`/`run_dir`; relative paths resolve against the watchlist's directory).
- The command: `<APIDOC> check-freshness-batch --watchlist <path> [--json] [--report-dir <dir>]`.
- The aggregate exit-code contract: `0` all unchanged; `1` any changed → re-run those; `2` any inconclusive/error → alert. Per-item errors don't abort the batch (recorded as `error`), but a malformed watchlist file fails loud.

- [ ] **Step 2: Note the batch mode in the example README**

In `examples/freshness-scheduling/README.md`, add a short paragraph pointing to `check-freshness-batch` for the many-docsets case (a single watchlist instead of one cron line per docset), with a one-line command example.

- [ ] **Step 3: Verify consistency**

Run: `rg -n "check-freshness-batch|freshness-watchlist" skills/loop-apidoc/ examples/`
Expected: the command and the watchlist filename appear in both the skill reference and the example README.

- [ ] **Step 4: Commit**

```bash
git add skills/loop-apidoc/reference/freshness-scheduling.md examples/freshness-scheduling/README.md
git commit -m "docs: document check-freshness-batch in skill and example"
```

---

## Task 6: Sync teaching & promotion docs (release policy)

**Files:**
- Modify: `CLAUDE.md`, `AGENTS.md`, `README.md`, `README.en.md`, `docs/operator-manual.html`

**Interfaces:**
- Consumes: nothing (documentation).
- Produces: docs consistent with the new `check-freshness-batch` command + `freshness/batch.py`.

- [ ] **Step 1: Update `CLAUDE.md`**

- In the `loop_apidoc/freshness/` package-table row, add `batch.py` (`load_watchlist` + `scan_watchlist` — fan `check_freshness` over a watchlist, per-item errors captured; writes nothing) and note `report.py` also writes `freshness-scan.{json,md}`.
- In the two-groups command paragraph (Source acquisition & quality), add `check-freshness-batch` next to `check-freshness` with a one-line description + the aggregate 0/1/2 contract.
- The File-I/O exits paragraph already names `freshness/report.py` as a write exit — confirm it still reads correctly (it now writes two report kinds); adjust wording only if needed.

- [ ] **Step 2: Mirror into `AGENTS.md`**

Apply the equivalent additions so `AGENTS.md` stays aligned with `CLAUDE.md`.

- [ ] **Step 3: Update `README.md` (zh-TW) and `README.en.md` (English)**

Add `check-freshness-batch` to the command list/table with a one-line purpose (batch watchlist scan → one report, aggregate exit code). Match each file's language and format.

- [ ] **Step 4: Update `docs/operator-manual.html`**

In the freshness-gate subsection (added in 0.12.0), add the batch command: the watchlist shape, the command, and the aggregate exit-code contract. Bump the top-level command count sentence (was 17 → now 18). Match surrounding HTML.

- [ ] **Step 5: Verify + full suite**

Run: `uv run pytest -q && rg -n "check-freshness-batch" CLAUDE.md AGENTS.md README.md README.en.md docs/operator-manual.html`
Expected: tests pass; the command appears in every listed doc.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md AGENTS.md README.md README.en.md docs/operator-manual.html
git commit -m "docs: document check-freshness-batch command"
```

---

## Release note (out of plan scope)

The version bump is a separate release action (`scripts/release.py prepare` on a clean
worktree — temporarily move `runs/`, `tmp/`, `.loop-apidoc/` — then `tag`). Task 6 covers the
human-facing docs the script does not touch. This feature adds one backward-compatible
command ⇒ a minor bump (0.12.0 → 0.13.0).

---

## Self-Review

- **Spec coverage:** watchlist schema (Task 1 models) ✓; `load_watchlist` fail-loud + `scan_watchlist` per-item-error + aggregation (Task 2) ✓; report render/write `freshness-scan.{json,md}` (Task 3) ✓; CLI `check-freshness-batch` + exit codes (Task 4) ✓; relative-path-against-watchlist-dir (Task 2 test + Task 4 `base_dir=watchlist.parent`) ✓; reuse of `check_freshness` unchanged (Task 2) ✓; skill/example + teaching docs (Tasks 5–6) ✓; follow-ups (Foundry enumeration, auto-rerun, parallelism) left out of scope ✓.
- **Placeholder scan:** every code step carries complete code; doc tasks enumerate exact required content.
- **Type consistency:** `Watchlist`/`WatchlistItem`/`BatchItemStatus`/`BatchItemResult`/`BatchReport`/`load_watchlist`/`scan_watchlist`/`render_batch_markdown`/`write_batch_reports` used with identical names/signatures across tasks; reuses existing `check_freshness`/`EXIT_CODES`/`FreshnessVerdict`/`SourceFingerprint`/`FreshnessInputError` verbatim.
