# sole_source URL + 快照檔摺疊 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓「照 URL 抓取 SOP 走的 run」(快照檔 + entry URL 被算成兩份文件)在有 coverage 帳本映射時把 URL 摺疊回其本地快照檔,恢復 `sole_source` 單一文件歸屬,消除假陰性的 `SOURCE_UNVERIFIED` FAIL。

**Architecture:** coverage.json 帳本的 `results[].file` 提供 URL→本地檔的明確映射。`run_assemble_pipeline` 在建 manifest 之後、建 plan 之前,用一個純函式 `backfill_snapshot_files` 把映射回填到 `manifest.url_sources[].snapshot_file`(唯一命中才配對,零/多重命中維持 None)。`classify.sole_source` 的「文件數」定義改為:可用本地來源 + 其 `snapshot_file` 未指向可用本地來源的 URL——摺疊後恰好一份文件時,回傳本地檔的 `relative_path`。`match_manifest_source` 的嚴格比對完全不動。

**Tech Stack:** Python 3.11+、pydantic v2、pytest、uv。

## Global Constraints

- Python `>=3.11`,以 `uv` 管理(禁用 `pip`);測試 `uv run pytest`,lint `uv run ruff check .`。
- 核心不變式:來源文件是唯一真相;本設計**不**新增任何推論/啟發式摺疊——無帳本 → 完全維持現狀。
- 不改驗證閘(severity 決定 FAIL)、不改 warning-only 的 `url_coverage` preparation phase、不改 `match_manifest_source` 的嚴格比對。
- 純函式優先:除既有 I/O 模組外一律回傳新值(immutable);`backfill_snapshot_files` / `sole_source` / `normalize_url` 皆為純函式。
- 配對失敗(路徑對不上、模糊、多重命中)一律靜默維持 `None`——配對是歸屬優化,不是輸入錯誤,寧可不摺疊也不誤配;不新增錯誤路徑。
- 舊 `manifest.json` 讀回不受影響(`snapshot_file` 預設 `None`)。

---

## File Structure

| File | 變更 | 責任 |
| --- | --- | --- |
| `loop_apidoc/preparation/coverage.py` | Modify | 新增公開純函式 `normalize_url`(自 `assess.py` 的私有 `_normalize_url` 提升,兩處共用) |
| `loop_apidoc/preparation/assess.py` | Modify | 移除私有 `_normalize_url`,改 import 使用 `coverage.normalize_url`(零行為變更) |
| `loop_apidoc/manifest/models.py` | Modify | `UrlSource` 加 optional `snapshot_file: str \| None = None` |
| `loop_apidoc/agentcli/assemble.py` | Modify | 新增純函式 `backfill_snapshot_files` + `_ledger_file_matches` 輔助;在 `run_assemble_pipeline` 中接線(build_manifest 後、寫 manifest.json 前) |
| `loop_apidoc/plan/classify.py` | Modify | `sole_source` 文件數定義改為摺疊 snapshot 對應 URL |
| `tests/preparation/test_coverage.py` | Modify | `normalize_url` 單元測試 |
| `tests/agentcli/test_assemble.py` | Modify | `backfill_snapshot_files` 單元測試 + 接線寫入 manifest.json 測試 |
| `tests/plan/test_classify.py` | Modify | `sole_source` 摺疊行為單元測試 |
| `tests/agentcli/test_snapshot_collapse.py` | Create | plan 層整合測試(line-pay 形狀:摺疊後不再 UNVERIFIED,無帳本維持現狀) |

---

## Task 1: 提升 `normalize_url` 為共用純函式

把 `assess.py` 私有的 `_normalize_url` 上移到 `coverage.py` 成為公開 `normalize_url`,讓 backfill 與 URL 涵蓋檢核共用同一份 URL 正規化實作,避免重複。

**Files:**
- Modify: `loop_apidoc/preparation/coverage.py`
- Modify: `loop_apidoc/preparation/assess.py:302-304` (移除 `_normalize_url` 定義)、`:397`、`:401`(改用 import 的 `normalize_url`)
- Test: `tests/preparation/test_coverage.py`

**Interfaces:**
- Produces: `normalize_url(url: str) -> str`(定義於 `loop_apidoc/preparation/coverage.py`)——去除 fragment(`#` 之後)與尾斜線;供 Task 3 的 backfill 與既有 `assess._assess_url_coverage` 共用。

