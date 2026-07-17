# Source Freshness Fingerprint Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cheap, deterministic pre-extraction gate — `record-fingerprint` + `check-freshness` — that skips the expensive parse when sources are unchanged (same OpenAPI `info.version` / same hash).

**Architecture:** A new self-contained `loop_apidoc/freshness/` package computes lightweight per-source signals (OpenAPI `info.version`, HTTP `ETag`/`Last-Modified`, `sha256`) and compares them against a `source-fingerprint.json` baseline. Two flat CLI commands drive it; only `record.py` and `report.py` write files. A skill reference documents the headless scheduled loop.

**Tech Stack:** Python ≥3.11, `uv`, pydantic v2, httpx, pyyaml, typer, pytest.

## Global Constraints

- Python `>=3.11`, managed with `uv` (no `pip`). Run tests with `uv run pytest`, lint with `uv run ruff check .`.
- Never fabricate: a source that cannot be fetched/read is `fetch_failed`/`inconclusive`, never silently `unchanged`.
- Pure functions everywhere except the two designated write exits (`freshness/record.py`, `freshness/report.py`). `signals.py` may do network reads but writes nothing; `check.py` writes nothing.
- Network: `httpx.Client(trust_env=False, follow_redirects=True)`, size-capped, accept header — mirror `loop_apidoc/openapi_snapshot.py`. Tests inject an `httpx.Client(transport=httpx.MockTransport(...))`; no real network in tests.
- pydantic models use `model_config = ConfigDict(extra="forbid")`.
- Product/user-facing strings stay `zh-TW`; code identifiers and this plan are English.
- Verdict → exit code: `unchanged`→0, `changed`→1, `inconclusive`→2.

---

## File Structure

- Create `loop_apidoc/freshness/__init__.py` — package marker + re-exports.
- Create `loop_apidoc/freshness/models.py` — enums, signals, fingerprint, report models, error.
- Create `loop_apidoc/freshness/signals.py` — pure signal helpers + comparison + network fetch.
- Create `loop_apidoc/freshness/check.py` — `check_freshness` orchestration + verdict.
- Create `loop_apidoc/freshness/record.py` — build baseline from a run-dir + write sidecar.
- Create `loop_apidoc/freshness/report.py` — write `freshness-report.{json,md}`.
- Modify `loop_apidoc/cli.py` — add `record-fingerprint` + `check-freshness` commands.
- Create `tests/test_freshness_models.py`, `tests/test_freshness_signals.py`, `tests/test_freshness_check.py`, `tests/test_freshness_record.py`, `tests/test_freshness_report.py`, `tests/test_cli_freshness.py`.
- Create `skills/loop-apidoc/reference/freshness-scheduling.md`; modify `skills/loop-apidoc/SKILL.md`.
- Modify `CLAUDE.md`, `AGENTS.md`, `README.md`, `README.en.md`, `docs/operator-manual.html`.

---

## Task 1: Freshness data models

**Files:**
- Create: `loop_apidoc/freshness/__init__.py`
- Create: `loop_apidoc/freshness/models.py`
- Test: `tests/test_freshness_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class SourceKind(str, Enum)`: `OPENAPI_URL="openapi_url"`, `WEB_URL="web_url"`, `LOCAL_FILE="local_file"`.
  - `class SourceStatus(str, Enum)`: `UNCHANGED="unchanged"`, `CHANGED="changed"`, `FETCH_FAILED="fetch_failed"`.
  - `class FreshnessVerdict(str, Enum)`: `UNCHANGED="unchanged"`, `CHANGED="changed"`, `INCONCLUSIVE="inconclusive"`.
  - `class SourceSignal(BaseModel)`: `version: str|None=None`, `etag: str|None=None`, `last_modified: str|None=None`, `sha256: str|None=None`.
  - `class FingerprintEntry(BaseModel)`: `id: str`, `kind: SourceKind`, `signal: SourceSignal`.
  - `class SourceFingerprint(BaseModel)`: `schema_version: int=1`, `openapi_version: str|None=None`, `recorded_from: str|None=None`, `sources: list[FingerprintEntry]=[]`.
  - `class SourceResult(BaseModel)`: `id: str`, `kind: SourceKind`, `status: SourceStatus`, `reason: str|None=None`.
  - `class FreshnessReport(BaseModel)`: `verdict: FreshnessVerdict`, `openapi_version: str|None`, `sources_total: int`, `unchanged_count: int`, `changed: list[SourceResult]=[]`, `inconclusive: list[SourceResult]=[]`.
  - `class FreshnessInputError(Exception)`.
  - `EXIT_CODES: dict[FreshnessVerdict, int]` = `{UNCHANGED:0, CHANGED:1, INCONCLUSIVE:2}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_freshness_models.py
import pytest
from pydantic import ValidationError

from loop_apidoc.freshness.models import (
    EXIT_CODES,
    FingerprintEntry,
    FreshnessVerdict,
    SourceFingerprint,
    SourceKind,
    SourceSignal,
    SourceStatus,
)


def test_fingerprint_roundtrip_defaults():
    fp = SourceFingerprint(
        openapi_version="2.3.0",
        recorded_from="runs/abc",
        sources=[
            FingerprintEntry(
                id="https://api.example.com/openapi.json",
                kind=SourceKind.OPENAPI_URL,
                signal=SourceSignal(version="2.3.0", etag='W/"a"', sha256="deadbeef"),
            )
        ],
    )
    assert fp.schema_version == 1
    restored = SourceFingerprint.model_validate_json(fp.model_dump_json())
    assert restored == fp
    assert restored.sources[0].signal.last_modified is None


def test_signal_forbids_extra_keys():
    with pytest.raises(ValidationError):
        SourceSignal.model_validate({"version": "1", "bogus": True})


def test_exit_codes_cover_every_verdict():
    assert EXIT_CODES[FreshnessVerdict.UNCHANGED] == 0
    assert EXIT_CODES[FreshnessVerdict.CHANGED] == 1
    assert EXIT_CODES[FreshnessVerdict.INCONCLUSIVE] == 2
    assert set(EXIT_CODES) == set(FreshnessVerdict)
    assert SourceStatus.FETCH_FAILED.value == "fetch_failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_freshness_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'loop_apidoc.freshness'`.

- [ ] **Step 3: Write minimal implementation**

```python
# loop_apidoc/freshness/__init__.py
"""Cheap source-freshness gate: fingerprint baseline + change check."""
```

