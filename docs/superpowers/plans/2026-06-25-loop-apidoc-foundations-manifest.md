# Loop API 文件 Pipeline — Plan 1：基礎建設與來源 Manifest

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `loop-apidoc` Python CLI 的專案骨架，並交付可運作的 `loop-apidoc manifest` 命令，將本機來源目錄與公開 URL 掃描成一份來源 manifest（含格式辨識、SHA-256、重複判定與處理狀態）。

**Architecture:** 純函式式的掃描層（`scanner`、`urls`）產出 Pydantic 模型，由 `builder` 組合成 `Manifest`，再由 Typer CLI 序列化為 JSON。所有與時間、網路相關的副作用都以參數注入（`generated_at`、`httpx.Client`），讓每一層都能在不碰真實時鐘或網路的情況下測試。

**Tech Stack:** Python ≥3.11、Typer（CLI）、Pydantic v2（資料模型與驗證）、httpx（URL 探測，測試以 `httpx.MockTransport` 注入）、uv（套件管理）、pytest（測試）。

這是六份計畫中的第 1 份。後續計畫（NotebookLM adapter+doctor、擷取+規格化計畫、產生 OpenAPI/Markdown/provenance、驗證、修正循環+完整 run）會沿用此處建立的 `loop_apidoc` 套件結構與 `Manifest` 模型。

## Global Constraints

下列為整份 spec 的專案級要求，每個 task 都隱含遵守（值逐字取自 spec）：

- **來源為唯一事實依據**：來源未提供的資訊不得推測；缺漏必須明確記錄，不得靜默略過（spec §1、§11「不支援檔案：加入 manifest issue，不靜默略過」）。
- **第一版支援來源**：PDF、Markdown、Microsoft Word、OpenAPI JSON 或 YAML、公開 URL（spec §2.1）。
- **輸出語言預設**：`zh-TW`（spec §5）。
- **規格版本**：OpenAPI 3.1（spec §5）。
- **最大修正輪數**：3（spec §5、§10）。
- **禁止推測**：預設啟用（spec §5）。
- **NotebookLM skill 只能透過 `scripts/run.py` wrapper 執行**，不可直接執行 `auth_manager.py`、`notebook_manager.py`、`ask_question.py`（spec §4.1）。
- **機密資料**：輸出及 log 不應保存 Google cookie、browser state 或憑證；skill 的 `data/`、`.venv/` 與瀏覽器狀態不得複製至專案或提交 Git（spec §11）。
- **Python 主程式**，核心流程不得直接耦合瀏覽器自動化細節（spec §4.1）。

> 與本計畫（manifest 階段）直接相關者：支援來源清單、缺漏不得靜默略過、機密與 skill 狀態不得入庫、副作用可注入以利測試。

---

### Task 1：專案骨架與 CLI 外殼

建立 uv 專案、套件結構與一個可執行的 Typer 進入點。此 task 完成後 `uv run pytest` 可跑、`uv run loop-apidoc --help` 可顯示說明。

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `loop_apidoc/__init__.py`
- Create: `loop_apidoc/cli.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_cli_smoke.py`

**Interfaces:**
- Consumes: 無（首個 task）。
- Produces:
  - `loop_apidoc.cli.app`：`typer.Typer` 實例，含一個 `@app.callback()` 強制子命令模式。
  - `loop_apidoc.cli.main() -> None`：console-script 進入點，呼叫 `app()`。
  - console script：`loop-apidoc = "loop_apidoc.cli:main"`。
  - pytest fixture `fixed_now() -> datetime`（位於 `tests/conftest.py`），回傳 `datetime(2026, 6, 25, 9, 0, 0, tzinfo=timezone.utc)`。

- [ ] **Step 1：建立 `pyproject.toml`**

```toml
[project]
name = "loop-apidoc"
version = "0.1.0"
description = "Source-grounded API documentation pipeline for Loop Engineering"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "pydantic>=2.6",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "openapi-spec-validator>=0.7",
    "jsonschema>=4.21",
]

[project.scripts]
loop-apidoc = "loop_apidoc.cli:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["loop_apidoc"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2：建立 `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.coverage
htmlcov/
dist/
output/