- [ ] **Step 1: 寫失敗測試**

在 `tests/preparation/test_coverage.py` 的既有 import 區塊加入 `normalize_url`,並在檔案末端新增:

```python
from loop_apidoc.preparation.coverage import normalize_url


def test_normalize_url_strips_fragment_and_trailing_slash():
    assert normalize_url("https://a.example/doc/") == "https://a.example/doc"
    assert normalize_url("https://a.example/doc#sec-2") == "https://a.example/doc"
    assert normalize_url("https://a.example/doc/#top") == "https://a.example/doc"
    # 同頁異寫正規化後相等
    assert normalize_url("https://a.example/p/") == normalize_url("https://a.example/p#x")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/preparation/test_coverage.py::test_normalize_url_strips_fragment_and_trailing_slash -v`
Expected: FAIL,`ImportError: cannot import name 'normalize_url'`

- [ ] **Step 3: 在 coverage.py 新增 `normalize_url`**

在 `loop_apidoc/preparation/coverage.py` 的 `load_coverage` 之前(或 `_first_error` 之後)新增:

```python
def normalize_url(url: str) -> str:
    """比對用正規化:去除 fragment 與尾斜線,同頁異寫不誤報/不誤配。"""
    return url.split("#", 1)[0].rstrip("/")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/preparation/test_coverage.py::test_normalize_url_strips_fragment_and_trailing_slash -v`
Expected: PASS

- [ ] **Step 5: 讓 assess.py 改用共用函式**

在 `loop_apidoc/preparation/assess.py` 的 import 區(既有 `from loop_apidoc.preparation.coverage import ResultStatus, UrlCoverage`)改為:

```python
from loop_apidoc.preparation.coverage import ResultStatus, UrlCoverage, normalize_url
```

刪除 `assess.py:302-304` 的私有定義:

```python
def _normalize_url(url: str) -> str:
    """比對用正規化:去除 fragment 與尾斜線,同頁異寫不誤報未爬取。"""
    return url.split("#", 1)[0].rstrip("/")
```

把 `_assess_url_coverage` 內兩處 `_normalize_url(...)` 改為 `normalize_url(...)`:

```python
    fetched_urls = {normalize_url(result.url) for result in coverage.results}
```
```python
        key = normalize_url(expected.url)
```

- [ ] **Step 6: 跑既有涵蓋測試確認零行為變更**

Run: `uv run pytest tests/preparation/ -v`
Expected: 全 PASS(既有 `test_url_coverage.py` 不變)

- [ ] **Step 7: Commit**

```bash
git add loop_apidoc/preparation/coverage.py loop_apidoc/preparation/assess.py tests/preparation/test_coverage.py
git commit -m "refactor: [preparation] promote normalize_url to shared coverage helper"
```

---

## Task 2: `UrlSource` 加 `snapshot_file` 欄位

Additive schema 變更:讓 URL 來源可記錄它對應的本地快照檔 `relative_path`。

**Files:**
- Modify: `loop_apidoc/manifest/models.py:37-42`
- Test: `tests/manifest/`(以下新增檔或就近檔)

**Interfaces:**
- Produces: `UrlSource.snapshot_file: str | None`(預設 `None`)——Task 3 寫入、Task 5 讀取。

- [ ] **Step 1: 寫失敗測試**

新建 `tests/manifest/test_url_source_snapshot.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import UrlSource


def test_url_source_snapshot_file_defaults_none():
    src = UrlSource(url="https://a.example/doc", fetched_at=datetime(2026, 7, 4, tzinfo=timezone.utc), http_status=200)
    assert src.snapshot_file is None


def test_url_source_snapshot_file_roundtrip():
    src = UrlSource(
        url="https://a.example/doc",
        fetched_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
        http_status=200,
        snapshot_file="overview.md",
    )
    assert src.snapshot_file == "overview.md"
    # 舊 JSON(無此欄位)讀回仍為 None
    reloaded = UrlSource.model_validate_json(
        '{"url":"https://a.example/doc","fetched_at":"2026-07-04T00:00:00Z","http_status":200}'
    )
    assert reloaded.snapshot_file is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/manifest/test_url_source_snapshot.py -v`
Expected: FAIL,`TypeError`/`ValidationError`(未知欄位 `snapshot_file`)

- [ ] **Step 3: 加欄位**