```python
# loop_apidoc/freshness/models.py
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FreshnessInputError(Exception):
    """Raised when fingerprint/run-dir input is unreadable or malformed."""


class SourceKind(str, Enum):
    OPENAPI_URL = "openapi_url"
    WEB_URL = "web_url"
    LOCAL_FILE = "local_file"


class SourceStatus(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    FETCH_FAILED = "fetch_failed"


class FreshnessVerdict(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    INCONCLUSIVE = "inconclusive"


class SourceSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    sha256: str | None = None


class FingerprintEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: SourceKind
    signal: SourceSignal


class SourceFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    openapi_version: str | None = None
    recorded_from: str | None = None
    sources: list[FingerprintEntry] = Field(default_factory=list)


class SourceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: SourceKind
    status: SourceStatus
    reason: str | None = None


class FreshnessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: FreshnessVerdict
    openapi_version: str | None = None
    sources_total: int
    unchanged_count: int
    changed: list[SourceResult] = Field(default_factory=list)
    inconclusive: list[SourceResult] = Field(default_factory=list)


EXIT_CODES: dict[FreshnessVerdict, int] = {
    FreshnessVerdict.UNCHANGED: 0,
    FreshnessVerdict.CHANGED: 1,
    FreshnessVerdict.INCONCLUSIVE: 2,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_freshness_models.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/freshness/__init__.py loop_apidoc/freshness/models.py tests/test_freshness_models.py
git commit -m "feat: freshness data models"
```

---

## Task 2: Pure signal helpers (hash, OpenAPI-version detect, compare)

**Files:**
- Create: `loop_apidoc/freshness/signals.py`
- Test: `tests/test_freshness_signals.py`

**Interfaces:**
- Consumes: `models.SourceKind`, `SourceSignal`, `SourceStatus`, `FingerprintEntry`.
- Produces:
  - `def hash_bytes(raw: bytes) -> str` — hex sha256.
  - `def file_signal(path: Path) -> SourceSignal` — `SourceSignal(sha256=...)`; raises `FreshnessInputError` if unreadable.
  - `def detect_openapi(raw: bytes, content_type: str) -> tuple[bool, str | None]` — `(is_openapi, info_version_or_None)`.
  - `@dataclass(frozen=True) class ObservedSignal`: `signal: SourceSignal | None`, `not_modified: bool = False`, `failed: bool = False`, `error: str | None = None`, `kind: SourceKind | None = None`.
  - `def classify(entry: FingerprintEntry, observed: ObservedSignal) -> tuple[SourceStatus, str | None]` — pure comparison.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_freshness_signals.py
from pathlib import Path

from loop_apidoc.freshness.models import (
    FingerprintEntry,
    SourceKind,
    SourceSignal,
    SourceStatus,
)
from loop_apidoc.freshness.signals import (
    ObservedSignal,
    classify,
    detect_openapi,
    file_signal,
    hash_bytes,
)


def test_hash_bytes_stable():
    assert hash_bytes(b"abc") == hash_bytes(b"abc")
    assert hash_bytes(b"abc") != hash_bytes(b"abd")


def test_file_signal(tmp_path: Path):
    f = tmp_path / "s.pdf"
    f.write_bytes(b"hello")
    assert file_signal(f).sha256 == hash_bytes(b"hello")


def test_detect_openapi_true_and_version():
    ok, ver = detect_openapi(b'{"openapi":"3.1.0","info":{"version":"2.3.0"}}', "application/json")
    assert ok is True and ver == "2.3.0"


def test_detect_openapi_false_on_html():
    ok, ver = detect_openapi(b"<html><body>hi</body></html>", "text/html")
    assert ok is False and ver is None


def _entry(kind, **sig):
    return FingerprintEntry(id="x", kind=kind, signal=SourceSignal(**sig))


def test_classify_not_modified_is_unchanged():
    status, _ = classify(_entry(SourceKind.WEB_URL, sha256="a"), ObservedSignal(signal=None, not_modified=True))
    assert status is SourceStatus.UNCHANGED


def test_classify_failed_is_fetch_failed():
    status, reason = classify(
        _entry(SourceKind.WEB_URL, sha256="a"),
        ObservedSignal(signal=None, failed=True, error="boom"),
    )
    assert status is SourceStatus.FETCH_FAILED and "boom" in reason


def test_classify_openapi_same_version_unchanged_even_if_sha_differs():
    entry = _entry(SourceKind.OPENAPI_URL, version="2.3.0", sha256="old")
    observed = ObservedSignal(signal=SourceSignal(version="2.3.0", sha256="new"), kind=SourceKind.OPENAPI_URL)
    status, _ = classify(entry, observed)
    assert status is SourceStatus.UNCHANGED


def test_classify_openapi_version_bump_is_changed():
    entry = _entry(SourceKind.OPENAPI_URL, version="2.3.0", sha256="old")
    observed = ObservedSignal(signal=SourceSignal(version="2.4.0", sha256="old"), kind=SourceKind.OPENAPI_URL)
    status, reason = classify(entry, observed)
    assert status is SourceStatus.CHANGED and "2.3.0" in reason and "2.4.0" in reason


def test_classify_openapi_missing_version_falls_back_to_sha():
    entry = _entry(SourceKind.OPENAPI_URL, version=None, sha256="old")
    observed = ObservedSignal(signal=SourceSignal(version=None, sha256="new"), kind=SourceKind.OPENAPI_URL)
    status, _ = classify(entry, observed)
    assert status is SourceStatus.CHANGED


def test_classify_web_sha_match_unchanged():
    entry = _entry(SourceKind.WEB_URL, sha256="same")
    observed = ObservedSignal(signal=SourceSignal(sha256="same"), kind=SourceKind.WEB_URL)
    status, _ = classify(entry, observed)
    assert status is SourceStatus.UNCHANGED


def test_classify_local_sha_mismatch_changed():
    entry = _entry(SourceKind.LOCAL_FILE, sha256="a")
    observed = ObservedSignal(signal=SourceSignal(sha256="b"), kind=SourceKind.LOCAL_FILE)
    status, _ = classify(entry, observed)
    assert status is SourceStatus.CHANGED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_freshness_signals.py -v`
Expected: FAIL — `ImportError` / `cannot import name 'classify'`.

- [ ] **Step 3: Write minimal implementation**

```python
# loop_apidoc/freshness/signals.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from loop_apidoc.freshness.models import (
    FingerprintEntry,
    FreshnessInputError,
    SourceKind,
    SourceSignal,
    SourceStatus,
)


def hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_signal(path: Path) -> SourceSignal:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FreshnessInputError(f"cannot read local source {path}: {exc}") from exc
    return SourceSignal(sha256=hash_bytes(raw))


def detect_openapi(raw: bytes, content_type: str) -> tuple[bool, str | None]:
    """Return (is_openapi_document, info.version). Never raises."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return (False, None)
    is_yaml = "yaml" in content_type.lower()
    try:
        parsed = yaml.safe_load(text) if is_yaml else json.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError):
        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError:
            return (False, None)
    if not isinstance(parsed, dict):
        return (False, None)
    version_field = parsed.get("openapi")
    is_openapi = parsed.get("swagger") == "2.0" or (
        isinstance(version_field, str) and version_field.startswith("3.")
    )
    if not is_openapi:
        return (False, None)
    info = parsed.get("info")
    info_version = info.get("version") if isinstance(info, dict) else None
    return (True, info_version if isinstance(info_version, str) else None)


@dataclass(frozen=True)
class ObservedSignal:
    signal: SourceSignal | None
    not_modified: bool = False
    failed: bool = False
    error: str | None = None
    kind: SourceKind | None = None


def classify(entry: FingerprintEntry, observed: ObservedSignal) -> tuple[SourceStatus, str | None]:
    if observed.failed:
        return (SourceStatus.FETCH_FAILED, observed.error or "fetch failed")
    if observed.not_modified:
        return (SourceStatus.UNCHANGED, None)
    current = observed.signal
    if current is None:  # defensive: no signal and not a failure/304 → cannot judge
        return (SourceStatus.FETCH_FAILED, "no signal produced")

    baseline = entry.signal
    if entry.kind is SourceKind.OPENAPI_URL and baseline.version and current.version:
        if baseline.version == current.version:
            return (SourceStatus.UNCHANGED, None)
        return (SourceStatus.CHANGED, f"version {baseline.version} -> {current.version}")

    if baseline.sha256 == current.sha256:
        return (SourceStatus.UNCHANGED, None)
    return (SourceStatus.CHANGED, "content hash changed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_freshness_signals.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/freshness/signals.py tests/test_freshness_signals.py
git commit -m "feat: freshness pure signal helpers"
```

---

## Task 3: Network fetch of a URL signal (conditional GET)

**Files:**
- Modify: `loop_apidoc/freshness/signals.py`
- Test: `tests/test_freshness_signals.py` (append)

**Interfaces:**
- Consumes: `httpx`, `ObservedSignal`, `detect_openapi`, `hash_bytes`.
- Produces:
  - `def fetch_url_signal(url: str, *, client: httpx.Client, prior_etag: str | None = None, prior_last_modified: str | None = None, max_bytes: int = 5 * 1024 * 1024) -> ObservedSignal` — sends a conditional GET; on `304` returns `ObservedSignal(signal=None, not_modified=True)`; on success returns an `ObservedSignal` with `kind` (`OPENAPI_URL` when the body parses as an OpenAPI/Swagger doc, else `WEB_URL`), `signal` carrying `version`/`etag`/`last_modified`/`sha256`; on any HTTP/size error returns `ObservedSignal(signal=None, failed=True, error=...)`. Never raises for network/HTTP errors.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_freshness_signals.py  (append)
import httpx

from loop_apidoc.freshness.signals import fetch_url_signal


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def test_fetch_openapi_url_captures_version_and_kind():
    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "etag": 'W/"v1"'},
            content=b'{"openapi":"3.1.0","info":{"version":"2.3.0"}}',
        )

    with _client(handler) as c:
        obs = fetch_url_signal("https://api.example.com/openapi.json", client=c)
    assert obs.kind is SourceKind.OPENAPI_URL
    assert obs.signal.version == "2.3.0"
    assert obs.signal.etag == 'W/"v1"'
    assert obs.not_modified is False


def test_fetch_web_url_is_web_kind_with_sha():
    body = b"<html><body>docs</body></html>"

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=body)

    with _client(handler) as c:
        obs = fetch_url_signal("https://docs.example.com/webhooks", client=c)
    assert obs.kind is SourceKind.WEB_URL
    assert obs.signal.sha256 == hash_bytes(body)
    assert obs.signal.version is None


def test_fetch_304_is_not_modified():
    seen = {}

    def handler(request):
        seen["inm"] = request.headers.get("if-none-match")
        return httpx.Response(304)

    with _client(handler) as c:
        obs = fetch_url_signal("https://x", client=c, prior_etag='W/"v1"')
    assert obs.not_modified is True and obs.signal is None
    assert seen["inm"] == 'W/"v1"'


def test_fetch_http_error_is_failed_not_raised():
    def handler(request):
        return httpx.Response(500)

    with _client(handler) as c:
        obs = fetch_url_signal("https://x", client=c)
    assert obs.failed is True and obs.error


def test_fetch_oversize_is_failed():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 100)

    with _client(handler) as c:
        obs = fetch_url_signal("https://x", client=c, max_bytes=10)
    assert obs.failed is True and "cap" in obs.error.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_freshness_signals.py -k fetch -v`
Expected: FAIL — `cannot import name 'fetch_url_signal'`.

- [ ] **Step 3: Write minimal implementation**

Append to `loop_apidoc/freshness/signals.py` (add `import httpx` to the imports at the top):

```python
def fetch_url_signal(
    url: str,
    *,
    client: httpx.Client,
    prior_etag: str | None = None,
    prior_last_modified: str | None = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> ObservedSignal:
    headers: dict[str, str] = {"accept": "application/json, application/yaml, text/yaml, text/html"}
    if prior_etag:
        headers["if-none-match"] = prior_etag
    if prior_last_modified:
        headers["if-modified-since"] = prior_last_modified
    try:
        response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return ObservedSignal(signal=None, failed=True, error=f"fetch failed: {exc}")
    if response.status_code == 304:
        return ObservedSignal(signal=None, not_modified=True)
    if response.status_code >= 400:
        return ObservedSignal(signal=None, failed=True, error=f"HTTP {response.status_code}")
    raw = response.content
    if len(raw) > max_bytes:
        return ObservedSignal(signal=None, failed=True, error=f"response exceeded {max_bytes} byte cap")
    content_type = response.headers.get("content-type", "")
    is_openapi, version = detect_openapi(raw, content_type)
    signal = SourceSignal(
        version=version,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
        sha256=hash_bytes(raw),
    )
    kind = SourceKind.OPENAPI_URL if is_openapi else SourceKind.WEB_URL
    return ObservedSignal(signal=signal, kind=kind)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_freshness_signals.py -v`
Expected: PASS (all, including the new fetch tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/freshness/signals.py tests/test_freshness_signals.py
git commit -m "feat: freshness url signal fetch (conditional GET)"
```

---

## Task 4: check_freshness orchestration + verdict

**Files:**
- Create: `loop_apidoc/freshness/check.py`
- Test: `tests/test_freshness_check.py`

**Interfaces:**
- Consumes: `models.*`, `signals.classify`, `signals.file_signal`, `signals.fetch_url_signal`, `signals.ObservedSignal`.
- Produces:
  - `def check_freshness(fingerprint: SourceFingerprint, *, sources_root: Path | None = None, client: httpx.Client | None = None, max_bytes: int = 5 * 1024 * 1024) -> FreshnessReport`. For each entry: `LOCAL_FILE` → recompute via `file_signal(sources_root / id)` (if `sources_root` is None or the file is missing → `fetch_failed` with a reason, never raises); URL kinds → `fetch_url_signal(id, client=..., prior_etag=entry.signal.etag, prior_last_modified=entry.signal.last_modified)`. Aggregates: verdict is `CHANGED` if any result is `CHANGED`, else `INCONCLUSIVE` if any is `FETCH_FAILED`, else `UNCHANGED`. Owns/closes an `httpx.Client` when `client is None` (only if a URL entry exists).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_freshness_check.py
from pathlib import Path

import httpx

from loop_apidoc.freshness.models import (
    FingerprintEntry,
    FreshnessVerdict,
    SourceFingerprint,
    SourceKind,
    SourceSignal,
    SourceStatus,
)
from loop_apidoc.freshness.check import check_freshness


def _fp(*entries, openapi_version="2.3.0"):
    return SourceFingerprint(openapi_version=openapi_version, sources=list(entries))


def _openapi_entry(version, sha="old", etag=None):
    return FingerprintEntry(
        id="https://api.example.com/openapi.json",
        kind=SourceKind.OPENAPI_URL,
        signal=SourceSignal(version=version, sha256=sha, etag=etag),
    )


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def test_unchanged_when_version_matches():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json"},
                              content=b'{"openapi":"3.1.0","info":{"version":"2.3.0"}}')

    report = check_freshness(_fp(_openapi_entry("2.3.0")), client=_client(handler))
    assert report.verdict is FreshnessVerdict.UNCHANGED
    assert report.unchanged_count == 1
    assert report.sources_total == 1


def test_changed_on_version_bump():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json"},
                              content=b'{"openapi":"3.1.0","info":{"version":"2.4.0"}}')

    report = check_freshness(_fp(_openapi_entry("2.3.0")), client=_client(handler))
    assert report.verdict is FreshnessVerdict.CHANGED
    assert report.changed[0].reason == "version 2.3.0 -> 2.4.0"


def test_changed_dominates_inconclusive():
    def handler(request):
        if "openapi" in str(request.url):
            return httpx.Response(200, headers={"content-type": "application/json"},
                                  content=b'{"openapi":"3.1.0","info":{"version":"2.4.0"}}')
        return httpx.Response(500)

    web = FingerprintEntry(id="https://docs.example.com/x", kind=SourceKind.WEB_URL,
                           signal=SourceSignal(sha256="a"))
    report = check_freshness(_fp(_openapi_entry("2.3.0"), web), client=_client(handler))
    assert report.verdict is FreshnessVerdict.CHANGED
    assert len(report.inconclusive) == 1


def test_web_fetch_failure_is_inconclusive():
    def handler(request):
        return httpx.Response(503)

    web = FingerprintEntry(id="https://docs.example.com/x", kind=SourceKind.WEB_URL,
                           signal=SourceSignal(sha256="a"))
    report = check_freshness(_fp(web), client=_client(handler))
    assert report.verdict is FreshnessVerdict.INCONCLUSIVE
    assert report.inconclusive[0].status is SourceStatus.FETCH_FAILED


def test_local_file_unchanged(tmp_path: Path):
    f = tmp_path / "spec.pdf"
    f.write_bytes(b"hello")
    from loop_apidoc.freshness.signals import hash_bytes
    entry = FingerprintEntry(id="spec.pdf", kind=SourceKind.LOCAL_FILE,
                             signal=SourceSignal(sha256=hash_bytes(b"hello")))
    report = check_freshness(_fp(entry), sources_root=tmp_path)
    assert report.verdict is FreshnessVerdict.UNCHANGED


def test_local_file_missing_root_is_inconclusive():
    entry = FingerprintEntry(id="spec.pdf", kind=SourceKind.LOCAL_FILE,
                             signal=SourceSignal(sha256="x"))
    report = check_freshness(_fp(entry), sources_root=None)
    assert report.verdict is FreshnessVerdict.INCONCLUSIVE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_freshness_check.py -v`
Expected: FAIL — `ModuleNotFoundError: loop_apidoc.freshness.check`.

- [ ] **Step 3: Write minimal implementation**

```python
# loop_apidoc/freshness/check.py
from __future__ import annotations

from pathlib import Path

import httpx

from loop_apidoc.freshness.models import (
    FingerprintEntry,
    FreshnessReport,
    FreshnessVerdict,
    SourceFingerprint,
    SourceKind,
    SourceResult,
    SourceStatus,
)
from loop_apidoc.freshness.signals import (
    FreshnessInputError,
    ObservedSignal,
    classify,
    fetch_url_signal,
    file_signal,
)


def _observe_local(entry: FingerprintEntry, sources_root: Path | None) -> ObservedSignal:
    if sources_root is None:
        return ObservedSignal(signal=None, failed=True, error="--sources required for local source")
    try:
        signal = file_signal(sources_root / entry.id)
    except FreshnessInputError as exc:
        return ObservedSignal(signal=None, failed=True, error=str(exc))
    return ObservedSignal(signal=signal, kind=SourceKind.LOCAL_FILE)


def check_freshness(
    fingerprint: SourceFingerprint,
    *,
    sources_root: Path | None = None,
    client: httpx.Client | None = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> FreshnessReport:
    needs_network = any(e.kind is not SourceKind.LOCAL_FILE for e in fingerprint.sources)
    active_client = client
    owns_client = False
    if needs_network and active_client is None:
        active_client = httpx.Client(timeout=20, follow_redirects=True, trust_env=False)
        owns_client = True

    results: list[SourceResult] = []
    try:
        for entry in fingerprint.sources:
            if entry.kind is SourceKind.LOCAL_FILE:
                observed = _observe_local(entry, sources_root)
            else:
                observed = fetch_url_signal(
                    entry.id,
                    client=active_client,
                    prior_etag=entry.signal.etag,
                    prior_last_modified=entry.signal.last_modified,
                    max_bytes=max_bytes,
                )
            status, reason = classify(entry, observed)
            results.append(SourceResult(id=entry.id, kind=entry.kind, status=status, reason=reason))
    finally:
        if owns_client and active_client is not None:
            active_client.close()

    changed = [r for r in results if r.status is SourceStatus.CHANGED]
    inconclusive = [r for r in results if r.status is SourceStatus.FETCH_FAILED]
    unchanged_count = sum(1 for r in results if r.status is SourceStatus.UNCHANGED)
    if changed:
        verdict = FreshnessVerdict.CHANGED
    elif inconclusive:
        verdict = FreshnessVerdict.INCONCLUSIVE
    else:
        verdict = FreshnessVerdict.UNCHANGED

    return FreshnessReport(
        verdict=verdict,
        openapi_version=fingerprint.openapi_version,
        sources_total=len(results),
        unchanged_count=unchanged_count,
        changed=changed,
        inconclusive=inconclusive,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_freshness_check.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/freshness/check.py tests/test_freshness_check.py
git commit -m "feat: freshness check orchestration and verdict"
```

---

## Task 5: Build + write the baseline fingerprint from a run-dir

**Files:**
- Create: `loop_apidoc/freshness/record.py`
- Test: `tests/test_freshness_record.py`

**Interfaces:**
- Consumes: `models.*`, `signals.fetch_url_signal`, `Manifest` (`loop_apidoc.manifest.models`), `load_coverage` (`loop_apidoc.preparation.coverage`), `ProcessingStatus`.
- Produces:
  - `def build_fingerprint(run_dir: Path, *, client: httpx.Client | None = None, max_bytes: int = 5 * 1024 * 1024) -> SourceFingerprint`. Reads `run_dir/openapi.yaml` → `info.version`; `run_dir/manifest.json` → local sources with `status == PENDING` become `LOCAL_FILE` entries using the manifest's `sha256` (no re-hash); `run_dir/url_sources/coverage.json` (if present) → each `results` entry whose `status` is `fetched`/`fetched_rendered` is fetched once via `fetch_url_signal` (no prior validators) to capture its kind + signal. Raises `FreshnessInputError` on a missing/unreadable `openapi.yaml` or `manifest.json`, or a malformed coverage ledger.
  - `def write_fingerprint(fingerprint: SourceFingerprint, output: Path, *, force: bool = False) -> None`. Writes pretty JSON. Refuses to overwrite an existing file unless `force` (raises `FreshnessInputError`), mirroring `snapshot-openapi-url` immutability.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_freshness_record.py
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import yaml

from loop_apidoc.freshness.models import FreshnessInputError, SourceKind
from loop_apidoc.freshness.record import build_fingerprint, write_fingerprint


def _write_run_dir(tmp_path: Path, *, with_url: bool) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    (run / "openapi.yaml").write_text(
        yaml.safe_dump({"openapi": "3.1.0", "info": {"title": "X", "version": "2.3.0"}}),
        encoding="utf-8",
    )
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "spec.pdf").write_bytes(b"hello")
    manifest = {
        "sources_root": str(sources),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "local_sources": [{
            "relative_path": "spec.pdf", "mime_type": "application/pdf",
            "source_format": "pdf", "size_bytes": 5,
            "sha256": "5d41402abc4b2a76b9719d911017c592",
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "supported": True, "status": "pending",
        }],
        "url_sources": [],
    }
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if with_url:
        us = run / "url_sources"
        us.mkdir()
        cov = {
            "entry_url": "https://api.example.com/openapi.json",
            "confirmed_by_user": True,
            "expected": [{"url": "https://api.example.com/openapi.json", "source": "user"}],
            "results": [{"url": "https://api.example.com/openapi.json", "status": "fetched",
                         "file": "sources/openapi.json", "method": "direct"}],
        }
        (us / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")
    return run


def _client():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json", "etag": 'W/"v1"'},
                              content=b'{"openapi":"3.1.0","info":{"version":"2.3.0"}}')
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def test_build_local_only(tmp_path: Path):
    run = _write_run_dir(tmp_path, with_url=False)
    fp = build_fingerprint(run)
    assert fp.openapi_version == "2.3.0"
    assert len(fp.sources) == 1
    entry = fp.sources[0]
    assert entry.kind is SourceKind.LOCAL_FILE
    assert entry.id == "spec.pdf"
    assert entry.signal.sha256 == "5d41402abc4b2a76b9719d911017c592"


def test_build_with_url_source(tmp_path: Path):
    run = _write_run_dir(tmp_path, with_url=True)
    with _client() as c:
        fp = build_fingerprint(run, client=c)
    kinds = {e.kind for e in fp.sources}
    assert SourceKind.OPENAPI_URL in kinds and SourceKind.LOCAL_FILE in kinds
    url_entry = next(e for e in fp.sources if e.kind is SourceKind.OPENAPI_URL)
    assert url_entry.signal.version == "2.3.0"
    assert url_entry.signal.etag == 'W/"v1"'


def test_build_missing_openapi_raises(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(FreshnessInputError):
        build_fingerprint(tmp_path / "empty")


def test_write_fingerprint_refuses_overwrite(tmp_path: Path):
    run = _write_run_dir(tmp_path, with_url=False)
    fp = build_fingerprint(run)
    out = tmp_path / "fp.json"
    write_fingerprint(fp, out)
    with pytest.raises(FreshnessInputError):
        write_fingerprint(fp, out)
    write_fingerprint(fp, out, force=True)  # ok
    assert json.loads(out.read_text())["openapi_version"] == "2.3.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_freshness_record.py -v`
Expected: FAIL — `ModuleNotFoundError: loop_apidoc.freshness.record`.

- [ ] **Step 3: Write minimal implementation**

```python
# loop_apidoc/freshness/record.py
from __future__ import annotations

import json
from pathlib import Path

import httpx
import yaml

from loop_apidoc.freshness.models import (
    FingerprintEntry,
    FreshnessInputError,
    SourceFingerprint,
    SourceKind,
    SourceSignal,
)
from loop_apidoc.freshness.signals import fetch_url_signal
from loop_apidoc.manifest.models import Manifest, ProcessingStatus
from loop_apidoc.preparation.coverage import CoverageInputError, ResultStatus, load_coverage

_USABLE_URL_STATUSES = {ResultStatus.FETCHED, ResultStatus.FETCHED_RENDERED}


def _read_openapi_version(run_dir: Path) -> str | None:
    path = run_dir / "openapi.yaml"
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FreshnessInputError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise FreshnessInputError(f"openapi.yaml is not valid YAML: {exc}") from exc
    info = doc.get("info") if isinstance(doc, dict) else None
    version = info.get("version") if isinstance(info, dict) else None
    return version if isinstance(version, str) else None


def _load_manifest(run_dir: Path) -> Manifest:
    path = run_dir / "manifest.json"
    try:
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FreshnessInputError(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise FreshnessInputError(f"manifest.json schema error: {exc}") from exc


def build_fingerprint(
    run_dir: Path,
    *,
    client: httpx.Client | None = None,
    max_bytes: int = 5 * 1024 * 1024,
) -> SourceFingerprint:
    openapi_version = _read_openapi_version(run_dir)
    manifest = _load_manifest(run_dir)

    entries: list[FingerprintEntry] = []
    for src in manifest.local_sources:
        if src.status is not ProcessingStatus.PENDING:
            continue
        entries.append(FingerprintEntry(
            id=src.relative_path,
            kind=SourceKind.LOCAL_FILE,
            signal=SourceSignal(sha256=src.sha256),
        ))

    coverage_path = run_dir / "url_sources" / "coverage.json"
    url_ids: list[str] = []
    if coverage_path.exists():
        try:
            coverage = load_coverage(coverage_path)
        except CoverageInputError as exc:
            raise FreshnessInputError(str(exc)) from exc
        seen: set[str] = set()
        for result in coverage.results:
            if result.status in _USABLE_URL_STATUSES and result.url not in seen:
                seen.add(result.url)
                url_ids.append(result.url)

    if url_ids:
        active_client = client or httpx.Client(timeout=20, follow_redirects=True, trust_env=False)
        owns_client = client is None
        try:
            for url in url_ids:
                observed = fetch_url_signal(url, client=active_client, max_bytes=max_bytes)
                if observed.failed or observed.signal is None:
                    raise FreshnessInputError(
                        f"cannot capture baseline signal for {url}: {observed.error or 'no signal'}"
                    )
                entries.append(FingerprintEntry(
                    id=url,
                    kind=observed.kind or SourceKind.WEB_URL,
                    signal=observed.signal,
                ))
        finally:
            if owns_client:
                active_client.close()

    return SourceFingerprint(
        openapi_version=openapi_version,
        recorded_from=run_dir.name,
        sources=entries,
    )


def write_fingerprint(fingerprint: SourceFingerprint, output: Path, *, force: bool = False) -> None:
    if output.exists() and not force:
        raise FreshnessInputError(f"fingerprint already exists: {output} (use --force to overwrite)")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(fingerprint.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_freshness_record.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/freshness/record.py tests/test_freshness_record.py
git commit -m "feat: build and write baseline source fingerprint"
```

---

## Task 6: Freshness report rendering

**Files:**
- Create: `loop_apidoc/freshness/report.py`
- Test: `tests/test_freshness_report.py`

**Interfaces:**
- Consumes: `FreshnessReport`, `SourceResult`.
- Produces:
  - `def render_markdown(report: FreshnessReport) -> str` — a `zh-TW` summary with verdict, openapi_version, counts, and a table of changed/inconclusive sources.
  - `def write_reports(report: FreshnessReport, report_dir: Path) -> tuple[Path, Path]` — writes `report_dir/freshness-report.json` and `freshness-report.md`, returns their paths.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_freshness_report.py
from pathlib import Path

from loop_apidoc.freshness.models import (
    FreshnessReport,
    FreshnessVerdict,
    SourceKind,
    SourceResult,
    SourceStatus,
)
from loop_apidoc.freshness.report import render_markdown, write_reports


def _report():
    return FreshnessReport(
        verdict=FreshnessVerdict.CHANGED,
        openapi_version="2.3.0",
        sources_total=2,
        unchanged_count=1,
        changed=[SourceResult(id="https://api/x", kind=SourceKind.OPENAPI_URL,
                              status=SourceStatus.CHANGED, reason="version 2.3.0 -> 2.4.0")],
        inconclusive=[],
    )


def test_render_markdown_mentions_verdict_and_reason():
    md = render_markdown(_report())
    assert "changed" in md
    assert "version 2.3.0 -> 2.4.0" in md


def test_write_reports(tmp_path: Path):
    json_path, md_path = write_reports(_report(), tmp_path)
    assert json_path.exists() and md_path.exists()
    assert '"verdict": "changed"' in json_path.read_text(encoding="utf-8")
    assert md_path.read_text(encoding="utf-8").startswith("#")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_freshness_report.py -v`
Expected: FAIL — `ModuleNotFoundError: loop_apidoc.freshness.report`.

- [ ] **Step 3: Write minimal implementation**

```python
# loop_apidoc/freshness/report.py
from __future__ import annotations

from pathlib import Path

from loop_apidoc.freshness.models import FreshnessReport, SourceResult


def _rows(results: list[SourceResult]) -> list[str]:
    return [f"| `{r.id}` | {r.kind.value} | {r.status.value} | {r.reason or '-'} |" for r in results]


def render_markdown(report: FreshnessReport) -> str:
    lines = [
        "# 來源新鮮度檢查",
        "",
        f"- 判定:**{report.verdict.value}**",
        f"- OpenAPI 版本:`{report.openapi_version or '-'}`",
        f"- 來源總數:{report.sources_total};未變:{report.unchanged_count};"
        f"變動:{len(report.changed)};無法判定:{len(report.inconclusive)}",
    ]
    flagged = report.changed + report.inconclusive
    if flagged:
        lines += ["", "| 來源 | 類型 | 狀態 | 原因 |", "| --- | --- | --- | --- |", *_rows(flagged)]
    return "\n".join(lines) + "\n"


def write_reports(report: FreshnessReport, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "freshness-report.json"
    md_path = report_dir / "freshness-report.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return (json_path, md_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_freshness_report.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/freshness/report.py tests/test_freshness_report.py
git commit -m "feat: freshness report rendering"
```

---

## Task 7: CLI commands `record-fingerprint` + `check-freshness`

**Files:**
- Modify: `loop_apidoc/cli.py` (add two `@app.command(...)` functions; place them after the `snapshot-openapi-url` command block, ~line 230)
- Test: `tests/test_cli_freshness.py`

**Interfaces:**
- Consumes: `build_fingerprint`, `write_fingerprint` (record), `SourceFingerprint`, `check_freshness`, `write_reports`, `EXIT_CODES`, `FreshnessInputError`.
- Produces two Typer commands:
  - `record-fingerprint --run-dir <dir> --output <path> [--force]` → builds + writes the baseline; on `FreshnessInputError` prints to stderr and exits 2.
  - `check-freshness --fingerprint <path> [--sources <dir>] [--json] [--report-dir <dir>]` → loads the fingerprint (`SourceFingerprint.model_validate_json`, fail-loud → exit 2), runs `check_freshness`, prints human summary or `--json`, optionally writes reports, and `raise typer.Exit(code=EXIT_CODES[verdict])`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_freshness.py
import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app
from loop_apidoc.freshness.models import SourceFingerprint
from loop_apidoc.freshness.signals import hash_bytes

runner = CliRunner()


def _local_fingerprint(tmp_path: Path, sha: str) -> Path:
    fp = SourceFingerprint(
        openapi_version="2.3.0",
        sources=[{"id": "spec.pdf", "kind": "local_file", "signal": {"sha256": sha}}],
    )
    out = tmp_path / "fp.json"
    out.write_text(fp.model_dump_json(indent=2), encoding="utf-8")
    return out


def test_check_freshness_unchanged_exit_0(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "spec.pdf").write_bytes(b"hello")
    fp = _local_fingerprint(tmp_path, hash_bytes(b"hello"))
    result = runner.invoke(app, ["check-freshness", "--fingerprint", str(fp),
                                 "--sources", str(sources), "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["verdict"] == "unchanged"


def test_check_freshness_changed_exit_1(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "spec.pdf").write_bytes(b"CHANGED")
    fp = _local_fingerprint(tmp_path, hash_bytes(b"hello"))
    result = runner.invoke(app, ["check-freshness", "--fingerprint", str(fp),
                                 "--sources", str(sources)])
    assert result.exit_code == 1


def test_check_freshness_inconclusive_exit_2(tmp_path: Path):
    fp = _local_fingerprint(tmp_path, hash_bytes(b"hello"))  # no --sources
    result = runner.invoke(app, ["check-freshness", "--fingerprint", str(fp)])
    assert result.exit_code == 2


def test_check_freshness_bad_fingerprint_exit_2(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = runner.invoke(app, ["check-freshness", "--fingerprint", str(bad)])
    assert result.exit_code == 2


def test_record_fingerprint_writes_and_refuses_overwrite(tmp_path: Path, monkeypatch):
    # Build a minimal run-dir (local-only, no network).
    import yaml
    from datetime import datetime, timezone
    run = tmp_path / "run"
    run.mkdir()
    run.joinpath("openapi.yaml").write_text(
        yaml.safe_dump({"openapi": "3.1.0", "info": {"version": "2.3.0"}}), encoding="utf-8")
    manifest = {
        "sources_root": "s", "generated_at": datetime.now(timezone.utc).isoformat(),
        "local_sources": [], "url_sources": [],
    }
    run.joinpath("manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "fp.json"
    r1 = runner.invoke(app, ["record-fingerprint", "--run-dir", str(run), "--output", str(out)])
    assert r1.exit_code == 0 and out.exists()
    r2 = runner.invoke(app, ["record-fingerprint", "--run-dir", str(run), "--output", str(out)])
    assert r2.exit_code == 2  # refuses overwrite
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_freshness.py -v`
Expected: FAIL — no such command `check-freshness`.

- [ ] **Step 3: Write minimal implementation**

Add to `loop_apidoc/cli.py` (after the `snapshot-openapi-url` command). Keep imports local to the function bodies, matching the file's existing style:

```python
@app.command(name="record-fingerprint")
def record_fingerprint_command(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False, help="已完成的 run 目錄"),
    output: Path = typer.Option(..., "--output", help="輸出的 source-fingerprint.json"),
    force: bool = typer.Option(False, "--force", help="覆寫既有 fingerprint"),
) -> None:
    """從 run 目錄擷取各來源便宜訊號,寫成基準 fingerprint 側檔。"""
    from loop_apidoc.freshness.models import FreshnessInputError
    from loop_apidoc.freshness.record import build_fingerprint, write_fingerprint

    try:
        fingerprint = build_fingerprint(run_dir)
        write_fingerprint(fingerprint, output, force=force)
    except FreshnessInputError as exc:
        typer.echo(f"record-fingerprint error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"fingerprint 已寫入 {output};OpenAPI 版本 {fingerprint.openapi_version or '-'};"
        f"來源 {len(fingerprint.sources)} 筆"
    )


@app.command(name="check-freshness")
def check_freshness_command(
    fingerprint: Path = typer.Option(..., "--fingerprint", exists=True, readable=True, help="基準 fingerprint 側檔"),
    sources: Path | None = typer.Option(None, "--sources", help="本地來源根目錄(fingerprint 含本地檔時必填)"),
    json_output: bool = typer.Option(False, "--json", help="輸出機器可讀 JSON"),
    report_dir: Path | None = typer.Option(None, "--report-dir", help="另存 freshness-report.{json,md}"),
) -> None:
    """比對來源當下訊號與基準,回報是否需要重新解析(退出碼 0/1/2)。"""
    from loop_apidoc.freshness.check import check_freshness
    from loop_apidoc.freshness.models import EXIT_CODES, FreshnessInputError, SourceFingerprint
    from loop_apidoc.freshness.report import render_markdown, write_reports

    try:
        loaded = SourceFingerprint.model_validate_json(fingerprint.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        typer.echo(f"check-freshness error: 無法讀取 fingerprint: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        report = check_freshness(loaded, sources_root=sources)
    except FreshnessInputError as exc:  # defensive; check_freshness normally returns a report
        typer.echo(f"check-freshness error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if report_dir is not None:
        write_reports(report, report_dir)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_markdown(report))
    raise typer.Exit(code=EXIT_CODES[report.verdict])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_freshness.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the full suite + lint**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add loop_apidoc/cli.py tests/test_cli_freshness.py
git commit -m "feat: record-fingerprint and check-freshness CLI commands"
```

---

## Task 8: Skill reference for headless scheduling

**Files:**
- Create: `skills/loop-apidoc/reference/freshness-scheduling.md`
- Modify: `skills/loop-apidoc/SKILL.md`

**Interfaces:**
- Consumes: nothing (documentation).
- Produces: a reference doc + a SKILL pointer that a scheduled headless agent reads.

- [ ] **Step 1: Write the reference doc**

Create `skills/loop-apidoc/reference/freshness-scheduling.md` (English, token-economical, matching sibling reference docs). It must document:
- Purpose: a cheap gate so scheduled re-checks skip extraction when sources are unchanged.
- The two commands with the `<APIDOC>` placeholder:
  - `<APIDOC> record-fingerprint --run-dir <run> --output <run>/source-fingerprint.json` — run once after a run is generated and adopted.
  - `<APIDOC> check-freshness --fingerprint <path> [--sources <dir>] --json` — run on a schedule.
- Exit-code contract: `0` unchanged → **stop, no cost**; `1` changed → re-run the extraction pipeline (SKILL orchestration), then `record-fingerprint --force` to refresh the baseline; `2` inconclusive → alert a human (source unreachable / auth / moved).
- The headless loop shape (pseudocode): a scheduled agent invokes `check-freshness`, branches on exit code, and only pays for extraction on `1`.
- Note the v1 limits from the spec: raw-body hash for HTML (no normalization yet); no added/removed-source detection — a brand-new page without an OpenAPI `info.version` bump is caught only at the next `record-fingerprint`.

- [ ] **Step 2: Add a SKILL.md pointer**

In `skills/loop-apidoc/SKILL.md`, add a short bullet under the command/reference listing pointing to `reference/freshness-scheduling.md` and naming the two commands as the scheduled-freshness gate. Keep it to 2-3 lines (token economy).

- [ ] **Step 3: Verify the reference is internally consistent**

Run: `rg -n "check-freshness|record-fingerprint" skills/loop-apidoc/`
Expected: both commands appear in `SKILL.md` and `reference/freshness-scheduling.md`; exit-code contract present.

- [ ] **Step 4: Commit**

```bash
git add skills/loop-apidoc/reference/freshness-scheduling.md skills/loop-apidoc/SKILL.md
git commit -m "docs: skill reference for freshness scheduling gate"
```

---

## Task 9: Sync teaching & promotion docs (release policy)

**Files:**
- Modify: `CLAUDE.md`, `AGENTS.md`, `README.md`, `README.en.md`, `docs/operator-manual.html`

**Interfaces:**
- Consumes: nothing (documentation).
- Produces: docs consistent with the two new commands + the new `freshness/` package.

- [ ] **Step 1: Update `CLAUDE.md`**

- Add a `loop_apidoc/freshness/` row to the Package boundaries table describing `models.py` / `signals.py` / `record.py` / `check.py` / `report.py`.
- In the **File-I/O exits** paragraph, add `freshness/record.py` (`write_fingerprint`) and `freshness/report.py` (`write_reports`) to the write-exits list, and note `signals.py` does network reads but writes nothing and `check.py` writes nothing (read-side/pure).
- In the Commands / execution-model command list, add `record-fingerprint` and `check-freshness` to the **source acquisition & quality (pre-extraction)** group with a one-line description and the 0/1/2 exit-code contract.

- [ ] **Step 2: Mirror the change into `AGENTS.md`**

Apply the equivalent additions so `AGENTS.md` and `CLAUDE.md` stay aligned (per the repo's non-negotiable sync rule).

- [ ] **Step 3: Update `README.md` and `README.en.md`**

Add the two commands to the command list/tables with a one-line purpose and the scheduled-gate use case (skip parse when `info.version` unchanged). `README.md` in `zh-TW`, `README.en.md` in English.

- [ ] **Step 4: Update `docs/operator-manual.html`**

Add a short subsection describing the freshness gate: when to `record-fingerprint`, how to schedule `check-freshness`, and the exit-code contract. Match the surrounding HTML structure/style.

- [ ] **Step 5: Verify + lint pass**

Run: `uv run pytest -q && rg -n "check-freshness" CLAUDE.md AGENTS.md README.md README.en.md docs/operator-manual.html`
Expected: tests pass; the command appears in every listed doc.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md AGENTS.md README.md README.en.md docs/operator-manual.html
git commit -m "docs: document freshness gate commands (record-fingerprint, check-freshness)"
```

---

## Release note (out of plan scope)

The version bump is a separate release action, not part of this feature plan. When
releasing, run `scripts/release.py prepare` (needs a clean worktree — temporarily move
`runs/`, `tmp/`, `.loop-apidoc/`), then `tag`, and cross-check `docs/RELEASE_CHECKLIST.md`.
Task 9 already covers the human-facing teaching/promotion docs the script does **not** touch.

---

## Self-Review

- **Spec coverage:** package `freshness/` (Tasks 1–6) ✓; two CLI commands + exit codes (Task 7) ✓; fingerprint schema (Task 1 models + Task 5 writer) ✓; signal tiers openapi_url/web_url/local_file (Tasks 2–4) ✓; verdict aggregation + precedence (Task 4) ✓; skill scheduling doc (Task 8) ✓; release doc sync (Task 9) ✓; follow-ups (HTML normalization, added/removed) left explicitly out of scope in the spec and not implemented ✓.
- **Placeholder scan:** every code step shows complete code; docs tasks (8, 9) enumerate exact required content rather than "etc." ✓.
- **Type consistency:** `SourceKind`/`SourceSignal`/`FingerprintEntry`/`SourceFingerprint`/`SourceResult`/`FreshnessReport`/`FreshnessVerdict`/`SourceStatus`/`ObservedSignal`/`classify`/`fetch_url_signal`/`file_signal`/`build_fingerprint`/`write_fingerprint`/`check_freshness`/`render_markdown`/`write_reports`/`EXIT_CODES` are used with identical names/signatures across tasks ✓.