# notebooklm-skill local state — never commit (spec §11)
**/notebooklm-skill/data/
**/notebooklm-skill/.venv/
**/notebooklm-skill/**/browser_state*
```

- [ ] **Step 3：建立套件與測試的 `__init__.py` 與 conftest**

`loop_apidoc/__init__.py`：

```python
"""Loop source-grounded API documentation pipeline."""

__version__ = "0.1.0"
```

`tests/__init__.py`：（空檔）

```python
```

`tests/conftest.py`：

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def fixed_now() -> datetime:
    """Deterministic timestamp injected into time-dependent code paths."""
    return datetime(2026, 6, 25, 9, 0, 0, tzinfo=timezone.utc)
```

- [ ] **Step 4：建立 CLI 外殼 `loop_apidoc/cli.py`**

```python
from __future__ import annotations

import typer

app = typer.Typer(
    help="Loop 來源依據式 API 文件 pipeline",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """Loop 來源依據式 API 文件 pipeline。"""


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5：寫 smoke 測試 `tests/test_cli_smoke.py`**

```python
from __future__ import annotations

from typer.testing import CliRunner

from loop_apidoc.cli import app


def test_help_runs():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "pipeline" in result.stdout.lower()
```

- [ ] **Step 6：同步依賴並執行測試確認通過**

Run: `uv sync && uv run pytest tests/test_cli_smoke.py -v`
Expected: PASS（`test_help_runs`）。若 `uv sync` 為首次執行會建立 `.venv` 並安裝依賴。

- [ ] **Step 7：確認 console script 可執行**

Run: `uv run loop-apidoc --help`
Expected: exit code 0，輸出包含「pipeline」字樣的說明文字。

- [ ] **Step 8：Commit**

```bash
git add pyproject.toml .gitignore loop_apidoc/ tests/
git commit -m "chore: scaffold loop-apidoc CLI project skeleton"
```

---

### Task 2：來源 Manifest 資料模型

定義 manifest 的 Pydantic 模型與列舉。對應 spec §6 的本機來源與 URL 來源欄位。

**Files:**
- Create: `loop_apidoc/manifest/__init__.py`
- Create: `loop_apidoc/manifest/models.py`
- Create: `tests/manifest/__init__.py`
- Create: `tests/manifest/test_models.py`

**Interfaces:**
- Consumes: 無外部相依。
- Produces：
  - `SourceFormat(str, Enum)`：值 `pdf` / `markdown` / `word` / `openapi-json` / `openapi-yaml` / `unknown`。
  - `ProcessingStatus(str, Enum)`：值 `pending` / `unsupported` / `duplicate`。
  - `LocalSource(BaseModel)`，欄位：`relative_path: str`、`mime_type: str | None`、`source_format: SourceFormat`、`size_bytes: int`、`sha256: str`、`scanned_at: datetime`、`supported: bool`、`status: ProcessingStatus`、`duplicate_of: str | None = None`。
  - `UrlSource(BaseModel)`，欄位：`url: str`、`fetched_at: datetime`、`http_status: int | None`、`content_sha256: str | None = None`、`note: str | None = None`。
  - `Manifest(BaseModel)`，欄位：`sources_root: str`、`generated_at: datetime`、`local_sources: list[LocalSource]`、`url_sources: list[UrlSource]`；方法 `unsupported() -> list[LocalSource]`、`duplicates() -> list[LocalSource]`。

- [ ] **Step 1：建立 `tests/manifest/__init__.py`**

```python
```

- [ ] **Step 2：寫失敗測試 `tests/manifest/test_models.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
)


def _local(path: str, status: ProcessingStatus) -> LocalSource:
    return LocalSource(
        relative_path=path,
        mime_type="text/markdown",
        source_format=SourceFormat.MARKDOWN,
        size_bytes=4,
        sha256="abc",
        scanned_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        supported=status is not ProcessingStatus.UNSUPPORTED,
        status=status,
    )