在 `loop_apidoc/manifest/models.py` 的 `UrlSource` 加最後一行:

```python
class UrlSource(BaseModel):
    url: str
    fetched_at: datetime
    http_status: int | None
    content_sha256: str | None = None
    note: str | None = None
    snapshot_file: str | None = None  # 該 URL 快照對應的本地來源 relative_path
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/manifest/test_url_source_snapshot.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/manifest/models.py tests/manifest/test_url_source_snapshot.py
git commit -m "feat: [manifest] add optional UrlSource.snapshot_file for URL→snapshot mapping"
```

---

## Task 3: `backfill_snapshot_files` 純函式

在 `assemble.py` 新增一個純函式:吃 manifest + coverage 帳本,回傳一個 `url_sources[].snapshot_file` 已回填的**新** Manifest。唯一命中才配對。

**Files:**
- Modify: `loop_apidoc/agentcli/assemble.py`(新增 `_ledger_file_matches` + `_MAPPING_STATUSES` + `backfill_snapshot_files`;擴充既有 coverage import)
- Test: `tests/agentcli/test_assemble.py`

**Interfaces:**
- Consumes: `Manifest`(Task 2 的 `UrlSource.snapshot_file`)、`UrlCoverage` / `ResultStatus`(`loop_apidoc/preparation/coverage.py`)、`normalize_url`(Task 1)。
- Produces: `backfill_snapshot_files(manifest: Manifest, coverage: UrlCoverage) -> Manifest`——Task 4 在 pipeline 中呼叫。

- [ ] **Step 1: 寫失敗測試**

在 `tests/agentcli/test_assemble.py` 末端新增(先補 import,見 Step 3 的最終 import 形狀):

```python
from datetime import datetime, timezone

from loop_apidoc.agentcli.assemble import backfill_snapshot_files
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
)
from loop_apidoc.preparation.coverage import (
    CoverageResult,
    FetchMethod,
    ResultStatus,
    UrlCoverage,
)

_NOW = datetime(2026, 7, 4, tzinfo=timezone.utc)


def _local(rel: str) -> LocalSource:
    return LocalSource(
        relative_path=rel, mime_type="text/markdown", source_format=SourceFormat.MARKDOWN,
        size_bytes=1, sha256="x", scanned_at=_NOW, supported=True,
        status=ProcessingStatus.PENDING,
    )


def _url(url: str) -> UrlSource:
    return UrlSource(url=url, fetched_at=_NOW, http_status=200)


def _manifest(locals_, urls) -> Manifest:
    return Manifest(sources_root="/src", generated_at=_NOW,
                    local_sources=locals_, url_sources=urls)


def _coverage(results) -> UrlCoverage:
    return UrlCoverage(entry_url="https://a.example/", results=results)


def test_backfill_unique_suffix_match_sets_snapshot_file():
    manifest = _manifest([_local("overview.md")], [_url("https://a.example/overview")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview/", status=ResultStatus.FETCHED,
                       file="sources/overview.md", method=FetchMethod.DEFUDDLE),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file == "overview.md"
    # 純函式:原 manifest 不被就地修改
    assert manifest.url_sources[0].snapshot_file is None


def test_backfill_normalizes_url_before_match():
    manifest = _manifest([_local("overview.md")], [_url("https://a.example/overview#top")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview", status=ResultStatus.FETCHED_RENDERED,
                       file="sources/overview.md"),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file == "overview.md"


def test_backfill_auth_required_with_file_maps():
    manifest = _manifest([_local("overview.md")], [_url("https://a.example/overview")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview", status=ResultStatus.AUTH_REQUIRED,
                       file="sources/overview.md"),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file == "overview.md"


def test_backfill_result_without_file_leaves_none():
    manifest = _manifest([_local("overview.md")], [_url("https://a.example/overview")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview", status=ResultStatus.FETCH_FAILED,
                       file=None),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file is None


def test_backfill_zero_match_leaves_none():
    manifest = _manifest([_local("overview.md")], [_url("https://a.example/other")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview", status=ResultStatus.FETCHED,
                       file="sources/overview.md"),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file is None


def test_backfill_ambiguous_suffix_leaves_none():
    # 帳本 file 後綴同時命中兩個本地檔 → 多重命中 → None
    manifest = _manifest(
        [_local("overview.md"), _local("docs/overview.md")],
        [_url("https://a.example/overview")],
    )
    coverage = _coverage([
        CoverageResult(url="https://a.example/overview", status=ResultStatus.FETCHED,
                       file="sources/docs/overview.md"),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    # "sources/docs/overview.md" 後綴命中 "docs/overview.md" 與 "overview.md" 兩者 → 模糊
    assert out.url_sources[0].snapshot_file is None


def test_backfill_multiple_results_to_different_files_leaves_none():
    manifest = _manifest([_local("a.md"), _local("b.md")], [_url("https://a.example/p")])
    coverage = _coverage([
        CoverageResult(url="https://a.example/p", status=ResultStatus.FETCHED, file="sources/a.md"),
        CoverageResult(url="https://a.example/p", status=ResultStatus.FETCHED, file="sources/b.md"),
    ])
    out = backfill_snapshot_files(manifest, coverage)
    assert out.url_sources[0].snapshot_file is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/agentcli/test_assemble.py -k backfill -v`