def test_manifest_json_round_trip():
    manifest = Manifest(
        sources_root="/sources",
        generated_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        local_sources=[_local("a.md", ProcessingStatus.PENDING)],
        url_sources=[
            UrlSource(
                url="https://example.com/api",
                fetched_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
                http_status=200,
                content_sha256="deadbeef",
            )
        ],
    )

    payload = manifest.model_dump_json()
    restored = Manifest.model_validate_json(payload)

    assert restored == manifest
    assert json.loads(payload)["local_sources"][0]["status"] == "pending"


def test_manifest_helpers_filter_by_status():
    manifest = Manifest(
        sources_root="/sources",
        generated_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        local_sources=[
            _local("a.md", ProcessingStatus.PENDING),
            _local("b.md", ProcessingStatus.DUPLICATE),
            _local("notes.txt", ProcessingStatus.UNSUPPORTED),
        ],
    )

    assert [s.relative_path for s in manifest.unsupported()] == ["notes.txt"]
    assert [s.relative_path for s in manifest.duplicates()] == ["b.md"]
```

- [ ] **Step 3：執行測試確認失敗**

Run: `uv run pytest tests/manifest/test_models.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.manifest'`）。

- [ ] **Step 4：建立 `loop_apidoc/manifest/__init__.py`**

```python
"""Source manifest building."""
```