Expected: FAIL,`ImportError: cannot import name 'backfill_snapshot_files'`

- [ ] **Step 3: 實作純函式**

在 `loop_apidoc/agentcli/assemble.py`,先擴充既有 import:

```python
from loop_apidoc.manifest.models import Manifest, UrlSource
from loop_apidoc.preparation import assess_preparation
from loop_apidoc.preparation import write_reports as write_preparation_reports
from loop_apidoc.preparation.coverage import (
    CoverageInputError,
    ResultStatus,
    UrlCoverage,
    load_coverage,
    normalize_url,
)
```

(既有 `from loop_apidoc.manifest.builder import build_manifest` 保留;既有的 `from loop_apidoc.preparation.coverage import CoverageInputError, load_coverage` 整行以上面擴充版取代。)

在 `RunDirectoryCollisionError` 類別之後、`load_extraction_inputs` 之前新增:

```python
# 只有帶 file 且成功抓到/需登入(仍留了本地檔)的 result 提供 URL→本地檔映射。
_MAPPING_STATUSES = (
    ResultStatus.FETCHED,
    ResultStatus.FETCHED_RENDERED,
    ResultStatus.AUTH_REQUIRED,
)


def _ledger_file_matches(ledger_file: str, relative_path: str) -> bool:
    """帳本 file(相對 work dir,如 sources/overview.md)以 `/` 為界、
    以某本地來源 relative_path(相對 sources_root)結尾即命中。"""
    return ledger_file == relative_path or ledger_file.endswith("/" + relative_path)


def backfill_snapshot_files(manifest: Manifest, coverage: UrlCoverage) -> Manifest:
    """把 coverage 帳本 results[].file 的 URL→本地檔映射回填到
    manifest.url_sources[].snapshot_file,回傳新的 Manifest(純函式,不就地修改)。

    - URL 比對用 normalize_url(去 fragment/尾斜線)。
    - 只有帶 file 且 status ∈ fetched/fetched_rendered/auth_required 的 result 提供映射。
    - 帳本 file 對本地 relative_path 採路徑後綴匹配。
    - 須唯一命中才配對;零命中或多重命中(含多個 result 映到不同檔)→ 維持 None,不誤配。
    """
    local_paths = [s.relative_path for s in manifest.local_sources]
    updated: list[UrlSource] = []
    for url_source in manifest.url_sources:
        key = normalize_url(url_source.url)
        candidates: set[str] = set()
        for result in coverage.results:
            if result.file is None or result.status not in _MAPPING_STATUSES:
                continue
            if normalize_url(result.url) != key:
                continue
            for rel in local_paths:
                if _ledger_file_matches(result.file, rel):
                    candidates.add(rel)
        snapshot = next(iter(candidates)) if len(candidates) == 1 else None
        updated.append(url_source.model_copy(update={"snapshot_file": snapshot}))
    return manifest.model_copy(update={"url_sources": updated})
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/agentcli/test_assemble.py -k backfill -v`
Expected: PASS(7 項)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/agentcli/assemble.py tests/agentcli/test_assemble.py
git commit -m "feat: [agentcli] backfill_snapshot_files maps ledger URL→local snapshot"
```

---

## Task 4: 接線進 `run_assemble_pipeline`

在 pipeline 中,build_manifest 之後、寫 `manifest.json` 之前呼叫 backfill,讓 `snapshot_file` 落地到 `manifest.json`(下游 diff/foundry/人眼可追溯)。沒傳 `--url-coverage` → 整段跳過,行為與現狀完全相同。

**Files:**
- Modify: `loop_apidoc/agentcli/assemble.py:155-158`(build_manifest → backfill → 寫 manifest.json)
- Test: `tests/agentcli/test_assemble.py`

**Interfaces:**
- Consumes: `backfill_snapshot_files`(Task 3)、既有 `url_coverage`(已由 `load_coverage` 於 pipeline 前段解出)。

- [ ] **Step 1: 寫失敗測試**

在 `tests/agentcli/test_assemble.py` 末端新增。此測試用 `httpx.MockTransport` 讓 URL 探測不打真網路:

```python
import httpx

from loop_apidoc import manifest as _manifest_pkg  # noqa: F401  (確保套件已載入)


def _mock_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>overview</body></html>")
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_pipeline_backfills_snapshot_file_into_manifest(tmp_path, monkeypatch):
    from loop_apidoc.agentcli import assemble as assemble_mod

    _write_extraction(tmp_path / "extraction")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "overview.md").write_text("# Demo API\nGET /ping", encoding="utf-8")

    # coverage 帳本:entry URL 對應 sources/overview.md 快照
    cov = tmp_path / "coverage.json"
    cov.write_text(json.dumps({
        "entry_url": "https://a.example/overview",
        "confirmed_by_user": True,
        "expected": [{"url": "https://a.example/overview", "source": "user"}],
        "results": [{"url": "https://a.example/overview", "status": "fetched",
                     "file": "sources/overview.md", "method": "defuddle"}],
    }), encoding="utf-8")

    # build_manifest 內部會探測 URL — 用 MockTransport 攔截,避免真網路。
    real_build = assemble_mod.build_manifest

    def fake_build(*, sources_root, urls, generated_at):
        return real_build(sources_root=sources_root, urls=urls,
                          generated_at=generated_at, client=_mock_client())

    monkeypatch.setattr(assemble_mod, "build_manifest", fake_build)

    out = tmp_path / "out"
    assemble_mod.run_assemble_pipeline(
        sources_root=sources,
        extraction_dir=tmp_path / "extraction",
        output_root=out,
        run_id="run-cov",
        generated_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
        urls=["https://a.example/overview"],
        url_coverage_path=cov,
    )

    manifest_payload = json.loads(
        (out / "run-cov" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["url_sources"][0]["snapshot_file"] == "overview.md"


def test_pipeline_without_coverage_leaves_snapshot_file_none(tmp_path, monkeypatch):
    from loop_apidoc.agentcli import assemble as assemble_mod

    _write_extraction(tmp_path / "extraction")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "overview.md").write_text("# Demo API\nGET /ping", encoding="utf-8")

    real_build = assemble_mod.build_manifest

    def fake_build(*, sources_root, urls, generated_at):
        return real_build(sources_root=sources_root, urls=urls,
                          generated_at=generated_at, client=_mock_client())

    monkeypatch.setattr(assemble_mod, "build_manifest", fake_build)

    out = tmp_path / "out"
    assemble_mod.run_assemble_pipeline(
        sources_root=sources,
        extraction_dir=tmp_path / "extraction",
        output_root=out,
        run_id="run-nocov",
        generated_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
        urls=["https://a.example/overview"],
        url_coverage_path=None,
    )

    manifest_payload = json.loads(
        (out / "run-nocov" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["url_sources"][0]["snapshot_file"] is None
```

> 注意 `fake_build` 的關鍵字參數 `sources_root` / `urls` / `generated_at` 必須與 Task 4 Step 3 改好後 `run_assemble_pipeline` 對 `build_manifest` 的呼叫形狀一致(見下),`monkeypatch` 才攔得到。

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/agentcli/test_assemble.py -k "snapshot_file_into_manifest or snapshot_file_none" -v`
Expected: FAIL,`assert None == "overview.md"`(backfill 尚未接線,snapshot_file 仍為 None)

- [ ] **Step 3: 接線**

在 `loop_apidoc/agentcli/assemble.py` 的 `run_assemble_pipeline`,把:

```python
    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [], generated_at=generated_at)
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8")
```

改為:

```python
    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [], generated_at=generated_at)
    if url_coverage is not None:
        # 有帳本才回填 URL→快照檔映射;無帳本行為與現狀完全相同。
        manifest = backfill_snapshot_files(manifest, url_coverage)
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/agentcli/test_assemble.py -k "snapshot_file_into_manifest or snapshot_file_none" -v`
Expected: PASS(2 項)

- [ ] **Step 5: 跑整組 assemble 測試確認未回歸**

Run: `uv run pytest tests/agentcli/test_assemble.py -v`
Expected: 全 PASS(含既有 `test_run_assemble_pipeline_writes_outputs` 等)

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/agentcli/assemble.py tests/agentcli/test_assemble.py
git commit -m "feat: [agentcli] wire snapshot backfill into assemble before manifest write"
```

---

## Task 5: `sole_source` 摺疊 snapshot 對應的 URL

把「文件數」定義改為:可用本地來源 + 其 `snapshot_file` 未指向可用本地來源的 URL。摺疊後恰好一份文件時,回傳本地檔的 `relative_path`(內容實際所在、provenance 可指向的 artifact)。`match_manifest_source` 完全不動。

**Files:**
- Modify: `loop_apidoc/plan/classify.py:50-66`
- Test: `tests/plan/test_classify.py`

**Interfaces:**
- Consumes: `UrlSource.snapshot_file`(Task 2)。
- Produces: `sole_source(manifest: Manifest) -> str | None`(簽章不變,行為擴充)。

- [ ] **Step 1: 寫失敗測試**

在 `tests/plan/test_classify.py` 末端新增(補 import `UrlSource`、`sole_source`):

```python
from datetime import timezone  # 若尚未 import
from loop_apidoc.manifest.models import UrlSource
from loop_apidoc.plan.classify import sole_source


def _now():
    return datetime(2026, 7, 4, tzinfo=timezone.utc)


def _local_src(rel: str, status=ProcessingStatus.PENDING) -> LocalSource:
    return LocalSource(
        relative_path=rel, mime_type="text/markdown", source_format=SourceFormat.MARKDOWN,
        size_bytes=1, sha256="x", scanned_at=_now(), supported=True, status=status,
    )


def _url_src(url: str, snapshot_file: str | None = None) -> UrlSource:
    return UrlSource(url=url, fetched_at=_now(), http_status=200, snapshot_file=snapshot_file)


def test_sole_source_collapses_url_pointing_to_local_snapshot():
    # 1 快照檔 + 1 entry URL(snapshot 指回該檔)→ 1 份文件 → 回傳本地檔 relative_path
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("overview.md")],
        url_sources=[_url_src("https://a.example/overview", snapshot_file="overview.md")],
    )
    assert sole_source(manifest) == "overview.md"


def test_sole_source_url_without_snapshot_counts_as_separate_document():
    # 無 snapshot_file → URL 另計一份 → 2 份文件 → None(維持現狀)
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("overview.md")],
        url_sources=[_url_src("https://a.example/overview", snapshot_file=None)],
    )
    assert sole_source(manifest) is None