- [ ] **Step 5：實作 `loop_apidoc/manifest/models.py`**

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceFormat(str, Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    WORD = "word"
    OPENAPI_JSON = "openapi-json"
    OPENAPI_YAML = "openapi-yaml"
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    UNSUPPORTED = "unsupported"
    DUPLICATE = "duplicate"


class LocalSource(BaseModel):
    relative_path: str
    mime_type: str | None
    source_format: SourceFormat
    size_bytes: int
    sha256: str
    scanned_at: datetime
    supported: bool
    status: ProcessingStatus
    duplicate_of: str | None = None


class UrlSource(BaseModel):
    url: str
    fetched_at: datetime
    http_status: int | None
    content_sha256: str | None = None
    note: str | None = None


class Manifest(BaseModel):
    sources_root: str
    generated_at: datetime
    local_sources: list[LocalSource] = Field(default_factory=list)
    url_sources: list[UrlSource] = Field(default_factory=list)

    def unsupported(self) -> list[LocalSource]:
        return [s for s in self.local_sources if s.status is ProcessingStatus.UNSUPPORTED]

    def duplicates(self) -> list[LocalSource]:
        return [s for s in self.local_sources if s.status is ProcessingStatus.DUPLICATE]
```

- [ ] **Step 6：執行測試確認通過**

Run: `uv run pytest tests/manifest/test_models.py -v`
Expected: PASS（兩個測試）。

- [ ] **Step 7：Commit**

```bash
git add loop_apidoc/manifest/__init__.py loop_apidoc/manifest/models.py tests/manifest/
git commit -m "feat: add source manifest data models"
```

---

### Task 3：格式辨識

依副檔名辨識來源格式並判定是否受支援，對應 spec §2.1 的五類來源（URL 另由 Task 5 處理）。

**Files:**
- Create: `loop_apidoc/manifest/formats.py`
- Create: `tests/manifest/test_formats.py`

**Interfaces:**
- Consumes: `loop_apidoc.manifest.models.SourceFormat`。
- Produces：
  - `detect_format(path: pathlib.Path) -> SourceFormat`：依 `path.suffix.lower()` 對應；未知副檔名回傳 `SourceFormat.UNKNOWN`。
  - `is_supported(source_format: SourceFormat) -> bool`：`source_format is not SourceFormat.UNKNOWN`。
  - `guess_mime_type(path: pathlib.Path) -> str | None`：以 `mimetypes.guess_type` 推測，無法判定時回傳 `None`。

- [ ] **Step 1：寫失敗測試 `tests/manifest/test_formats.py`**

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.manifest.formats import detect_format, is_supported
from loop_apidoc.manifest.models import SourceFormat


def test_detect_pdf_is_case_insensitive():
    assert detect_format(Path("spec.PDF")) is SourceFormat.PDF


def test_detect_markdown_variants():
    assert detect_format(Path("guide.md")) is SourceFormat.MARKDOWN
    assert detect_format(Path("guide.markdown")) is SourceFormat.MARKDOWN


def test_detect_word_and_openapi():
    assert detect_format(Path("notes.docx")) is SourceFormat.WORD
    assert detect_format(Path("api.json")) is SourceFormat.OPENAPI_JSON
    assert detect_format(Path("api.yaml")) is SourceFormat.OPENAPI_YAML
    assert detect_format(Path("api.yml")) is SourceFormat.OPENAPI_YAML


def test_detect_unknown_extension():
    assert detect_format(Path("notes.txt")) is SourceFormat.UNKNOWN


def test_is_supported():
    assert is_supported(SourceFormat.WORD) is True
    assert is_supported(SourceFormat.UNKNOWN) is False
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/manifest/test_formats.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.manifest.formats'`）。

- [ ] **Step 3：實作 `loop_apidoc/manifest/formats.py`**

```python
from __future__ import annotations

import mimetypes
from pathlib import Path

from loop_apidoc.manifest.models import SourceFormat

_EXTENSION_FORMATS: dict[str, SourceFormat] = {
    ".pdf": SourceFormat.PDF,
    ".md": SourceFormat.MARKDOWN,
    ".markdown": SourceFormat.MARKDOWN,
    ".docx": SourceFormat.WORD,
    ".doc": SourceFormat.WORD,
    ".json": SourceFormat.OPENAPI_JSON,
    ".yaml": SourceFormat.OPENAPI_YAML,
    ".yml": SourceFormat.OPENAPI_YAML,
}


def detect_format(path: Path) -> SourceFormat:
    return _EXTENSION_FORMATS.get(path.suffix.lower(), SourceFormat.UNKNOWN)


def is_supported(source_format: SourceFormat) -> bool:
    return source_format is not SourceFormat.UNKNOWN


def guess_mime_type(path: Path) -> str | None:
    mime, _ = mimetypes.guess_type(path.name)
    return mime
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/manifest/test_formats.py -v`
Expected: PASS（五個測試）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/manifest/formats.py tests/manifest/test_formats.py
git commit -m "feat: add source format detection"
```

---

### Task 4：本機來源掃描

遞迴掃描來源目錄，計算 SHA-256，辨識格式，判定重複與處理狀態，產出 `list[LocalSource]`。對應 spec §6 本機來源欄位與重複判定。

**Files:**
- Create: `loop_apidoc/manifest/scanner.py`
- Create: `tests/manifest/test_scanner.py`

**Interfaces:**
- Consumes: `loop_apidoc.manifest.formats.{detect_format, guess_mime_type, is_supported}`、`loop_apidoc.manifest.models.{LocalSource, ProcessingStatus}`。
- Produces：
  - `hash_file(path: pathlib.Path) -> str`：以 1 MiB 分塊讀檔回傳 SHA-256 hex digest。
  - `scan_sources(root: pathlib.Path, scanned_at: datetime) -> list[LocalSource]`：依 `root.rglob("*")` 取所有檔案，**以相對路徑字典序排序**後逐一處理；不支援格式 → `UNSUPPORTED`；支援但 SHA-256 已出現 → `DUPLICATE` 且 `duplicate_of` 指向第一個出現的相對路徑；其餘 → `PENDING`。回傳順序與排序一致。

- [ ] **Step 1：寫失敗測試 `tests/manifest/test_scanner.py`**

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.manifest.models import ProcessingStatus, SourceFormat
from loop_apidoc.manifest.scanner import hash_file, scan_sources


def test_hash_file_matches_known_value(tmp_path: Path):
    target = tmp_path / "x.bin"
    target.write_bytes(b"abc")
    # SHA-256 of b"abc"
    assert hash_file(target) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_scan_classifies_and_dedupes(tmp_path: Path, fixed_now):
    (tmp_path / "a.md").write_text("same", encoding="utf-8")
    (tmp_path / "b.md").write_text("same", encoding="utf-8")  # duplicate content
    (tmp_path / "notes.txt").write_text("unsupported", encoding="utf-8")

    sources = scan_sources(tmp_path, scanned_at=fixed_now)
    by_path = {s.relative_path: s for s in sources}

    assert by_path["a.md"].status is ProcessingStatus.PENDING
    assert by_path["a.md"].supported is True
    assert by_path["b.md"].status is ProcessingStatus.DUPLICATE
    assert by_path["b.md"].duplicate_of == "a.md"
    assert by_path["a.md"].sha256 == by_path["b.md"].sha256
    assert by_path["notes.txt"].status is ProcessingStatus.UNSUPPORTED
    assert by_path["notes.txt"].supported is False
    assert by_path["notes.txt"].source_format is SourceFormat.UNKNOWN
    assert by_path["a.md"].scanned_at == fixed_now


def test_scan_records_nested_relative_paths(tmp_path: Path, fixed_now):
    nested = tmp_path / "api" / "v1"
    nested.mkdir(parents=True)
    (nested / "openapi.yaml").write_text("openapi: 3.1.0", encoding="utf-8")

    sources = scan_sources(tmp_path, scanned_at=fixed_now)

    assert len(sources) == 1
    assert sources[0].relative_path == "api/v1/openapi.yaml"
    assert sources[0].source_format is SourceFormat.OPENAPI_YAML
    assert sources[0].size_bytes == len(b"openapi: 3.1.0")
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/manifest/test_scanner.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.manifest.scanner'`）。

- [ ] **Step 3：實作 `loop_apidoc/manifest/scanner.py`**

```python
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from loop_apidoc.manifest.formats import detect_format, guess_mime_type, is_supported
from loop_apidoc.manifest.models import LocalSource, ProcessingStatus

_CHUNK_SIZE = 1 << 20  # 1 MiB


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_sources(root: Path, scanned_at: datetime) -> list[LocalSource]:
    sources: list[LocalSource] = []
    seen_hashes: dict[str, str] = {}  # sha256 -> first relative_path

    files = sorted(
        (p for p in root.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(root).as_posix(),
    )

    for path in files:
        relative_path = path.relative_to(root).as_posix()
        source_format = detect_format(path)
        supported = is_supported(source_format)
        sha256 = hash_file(path)

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
                size_bytes=path.stat().st_size,
                sha256=sha256,
                scanned_at=scanned_at,
                supported=supported,
                status=status,
                duplicate_of=duplicate_of,
            )
        )

    return sources
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/manifest/test_scanner.py -v`
Expected: PASS（三個測試）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/manifest/scanner.py tests/manifest/test_scanner.py
git commit -m "feat: add local source scanner with dedupe and status"
```

---

### Task 5：公開 URL 探測

對每個公開 URL 發出 GET，記錄 HTTP 狀態與（成功時）內容雜湊。對應 spec §6 公開 URL 欄位。`httpx.Client` 由呼叫端注入，測試以 `httpx.MockTransport` 提供，不碰真實網路。

**Files:**
- Create: `loop_apidoc/manifest/urls.py`
- Create: `tests/manifest/test_urls.py`

**Interfaces:**
- Consumes: `loop_apidoc.manifest.models.UrlSource`、`httpx`。
- Produces：
  - `probe_url(url: str, fetched_at: datetime, client: httpx.Client) -> UrlSource`：成功（`response.is_success`）時設 `http_status` 與 `content_sha256`；非 2xx 時設 `http_status` 但 `content_sha256=None`；`httpx.HTTPError` 時 `http_status=None`、`content_sha256=None`、`note` 含例外類別名稱。

- [ ] **Step 1：寫失敗測試 `tests/manifest/test_urls.py`**

```python
from __future__ import annotations

import hashlib

import httpx

from loop_apidoc.manifest.urls import probe_url


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_probe_url_success_records_status_and_hash(fixed_now):
    body = b"hello world"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    with _client(handler) as client:
        result = probe_url("https://example.com/api", fetched_at=fixed_now, client=client)

    assert result.url == "https://example.com/api"
    assert result.http_status == 200
    assert result.content_sha256 == hashlib.sha256(body).hexdigest()
    assert result.fetched_at == fixed_now
    assert result.note is None


def test_probe_url_non_success_has_no_hash(fixed_now):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with _client(handler) as client:
        result = probe_url("https://example.com/missing", fetched_at=fixed_now, client=client)

    assert result.http_status == 404
    assert result.content_sha256 is None


def test_probe_url_network_error_records_note(fixed_now):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with _client(handler) as client:
        result = probe_url("https://example.com/down", fetched_at=fixed_now, client=client)

    assert result.http_status is None
    assert result.content_sha256 is None
    assert result.note is not None
    assert "ConnectError" in result.note
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/manifest/test_urls.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.manifest.urls'`）。

- [ ] **Step 3：實作 `loop_apidoc/manifest/urls.py`**

```python
from __future__ import annotations

import hashlib
from datetime import datetime

import httpx

from loop_apidoc.manifest.models import UrlSource


def probe_url(url: str, fetched_at: datetime, client: httpx.Client) -> UrlSource:
    try:
        response = client.get(url)
    except httpx.HTTPError as error:
        return UrlSource(
            url=url,
            fetched_at=fetched_at,
            http_status=None,
            content_sha256=None,
            note=f"fetch failed: {error.__class__.__name__}",
        )

    content_sha256 = None
    if response.is_success:
        content_sha256 = hashlib.sha256(response.content).hexdigest()

    return UrlSource(
        url=url,
        fetched_at=fetched_at,
        http_status=response.status_code,
        content_sha256=content_sha256,
    )
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/manifest/test_urls.py -v`
Expected: PASS（三個測試）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/manifest/urls.py tests/manifest/test_urls.py
git commit -m "feat: add public URL probing for manifest"
```

---

### Task 6：Manifest 組合器

把本機掃描與 URL 探測組合成單一 `Manifest`。負責在未注入 client 時自行建立並關閉 `httpx.Client`。

**Files:**
- Create: `loop_apidoc/manifest/builder.py`
- Create: `tests/manifest/test_builder.py`

**Interfaces:**
- Consumes: `loop_apidoc.manifest.scanner.scan_sources`、`loop_apidoc.manifest.urls.probe_url`、`loop_apidoc.manifest.models.Manifest`、`httpx`。
- Produces：
  - `build_manifest(sources_root: pathlib.Path, urls: list[str], generated_at: datetime, client: httpx.Client | None = None) -> Manifest`：`local_sources` 來自 `scan_sources(sources_root, scanned_at=generated_at)`；`url_sources` 對每個 url 呼叫 `probe_url(..., fetched_at=generated_at, ...)`；`client=None` 時建立 `httpx.Client(timeout=10.0, follow_redirects=True)` 並在結束時關閉；`Manifest.sources_root` 設為 `str(sources_root)`。

- [ ] **Step 1：寫失敗測試 `tests/manifest/test_builder.py`**

```python
from __future__ import annotations

from pathlib import Path

import httpx

from loop_apidoc.manifest.builder import build_manifest
from loop_apidoc.manifest.models import ProcessingStatus


def test_build_manifest_combines_local_and_urls(tmp_path: Path, fixed_now):
    (tmp_path / "openapi.yaml").write_text("openapi: 3.1.0", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"doc")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with client:
        manifest = build_manifest(
            sources_root=tmp_path,
            urls=["https://example.com/api"],
            generated_at=fixed_now,
            client=client,
        )

    assert manifest.sources_root == str(tmp_path)
    assert manifest.generated_at == fixed_now
    assert len(manifest.local_sources) == 1
    assert manifest.local_sources[0].status is ProcessingStatus.PENDING
    assert len(manifest.url_sources) == 1
    assert manifest.url_sources[0].http_status == 200


def test_build_manifest_without_urls_needs_no_client(tmp_path: Path, fixed_now):
    (tmp_path / "guide.md").write_text("hi", encoding="utf-8")

    manifest = build_manifest(
        sources_root=tmp_path,
        urls=[],
        generated_at=fixed_now,
    )

    assert manifest.url_sources == []
    assert len(manifest.local_sources) == 1
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/manifest/test_builder.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.manifest.builder'`）。

- [ ] **Step 3：實作 `loop_apidoc/manifest/builder.py`**

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx

from loop_apidoc.manifest.models import Manifest, UrlSource
from loop_apidoc.manifest.scanner import scan_sources
from loop_apidoc.manifest.urls import probe_url


def build_manifest(
    sources_root: Path,
    urls: list[str],
    generated_at: datetime,
    client: httpx.Client | None = None,
) -> Manifest:
    local_sources = scan_sources(sources_root, scanned_at=generated_at)

    url_sources: list[UrlSource] = []
    if urls:
        owns_client = client is None
        active_client = client or httpx.Client(timeout=10.0, follow_redirects=True)
        try:
            url_sources = [
                probe_url(url, fetched_at=generated_at, client=active_client)
                for url in urls
            ]
        finally:
            if owns_client:
                active_client.close()

    return Manifest(
        sources_root=str(sources_root),
        generated_at=generated_at,
        local_sources=local_sources,
        url_sources=url_sources,
    )
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/manifest/test_builder.py -v`
Expected: PASS（兩個測試）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/manifest/builder.py tests/manifest/test_builder.py
git commit -m "feat: add manifest builder combining sources and urls"
```

---

### Task 7：`loop-apidoc manifest` CLI 命令

把 builder 接上 CLI，產出 spec §5 的 `loop-apidoc manifest --sources ./sources`。支援可重複的 `--url` 與選擇性 `--output`（省略則輸出至 stdout）。

**Files:**
- Modify: `loop_apidoc/cli.py`
- Create: `tests/test_cli_manifest.py`

**Interfaces:**
- Consumes: `loop_apidoc.manifest.builder.build_manifest`。
- Produces：CLI 子命令 `manifest`，選項 `--sources`（必填、須為既有目錄）、`--url`（可重複、預設空清單）、`--output`（選填路徑）。以 `Manifest.model_dump_json(indent=2)` 序列化；`--output` 存在時寫檔（UTF-8）並回報路徑，否則印到 stdout。

- [ ] **Step 1：寫失敗測試 `tests/test_cli_manifest.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()


def test_manifest_command_writes_output(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "guide.md").write_text("hello", encoding="utf-8")
    output = tmp_path / "manifest.json"

    result = runner.invoke(
        app, ["manifest", "--sources", str(sources), "--output", str(output)]
    )

    assert result.exit_code == 0, result.stdout
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["local_sources"][0]["relative_path"] == "guide.md"
    assert data["local_sources"][0]["status"] == "pending"


def test_manifest_command_prints_to_stdout(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "guide.md").write_text("hello", encoding="utf-8")

    result = runner.invoke(app, ["manifest", "--sources", str(sources)])

    assert result.exit_code == 0
    assert '"sources_root"' in result.stdout


def test_manifest_command_rejects_missing_sources_dir(tmp_path: Path):
    missing = tmp_path / "does-not-exist"

    result = runner.invoke(app, ["manifest", "--sources", str(missing)])

    assert result.exit_code != 0
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/test_cli_manifest.py -v`
Expected: FAIL（`manifest` 子命令尚不存在，Typer 以 exit code 2 回報 "No such command"；`test_manifest_command_writes_output` 等斷言失敗）。

- [ ] **Step 3：在 `loop_apidoc/cli.py` 加入 `manifest` 命令**

把整個 `loop_apidoc/cli.py` 取代為：

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer

from loop_apidoc.manifest.builder import build_manifest

app = typer.Typer(
    help="Loop 來源依據式 API 文件 pipeline",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """Loop 來源依據式 API 文件 pipeline。"""


@app.command()
def manifest(
    sources: Path = typer.Option(
        ...,
        "--sources",
        help="本機來源目錄",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    url: list[str] = typer.Option(
        [],
        "--url",
        help="公開來源 URL，可重複指定",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="manifest.json 輸出路徑；省略則輸出至 stdout",
    ),
) -> None:
    """掃描本機來源並建立來源 manifest。"""
    generated_at = datetime.now(timezone.utc)
    result = build_manifest(
        sources_root=sources,
        urls=list(url),
        generated_at=generated_at,
    )
    payload = result.model_dump_json(indent=2)
    if output is None:
        typer.echo(payload)
    else:
        output.write_text(payload, encoding="utf-8")
        typer.echo(f"manifest 已寫入 {output}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/test_cli_manifest.py -v`
Expected: PASS（三個測試）。

- [ ] **Step 5：執行整體測試套件**

Run: `uv run pytest`
Expected: 全部 PASS（Task 1–7 共 ~18 個測試）。

- [ ] **Step 6：手動驗證 CLI 端到端**

```bash
mkdir -p /tmp/loop-sources && echo "openapi: 3.1.0" > /tmp/loop-sources/api.yaml
uv run loop-apidoc manifest --sources /tmp/loop-sources
```

Expected: stdout 印出 JSON，`local_sources[0].relative_path == "api.yaml"`、`source_format == "openapi-yaml"`、`status == "pending"`。

- [ ] **Step 7：Commit**

```bash
git add loop_apidoc/cli.py tests/test_cli_manifest.py
git commit -m "feat: add loop-apidoc manifest command"
```

---

## 後續計畫（不在本計畫範圍）

| Plan | 範圍 | 主要交付 |
|------|------|----------|
| 2 | NotebookLM adapter + doctor | `loop-apidoc doctor`、`scripts/run.py` wrapper 呼叫、輸出解析、錯誤處理（spec §4、§11） |
| 3 | 擷取 + 規格化計畫 | 分段查詢、context-bearing follow-up、`normalization-plan.json`（spec §7） |
| 4 | 產生輸出 | `openapi.yaml`、`api-guide.zh-TW.md`、`provenance.json`（spec §8） |
| 5 | 驗證 | 結構／完整性／一致性／禁止推測四類驗證 + issue code + 報告、`loop-apidoc validate`（spec §9） |
| 6 | 修正循環 + 完整 run | run directory、三輪修正、`loop-apidoc run` 完整流程與 exit code（spec §3.2、§10、§13） |

---

## Self-Review

**Spec coverage（本計畫範圍 = §2.1 來源類型、§5 manifest 命令、§6 來源 manifest）：**
- §2.1 五類來源 → Task 3 格式辨識涵蓋 PDF/Markdown/Word/OpenAPI JSON/YAML；URL → Task 5。✅
- §5 `loop-apidoc manifest --sources` → Task 7。✅
- §6 本機來源欄位（相對路徑/MIME/大小/SHA-256/掃描時間/是否支援/重複判定/處理狀態）→ Task 2 模型 + Task 4 掃描器逐欄涵蓋。✅
- §6 URL 欄位（原始 URL/擷取時間/HTTP 狀態/可用時內容雜湊）→ Task 2 模型 + Task 5 探測。✅
- §6「不支援格式不靜默略過」→ Task 4 以 `UNSUPPORTED` 狀態保留於 manifest。✅
- §11「skill data/.venv/browser state 不入庫」→ Task 1 `.gitignore`。✅
- §6「Notebook 逐檔比對」「unverified 狀態」「完整性驗證」→ **不在本計畫**，屬 Plan 2/3/5（已於後續計畫表標註）。manifest 模型刻意不含 `unverified`，因為該狀態源自 NotebookLM 比對結果，留待 Plan 3 擴充。

**Placeholder scan：** 無 TBD／TODO／「add error handling」等占位；每個程式步驟皆含完整程式碼。✅

**Type consistency：**
- `SourceFormat` / `ProcessingStatus` 列舉值在 Task 2 定義，Task 3/4 一致引用。✅
- `scan_sources(root, scanned_at)`、`probe_url(url, fetched_at, client)`、`build_manifest(sources_root, urls, generated_at, client=None)` 簽章在 Interfaces 與實作、測試三處一致。✅
- `Manifest` 欄位名（`sources_root`/`generated_at`/`local_sources`/`url_sources`）跨 Task 2/6/7 一致。✅
- CLI 以 `model_dump_json(indent=2)` 輸出，測試以 `json.loads` 解析欄位，鍵名一致。✅