def test_sole_source_snapshot_to_unusable_source_does_not_collapse():
    # snapshot_file 指向不可用(UNREADABLE)本地來源 → 該 URL 不被摺疊,另計一份
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("overview.md", status=ProcessingStatus.UNREADABLE)],
        url_sources=[_url_src("https://a.example/overview", snapshot_file="overview.md")],
    )
    # 本地來源不可用(0 份)+ URL 不摺疊(1 份)→ 恰好 1 份 → 回傳 URL
    assert sole_source(manifest) == "https://a.example/overview"


def test_sole_source_multi_file_plus_url_still_none():
    manifest = Manifest(
        sources_root="/src", generated_at=_now(),
        local_sources=[_local_src("a.md"), _local_src("b.md")],
        url_sources=[_url_src("https://a.example/a", snapshot_file="a.md")],
    )
    # 摺疊後仍是 a.md + b.md = 2 份 → None(多來源 run 仍須嚴格比對)
    assert sole_source(manifest) is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/plan/test_classify.py -k sole_source -v`
Expected: FAIL,`test_sole_source_collapses_url_pointing_to_local_snapshot` 期待 `"overview.md"` 但得 `None`(現行實作把 local + url 算成 2 份)

- [ ] **Step 3: 改 `sole_source`**

把 `loop_apidoc/plan/classify.py` 的 `sole_source` 整個函式改為:

```python
def sole_source(manifest: Manifest) -> str | None:
    """Return the lone usable *document*'s identifier if the manifest collapses to
    exactly one, else None.

    A document is a usable local source, plus each URL whose snapshot_file does NOT
    point at a usable local source. A URL saved as a local snapshot (per the
    url-fetching SOP) is the SAME document as that snapshot, so it is not counted
    twice — otherwise every SOP-following URL run would have ≥2 documents and lose
    single-source attribution. When exactly one document remains, a citation that
    names a section (not the filename), or carries no locator, is still
    attributable to it. With multiple documents we cannot disambiguate and fall
    back to strict matching. The collapsed URL returns the LOCAL file's
    relative_path (where the content actually lives, and what provenance targets),
    not the URL.
    """
    usable = [
        s.relative_path
        for s in manifest.local_sources
        if s.supported and s.status not in _UNUSABLE
    ]
    usable_set = set(usable)
    documents = list(usable)
    for url_source in manifest.url_sources:
        if url_source.snapshot_file is not None and url_source.snapshot_file in usable_set:
            continue  # 這個 URL 就是某可用本地快照檔,不另計一份文件
        documents.append(url_source.url)
    return documents[0] if len(documents) == 1 else None
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/plan/test_classify.py -v`
Expected: 全 PASS(新增 4 項 + 既有全部,含 `test_single_source_*`、`test_classify_unverified_*`)

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/plan/classify.py tests/plan/test_classify.py
git commit -m "feat: [plan] collapse snapshot-backed URL into its local document in sole_source"
```

---

## Task 6: plan 層整合測試 + 全回歸

證明「backfill → sole_source → build_normalization_plan」端到端修復假陰性:line-pay 形狀(單快照檔 + entry URL + 帳本、章節式 locator)摺疊後 plan 無 `unverified_items`;對照無帳本時維持現狀(有 `unverified_items`)。網路無關——直接建 manifest,不走 URL 探測。

**Files:**
- Create: `tests/agentcli/test_snapshot_collapse.py`
- Test: 全套 `uv run pytest` + `uv run ruff check .`

**Interfaces:**
- Consumes: `backfill_snapshot_files`(Task 3)、`build_normalization_plan`(`loop_apidoc/plan/builder.py`)、`build_extraction_from_files`(`loop_apidoc/agentcli/assemble.py`)。

- [ ] **Step 1: 寫整合測試**

新建 `tests/agentcli/test_snapshot_collapse.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.agentcli.assemble import backfill_snapshot_files, build_extraction_from_files
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
)
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.preparation.coverage import CoverageResult, ResultStatus, UrlCoverage

_NOW = datetime(2026, 7, 4, tzinfo=timezone.utc)

# 章節式 locator(非檔名、非完整 URL)——多來源時 match_manifest_source 落空
_INVENTORY = {
    "overview": "Line Pay Online v3",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "線上付款 §1"}],
    "security_schemes": [],
    "endpoints": [{"method": "POST", "path": "/payments/request",
                   "summary": "請求付款", "source": "線上付款 §3"}],
    "schemas": [],
    "errors": [],
    "operational": [],
    "missing": [],
}
_ENDPOINT = {
    "method": "POST", "path": "/payments/request", "parameters": [],
    "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [], "source": "線上付款 §3",
}


def _manifest(url_snapshot: str | None) -> Manifest:
    return Manifest(
        sources_root="/src", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="online-api-v3-overview.md", mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=1, sha256="x",
            scanned_at=_NOW, supported=True, status=ProcessingStatus.PENDING)],
        url_sources=[UrlSource(url="https://pay.example/online/v3", fetched_at=_NOW,
                               http_status=200, snapshot_file=url_snapshot)],
    )


def _extraction(tmp_path):
    import json
    store = ExtractionStore(tmp_path / "store")
    return build_extraction_from_files(
        _INVENTORY, [json.dumps(_ENDPOINT, ensure_ascii=False)], store)


def test_backfilled_snapshot_collapses_and_removes_unverified(tmp_path):
    # 帳本把 entry URL 映射到單一本地快照檔 → 摺疊為 1 份文件 → 章節式 locator 歸屬回檔
    coverage = UrlCoverage(
        entry_url="https://pay.example/online/v3",
        results=[CoverageResult(url="https://pay.example/online/v3",
                                status=ResultStatus.FETCHED,
                                file="sources/online-api-v3-overview.md")],
    )
    manifest = backfill_snapshot_files(_manifest(None), coverage)
    assert manifest.url_sources[0].snapshot_file == "online-api-v3-overview.md"

    plan = build_normalization_plan(_extraction(tmp_path), manifest)
    assert plan.unverified_items == []


def test_no_ledger_preserves_current_unverified_behavior(tmp_path):
    # 無帳本(snapshot_file=None)→ URL 另計 → 2 份文件 → 章節式 locator 落空 → UNVERIFIED
    manifest = _manifest(None)
    plan = build_normalization_plan(_extraction(tmp_path), manifest)
    assert plan.unverified_items  # 至少一項 UNVERIFIED(現狀維持)
```

- [ ] **Step 2: 跑整合測試確認通過**

Run: `uv run pytest tests/agentcli/test_snapshot_collapse.py -v`
Expected: PASS(2 項)。若 `test_no_ledger_preserves_current_unverified_behavior` 未如預期產生 unverified,先確認 `_INVENTORY`/`_ENDPOINT` 的 `source` 確為章節式字串(非檔名、非完整 URL),使多來源 manifest 下 `match_manifest_source` 必然落空。

- [ ] **Step 3: 全套回歸 + lint**

Run: `uv run pytest`
Expected: 全 PASS(既有 + 本次新增;benchmark harness 缺本機 sources 的 case 自動 skip)

Run: `uv run ruff check .`
Expected: 無錯誤(`All checks passed!`)

- [ ] **Step 4: Commit**

```bash
git add tests/agentcli/test_snapshot_collapse.py
git commit -m "test: [agentcli] plan-level integration for snapshot URL collapse"
```

---

## Self-Review

**1. Spec coverage:**

| Spec 段落 | 對應 Task |
| --- | --- |
| §設計 1:Manifest schema additive `snapshot_file` | Task 2 |
| §設計 2:回填邏輯(URL 相符 / 只帶 file 的 fetched·fetched_rendered·auth_required / 路徑後綴匹配 / 唯一命中 / 無 `--url-coverage` 跳過) | Task 3(純函式全條件)+ Task 4(pipeline 跳過條件) |
| §設計 2:`_normalize_url` 移到 coverage.py 成公開 `normalize_url` 兩處共用 | Task 1 |
| §設計 3:sole_source 文件數定義 + 摺疊回傳本地 relative_path + `match_manifest_source` 不動 | Task 5 |
| §設計 4:line-pay PASS 恢復 / ecpay 多頁維持嚴格 / 不改驗證閘·url_coverage phase·嚴格比對 | Task 5(多檔+URL 仍 None 測試)+ Task 6(整合) |
| §設計 5:錯誤處理(load_coverage 已 fail-loud、配對失敗靜默 None、不新增錯誤路徑) | Task 3(零/多重命中 → None,不拋錯) |
| §設計 6:classify 單元 / assemble 回填 / 整合 / 既有回歸 | Task 5 / Task 3+4 / Task 6 / Task 6 Step 3 |

無缺口。

**2. Placeholder scan:** 每個 code step 皆為完整程式碼;無 TBD/TODO/"similar to"/"add error handling" 佔位。

**3. Type consistency:**
- `backfill_snapshot_files(manifest: Manifest, coverage: UrlCoverage) -> Manifest`:Task 3 定義、Task 4/Task 6 呼叫,簽章一致。
- `normalize_url(url: str) -> str`:Task 1 定義、Task 3 使用,一致。
- `UrlSource.snapshot_file: str | None`:Task 2 定義、Task 3 寫、Task 5 讀,型別一致。
- `sole_source(manifest) -> str | None`:簽章未變,僅行為擴充。
- Task 4 的 `fake_build` 關鍵字 `sources_root`/`urls`/`generated_at` 與 `run_assemble_pipeline` 內對 `build_manifest` 的呼叫形狀一致(該呼叫本就用這三個關鍵字),monkeypatch 可攔截。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-04-sole-document-url-snapshot-collapse.md`. Two execution options:

1. **Subagent-Driven (recommended)** — 每個 Task 派一個新 subagent,任務間我審查,快速迭代。
2. **Inline Execution** — 在本 session 依 executing-plans 分批執行、設檢查點審查。

要用哪一種?
