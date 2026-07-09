# Extraction Write Contract + `verify-extraction` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let endpoint subagents write their own `endpoints/ep<N>.json`, and make that safe by adding cross-file invariants to the assemble input boundary plus a standalone `verify-extraction` command that runs the same boundary.

**Architecture:** A new pure module `loop_apidoc/agentcli/cross_file.py` adds five cross-file invariants (endpoint files ↔ inventory). A new pure aggregator `loop_apidoc/agentcli/gate.py::check_extraction` composes `source_guard` + `cross_file` into one function. `assemble` calls it instead of `check_extraction_inputs`; a new `verify-extraction` CLI command calls the same function via a thin `loop_apidoc/agentcli/verify.py` that builds a manifest and loads the extraction dir but writes nothing and creates no run directory. Finally `SKILL.md` relaxes the subagent write contract for endpoint files only.

**Tech Stack:** Python ≥3.11, `uv`, typer, pydantic v2, pytest.

## Global Constraints

- Every new module in `loop_apidoc/agentcli/` except `verify.py` is **pure**: no file I/O. `verify.py` reads (manifest scan + extraction dir) and writes nothing.
- All five cross-file invariants are `error` severity: a violation → `AssembleInputError` → CLI `exit 2`, and **no run directory is created**.
- `verify-extraction` exits `0` when clean, `2` on any violation or hard schema error. Never `1` (`1` means validation FAIL).
- Violations of path/source/cross-file kinds are **collected and reported together**. Hard schema errors (malformed JSON, wrong types) still abort on the first one from `load_extraction_inputs`.
- Index-strict `ep<N>.json` ↔ `inventory.endpoints[N]` correspondence is **out of scope** — do not implement it. Filename ordering carries no meaning.
- Endpoints with `path: null` (webhooks/callbacks — the documented shape) are **exempt from invariants 2 and 3**: they carry no comparable key, so "the same endpoint twice" is undefined for them at this layer. They still count toward invariant 1 and are still subject to invariants 4 and 5.
- Do **not** relax the write contract for `inventory.json` or `integration.json`.
- Code comments and docs: Traditional Chinese (Taiwan). `skills/loop-apidoc/SKILL.md` stays English.
- TDD: red before green. Commit after each task.
- Lint clean: `uv run ruff check .`

---

### Task 1: Cross-file invariants module

**Files:**
- Create: `loop_apidoc/agentcli/cross_file.py`
- Test: `tests/agentcli/test_cross_file.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `cross_file_violations(inventory: dict, endpoints: list[tuple[str, dict]]) -> list[str]` — `endpoints` is a list of `(filename, parsed_json)` pairs, the same shape `source_guard.check_extraction_inputs` already takes. Returns human-readable violation strings, empty when clean.

- [ ] **Step 1: Write the failing tests**

Create `tests/agentcli/test_cross_file.py`:

```python
from __future__ import annotations

from loop_apidoc.agentcli.cross_file import cross_file_violations


def _inv(*endpoints: dict, schemas=(), security_schemes=()) -> dict:
    return {
        "endpoints": list(endpoints),
        "schemas": [{"name": n} for n in schemas],
        "security_schemes": [{"name": n} for n in security_schemes],
    }


def _ep(method: str = "GET", path: str = "/ping", **extra) -> dict:
    return {"method": method, "path": path, **extra}


def test_clean_extraction_has_no_violations():
    inventory = _inv(_ep("GET", "/ping"), _ep("POST", "/orders"))
    endpoints = [("ep0.json", _ep("GET", "/ping")),
                 ("ep1.json", _ep("POST", "/orders"))]

    assert cross_file_violations(inventory, endpoints) == []


def test_method_case_is_normalized():
    inventory = _inv(_ep("get", "/ping"))
    endpoints = [("ep0.json", _ep("GET", "/ping"))]

    assert cross_file_violations(inventory, endpoints) == []


# ── 不變式 1:數量 ────────────────────────────────────────────────────

def test_missing_endpoint_file_is_a_violation():
    """一個 subagent 死掉、什麼都沒寫。"""
    inventory = _inv(_ep("GET", "/ping"), _ep("POST", "/orders"))
    endpoints = [("ep0.json", _ep("GET", "/ping"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("1" in v and "2" in v for v in violations)
    assert any("endpoints/*.json" in v for v in violations)


# ── 不變式 2:(method, path) 多重集合相等 ─────────────────────────────

def test_endpoint_file_not_in_inventory_is_a_violation():
    inventory = _inv(_ep("GET", "/ping"))
    endpoints = [("ep0.json", _ep("GET", "/pong"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("GET /pong" in v and "ep0.json" in v for v in violations)


def test_inventory_endpoint_with_no_file_is_a_violation():
    inventory = _inv(_ep("GET", "/ping"), _ep("POST", "/orders"))
    endpoints = [("ep0.json", _ep("GET", "/ping")), ("ep1.json", _ep("GET", "/ping"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("POST /orders" in v for v in violations)


# ── 不變式 3:端點檔之間不得重複 ───────────────────────────────────────

def test_two_files_writing_the_same_endpoint_is_a_violation():
    """真正會掉資料的失效模式:兩個 subagent 寫同一個端點,第三個端點沒人寫。"""
    inventory = _inv(_ep("GET", "/ping"), _ep("POST", "/orders"))
    endpoints = [("ep0.json", _ep("GET", "/ping")), ("ep1.json", _ep("GET", "/ping"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("ep0.json" in v and "ep1.json" in v and "GET /ping" in v
               for v in violations)


def test_duplicate_endpoint_is_not_reported_as_missing_from_inventory():
    """重複寫入的端點確實在 inventory 中——只能報「重複」,不可報「不在 inventory」。"""
    inventory = _inv(_ep("GET", "/ping"), _ep("POST", "/orders"))
    endpoints = [("ep0.json", _ep("GET", "/ping")), ("ep1.json", _ep("GET", "/ping"))]

    violations = cross_file_violations(inventory, endpoints)

    assert not any("不在 inventory.endpoints" in v for v in violations)
    assert any("被寫進多個檔案" in v for v in violations)
    assert any("POST /orders" in v for v in violations)


# ── 不變式 4:schema_ref 必須指向 inventory.schemas[].name ─────────────

def test_request_schema_ref_must_resolve():
    inventory = _inv(_ep(), schemas=("Order",))
    endpoints = [("ep0.json", _ep(request={"schema_ref": "Ordr"}))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("ep0.json" in v and "schema_ref" in v and "Ordr" in v
               for v in violations)


def test_response_schema_ref_must_resolve():
    inventory = _inv(_ep(), schemas=("Order",))
    endpoints = [("ep0.json", _ep(responses=[{"status": "200", "schema_ref": "Nope"}]))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("responses[0].schema_ref" in v for v in violations)


def test_resolving_schema_refs_pass():
    inventory = _inv(_ep(), schemas=("Order",))
    endpoints = [("ep0.json", _ep(request={"schema_ref": "Order"},
                                  responses=[{"schema_ref": "Order"}]))]

    assert cross_file_violations(inventory, endpoints) == []


def test_null_schema_ref_is_allowed():
    inventory = _inv(_ep())
    endpoints = [("ep0.json", _ep(request={"schema_ref": None}, responses=[{}]))]

    assert cross_file_violations(inventory, endpoints) == []


# ── 不變式 5:security[] 必須指向 inventory.security_schemes[].name ────

def test_unknown_security_scheme_is_a_violation():
    inventory = _inv(_ep(), security_schemes=("apiKey",))
    endpoints = [("ep0.json", _ep(security=["oauth2"]))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("ep0.json" in v and "security[0]" in v and "oauth2" in v
               for v in violations)


def test_known_security_scheme_passes():
    inventory = _inv(_ep(), security_schemes=("apiKey",))
    endpoints = [("ep0.json", _ep(security=["apiKey"]))]

    assert cross_file_violations(inventory, endpoints) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agentcli/test_cross_file.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'loop_apidoc.agentcli.cross_file'`

- [ ] **Step 3: Write the implementation**

Create `loop_apidoc/agentcli/cross_file.py`:

```python
"""Cross-file invariants between `endpoints/*.json` and `inventory.json`.

Endpoint subagents write their own file, so the orchestrator no longer sees each
endpoint's JSON pass through its context. What it loses in carriage it must regain
in verification: these five invariants catch every failure mode that *loses data* —
a subagent that died, one that wrote an endpoint nobody asked for, two that wrote
the same endpoint, or one that invented a schema/security name.

Deliberately set-based, never index-based: generation keys on `method`/`path` and
never on the filename, so two files' contents being swapped has no downstream
consequence and must not be rejected.

Pure: no file I/O. Callers turn the returned messages into `AssembleInputError`.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def _entries(payload: dict | None, section: str) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    return [e for e in (payload.get(section) or []) if isinstance(e, dict)]


def _key(entry: dict) -> str:
    """`(method, path)` 正規化為一個可讀的比對鍵;method 大小寫不敏感。"""
    method = entry.get("method")
    method = method.upper() if isinstance(method, str) else "?"
    path = entry.get("path")
    path = path if isinstance(path, str) else "?"
    return f"{method} {path}"


def _names(payload: dict, section: str) -> set[str]:
    return {
        e["name"] for e in _entries(payload, section)
        if isinstance(e.get("name"), str)
    }


def _count_violations(inventory: dict, endpoints: list[tuple[str, dict]]) -> list[str]:
    expected = len(_entries(inventory, "endpoints"))
    actual = len(endpoints)
    if expected == actual:
        return []
    return [
        f"endpoints/*.json 檔數 {actual} 不等於 inventory.endpoints 筆數 {expected}"
        "(每個 inventory 端點恰好一個檔;可能有 subagent 未寫出檔案)"
    ]


def _multiset_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    inventory_keys = Counter(_key(e) for e in _entries(inventory, "endpoints"))
    file_keys = Counter(_key(ep) for _, ep in endpoints)

    out: list[str] = []
    # 集合差,不是 Counter 差:同一端點被寫進兩個檔時,它「確實在」inventory 中,
    # 只是被寫了兩次——那由 _duplicate_violations 專責回報。
    for key in sorted(set(file_keys) - set(inventory_keys)):
        files = sorted(name for name, ep in endpoints if _key(ep) == key)
        out.append(
            f"{', '.join(files)}: 端點 {key} 不在 inventory.endpoints 中"
        )
    for key in sorted(set(inventory_keys) - set(file_keys)):
        out.append(
            f"inventory.json: 端點 {key} 沒有對應的 endpoints/*.json"
        )
    return out


def _duplicate_violations(endpoints: list[tuple[str, dict]]) -> list[str]:
    seen: dict[str, list[str]] = {}
    for name, endpoint in endpoints:
        seen.setdefault(_key(endpoint), []).append(name)
    return [
        f"{', '.join(sorted(files))}: 同一端點 {key} 被寫進多個檔案"
        "(兩個 subagent 寫了同一個端點,另一個端點可能因此沒人寫)"
        for key, files in sorted(seen.items()) if len(files) > 1
    ]


def _schema_refs(endpoint: dict) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    request = endpoint.get("request")
    if isinstance(request, dict):
        out.append(("request.schema_ref", request.get("schema_ref")))
    responses = endpoint.get("responses")
    if isinstance(responses, list):
        for idx, response in enumerate(responses):
            if isinstance(response, dict):
                out.append((f"responses[{idx}].schema_ref",
                            response.get("schema_ref")))
    return out


def _reference_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    schema_names = _names(inventory, "schemas")
    scheme_names = _names(inventory, "security_schemes")

    out: list[str] = []
    for name, endpoint in endpoints:
        for field, ref in _schema_refs(endpoint):
            if isinstance(ref, str) and ref not in schema_names:
                out.append(
                    f"{name}: {field} 未指向任何 inventory.schemas[].name:{ref!r}"
                )
        security = endpoint.get("security")
        if isinstance(security, list):
            for idx, scheme in enumerate(security):
                if isinstance(scheme, str) and scheme not in scheme_names:
                    out.append(
                        f"{name}: security[{idx}] 未指向任何 "
                        f"inventory.security_schemes[].name:{scheme!r}"
                    )
    return out


def cross_file_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    """一次列出所有跨檔違規——修正是一次重寫擷取 JSON,不是逐筆往返。"""
    return (
        _count_violations(inventory, endpoints)
        + _multiset_violations(inventory, endpoints)
        + _duplicate_violations(endpoints)
        + _reference_violations(inventory, endpoints)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agentcli/test_cross_file.py -v && uv run ruff check .`
Expected: PASS (13 tests), ruff clean.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/agentcli/cross_file.py tests/agentcli/test_cross_file.py
git commit -m "feat: [agentcli] 新增 endpoints↔inventory 跨檔不變式"
```

---

### Task 2: The gate — one aggregator, wired into `assemble`

**Files:**
- Create: `loop_apidoc/agentcli/gate.py`
- Test: `tests/agentcli/test_gate.py`
- Modify: `loop_apidoc/agentcli/assemble.py` (rename `_named_endpoints` → `named_endpoints`; call `check_extraction` at lines 220–226)
- Test: `tests/agentcli/test_assemble_boundary.py` (append one test)

**Interfaces:**
- Consumes: `cross_file.cross_file_violations` (Task 1); existing `source_guard.check_extraction_inputs`.
- Produces:
  - `gate.check_extraction(inventory: dict, endpoints: list[tuple[str, dict]], integration: dict | None, manifest: Manifest) -> list[str]`
  - `assemble.named_endpoints(extraction_dir: Path, endpoint_texts: list[str]) -> list[tuple[str, dict]]` (public rename of `_named_endpoints`)

- [ ] **Step 1: Write the failing tests**

Create `tests/agentcli/test_gate.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.agentcli.gate import check_extraction
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)

_AT = datetime(2026, 7, 9, tzinfo=timezone.utc)


def _local(path: str) -> LocalSource:
    return LocalSource(
        relative_path=path,
        mime_type="application/pdf",
        source_format=SourceFormat.PDF,
        size_bytes=1,
        sha256="a" * 64,
        scanned_at=_AT,
        supported=True,
        status=ProcessingStatus.PENDING,
    )


def _manifest(*paths: str) -> Manifest:
    return Manifest(
        sources_root="/s", generated_at=_AT,
        local_sources=[_local(p) for p in paths],
    )


def test_clean_input_has_no_violations():
    manifest = _manifest("a.pdf", "b.pdf")
    inventory = {"endpoints": [{"method": "GET", "path": "/ping",
                                "source": "a.pdf p.1"}]}
    endpoints = [("ep0.json", {"method": "GET", "path": "/ping",
                               "source": "a.pdf p.1"})]

    assert check_extraction(inventory, endpoints, None, manifest) == []


def test_violations_from_two_layers_are_reported_together():
    """一份輸入同時違反 source_guard(path 未以 / 開頭)與 cross_file
    (端點檔不在 inventory)→ 兩層的違規都要出現,不是遇到第一層就停。"""
    manifest = _manifest("a.pdf", "b.pdf")
    inventory = {"endpoints": [{"method": "GET", "path": "api/ping",
                                "source": "a.pdf p.1"}]}
    endpoints = [("ep0.json", {"method": "GET", "path": "/pong",
                               "source": "a.pdf p.1"})]

    violations = check_extraction(inventory, endpoints, None, manifest)

    assert any("endpoints[0].path" in v for v in violations)   # source_guard 層
    assert any("GET /pong" in v for v in violations)            # cross_file 層
```

Append to `tests/agentcli/test_assemble_boundary.py`:

```python
def test_duplicate_endpoint_files_fail_before_any_run_dir_exists(tmp_path):
    """兩個檔案寫同一個端點 → 跨檔不變式在建立 run 目錄前擋下。"""
    sources, extraction, out = _setup(tmp_path)
    (extraction / "endpoints" / "ep1.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(AssembleInputError) as exc:
        _run(sources, extraction, out)

    assert "ep0.json" in str(exc.value) and "ep1.json" in str(exc.value)
    assert not (out / "r1").exists(), "違規時不得留下孤兒 run 目錄"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agentcli/test_gate.py tests/agentcli/test_assemble_boundary.py -v`
Expected: `test_gate.py` FAILs with `ModuleNotFoundError: ... gate`; `test_duplicate_endpoint_files_fail_before_any_run_dir_exists` FAILs because no `AssembleInputError` is raised (the duplicate is currently accepted).

- [ ] **Step 3: Write the implementation**

Create `loop_apidoc/agentcli/gate.py`:

```python
"""擷取輸入的邊界閘門:一個定義,兩個入口。

`assemble` 與 `verify-extraction` 都只呼叫 `check_extraction`,兩者不可能漂移。
純函式、不做檔案 I/O;呼叫端把回傳的訊息轉成 AssembleInputError。

硬 schema 錯誤(JSON 壞掉、型別錯)不在這裡——那些由
`load_extraction_inputs` 在讀檔時就 fail loudly,因為它們會讓後續檢查失去意義。
"""

from __future__ import annotations

from loop_apidoc.agentcli.cross_file import cross_file_violations
from loop_apidoc.agentcli.source_guard import check_extraction_inputs
from loop_apidoc.manifest.models import Manifest


def check_extraction(
    inventory: dict,
    endpoints: list[tuple[str, dict]],
    integration: dict | None,
    manifest: Manifest,
) -> list[str]:
    """一次列出所有違規(path / source / 跨檔),讓 agent 一次改寫即可。"""
    return check_extraction_inputs(
        inventory, endpoints, integration, manifest
    ) + cross_file_violations(inventory, endpoints)
```

In `loop_apidoc/agentcli/assemble.py`, rename `_named_endpoints` to `named_endpoints` (definition at line 147 and the call at line 221), swap the import, and call the gate. Replace the import at line 11:

```python
from loop_apidoc.agentcli.gate import check_extraction
```

Change the definition:

```python
def named_endpoints(
    extraction_dir: Path, endpoint_texts: list[str]
) -> list[tuple[str, dict]]:
    """Pair each endpoint text with its filename, for guard messages that name
    the file to fix. Same sorted order `load_extraction_inputs` read them in."""
    endpoints_dir = extraction_dir / "endpoints"
    names = (
        [p.name for p in sorted(endpoints_dir.glob("*.json"))]
        if endpoints_dir.is_dir() else []
    )
    return [(name, json.loads(text)) for name, text in zip(names, endpoint_texts)]
```

And the call site inside `run_assemble_pipeline`:

```python
    violations = check_extraction(
        inventory, named_endpoints(extraction_dir, endpoint_texts),
        integration, manifest)
    if violations:
        raise AssembleInputError(
            "擷取輸入不符契約(修正後重跑 assemble):\n"
            + "\n".join(f"  - {v}" for v in violations))
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/agentcli -v && uv run ruff check .`
Expected: PASS. If an existing fixture in `tests/agentcli/` or `tests/test_cli_assemble.py` now trips a cross-file invariant, **fix the fixture** (it was an unrealistic extraction dir) — do not weaken the invariant.

Run: `uv run pytest`
Expected: PASS (benchmark cases skip without local `sources/`).

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/agentcli/gate.py loop_apidoc/agentcli/assemble.py tests/agentcli/test_gate.py tests/agentcli/test_assemble_boundary.py
git commit -m "feat: [agentcli] check_extraction 聚合閘門,assemble 納入跨檔不變式"
```

---

### Task 3: `verify-extraction` CLI command

**Files:**
- Create: `loop_apidoc/agentcli/verify.py`
- Modify: `loop_apidoc/cli.py` (add a `verify_extraction` command after `manifest`)
- Test: `tests/test_cli_verify_extraction.py`

**Interfaces:**
- Consumes: `gate.check_extraction` (Task 2), `assemble.load_extraction_inputs`, `assemble.named_endpoints`, `assemble.AssembleInputError`.
- Produces: `verify.verify_extraction_dir(*, sources_root: Path, extraction_dir: Path, generated_at: datetime, urls: list[str] | None = None, excludes: Sequence[str] = ()) -> list[str]` — raises `AssembleInputError` on hard schema errors, otherwise returns every violation. Writes nothing.
- CLI: `loop-apidoc verify-extraction --sources <DIR> --extraction <DIR> [--url U ...] [--exclude G ...] [--json]`; exit `0` clean, `2` on any violation or schema error.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_verify_extraction.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()

_INVENTORY = {
    "overview": "Demo API",
    "environments": [{"name": "prod", "base_url": "https://api.example.com",
                      "version": None, "source": "manual.md p.1"}],
    "security_schemes": [], "schemas": [], "errors": [], "operational": [],
    "endpoints": [{"method": "GET", "path": "/ping", "summary": "健康檢查",
                   "source": "manual.md p.2"}],
    "missing": [],
}
_ENDPOINT = {
    "method": "GET", "path": "/ping", "parameters": [], "request": None,
    "responses": [{"status": "200", "description": "OK", "schema": None}],
    "examples": [], "missing": [],
}


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    extraction = tmp_path / "extraction"
    (extraction / "endpoints").mkdir(parents=True)
    (extraction / "inventory.json").write_text(
        json.dumps(_INVENTORY, ensure_ascii=False), encoding="utf-8")
    (extraction / "endpoints" / "ep0.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "manual.md").write_text("# Demo API\nGET /ping", encoding="utf-8")
    return sources, extraction


def _invoke(sources: Path, extraction: Path, *extra: str):
    return runner.invoke(app, [
        "verify-extraction", "--sources", str(sources),
        "--extraction", str(extraction), *extra,
    ])


def test_clean_extraction_exits_zero(tmp_path):
    sources, extraction = _setup(tmp_path)

    res = _invoke(sources, extraction)

    assert res.exit_code == 0, res.output


def test_violations_exit_two_and_are_all_listed(tmp_path):
    sources, extraction = _setup(tmp_path)
    # 未以 / 開頭的 path(source_guard)+ 端點檔不在 inventory(cross_file)
    (extraction / "endpoints" / "ep0.json").write_text(
        json.dumps({**_ENDPOINT, "path": "pong"}, ensure_ascii=False),
        encoding="utf-8")

    res = _invoke(sources, extraction)

    assert res.exit_code == 2
    assert "ep0.json" in res.output
    assert "/ping" in res.output


def test_json_flag_emits_an_array_of_violations(tmp_path):
    sources, extraction = _setup(tmp_path)
    (extraction / "endpoints" / "ep1.json").write_text(
        json.dumps(_ENDPOINT, ensure_ascii=False), encoding="utf-8")

    res = _invoke(sources, extraction, "--json")

    assert res.exit_code == 2
    payload = json.loads(res.output)
    assert isinstance(payload, list)
    assert payload and all(isinstance(v, str) for v in payload)


def test_json_flag_emits_empty_array_when_clean(tmp_path):
    sources, extraction = _setup(tmp_path)

    res = _invoke(sources, extraction, "--json")

    assert res.exit_code == 0
    assert json.loads(res.output) == []


def test_malformed_json_exits_two(tmp_path):
    sources, extraction = _setup(tmp_path)
    (extraction / "endpoints" / "ep0.json").write_text("{ nope", encoding="utf-8")

    res = _invoke(sources, extraction)

    assert res.exit_code == 2


def test_no_run_directory_is_created(tmp_path):
    sources, extraction = _setup(tmp_path)

    _invoke(sources, extraction)

    entries = {p.name for p in tmp_path.iterdir()}
    assert entries == {"sources", "extraction"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_verify_extraction.py -v`
Expected: FAIL — typer exits with code 2 and `No such command 'verify-extraction'` for every test (so even the exit-2 assertions fail on output content / JSON parse).

- [ ] **Step 3: Write the implementation**

Create `loop_apidoc/agentcli/verify.py`:

```python
"""`verify-extraction` 的薄殼:建 manifest、讀擷取目錄、跑同一個閘門。

不寫任何檔、不建立 run 目錄。`assemble` 與這裡呼叫的是同一個
`gate.check_extraction`,兩個入口不可能漂移。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from loop_apidoc.agentcli.assemble import load_extraction_inputs, named_endpoints
from loop_apidoc.agentcli.gate import check_extraction
from loop_apidoc.manifest.builder import build_manifest


def verify_extraction_dir(
    *,
    sources_root: Path,
    extraction_dir: Path,
    generated_at: datetime,
    urls: list[str] | None = None,
    excludes: Sequence[str] = (),
) -> list[str]:
    """回傳所有違規(空 list = 乾淨)。硬 schema 錯誤由
    `load_extraction_inputs` 拋 AssembleInputError,不在此收斂。"""
    inventory, endpoint_texts, integration = load_extraction_inputs(extraction_dir)
    manifest = build_manifest(
        sources_root=sources_root, urls=urls or [],
        generated_at=generated_at, excludes=excludes)
    return check_extraction(
        inventory, named_endpoints(extraction_dir, endpoint_texts),
        integration, manifest)
```

In `loop_apidoc/cli.py`, add after the `manifest` command:

```python
@app.command(name="verify-extraction")
def verify_extraction(
    sources: Path = typer.Option(
        ..., "--sources", help="本機來源目錄（source 引用要比對 manifest）",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    extraction: Path = typer.Option(
        ..., "--extraction",
        help="agent 產出的擷取目錄(inventory.json + endpoints/*.json,選用 integration.json)",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    url: list[str] = typer.Option([], "--url", help="公開來源 URL,可重複指定"),
    exclude: list[str] = typer.Option(
        [], "--exclude",
        help="額外排除的 glob(可重複);預設已排除 README/LICENSE/CHANGELOG 等非規格檔",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="把違規以 JSON 陣列印到 stdout(供 agent 解析)"
    ),
) -> None:
    """檢查 agent 產出的擷取 JSON 是否符合契約;不寫檔、不建立 run 目錄。

    exit 0 乾淨;exit 2 有違規或硬 schema 錯誤（不會是 1——1 代表 validate FAIL）。
    """
    from loop_apidoc.agentcli.assemble import AssembleInputError
    from loop_apidoc.agentcli.verify import verify_extraction_dir

    try:
        violations = verify_extraction_dir(
            sources_root=sources,
            extraction_dir=extraction,
            generated_at=datetime.now(timezone.utc),
            urls=list(url),
            excludes=tuple(exclude),
        )
    except AssembleInputError as exc:
        if json_out:
            typer.echo(json.dumps([str(exc)], ensure_ascii=False, indent=2))
        else:
            typer.echo(f"擷取輸入錯誤:{exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(violations, ensure_ascii=False, indent=2))
    elif violations:
        typer.echo("擷取輸入不符契約(修正後重跑):", err=True)
        for violation in violations:
            typer.echo(f"  - {violation}", err=True)
    else:
        typer.echo("verify-extraction PASS:擷取輸入符合契約")
    raise typer.Exit(code=2 if violations else 0)
```

Note: `CliRunner()` in the tests captures stderr into `res.output` by default, so the `err=True` echoes are asserted from `res.output`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_verify_extraction.py -v && uv run ruff check .`
Expected: PASS (6 tests). If `res.output` does not contain stderr, construct the runner as `CliRunner(mix_stderr=True)` (older click) or assert on `res.stderr` — adjust the test, not the command's stream choice.

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/agentcli/verify.py loop_apidoc/cli.py tests/test_cli_verify_extraction.py
git commit -m "feat: [cli] 新增 verify-extraction 命令,與 assemble 共用同一個閘門"
```

---

### Task 4: Benchmark regression net

**Files:**
- Modify: `tests/test_benchmarks.py` (append one test)

**Interfaces:**
- Consumes: `verify.verify_extraction_dir` (Task 3); the module-level `case` fixture, `_has_sources`, and `_FIXED_TS` already in the file.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_benchmarks.py`:

```python
def test_benchmark_extraction_passes_the_gate(case) -> None:
    """每個 benchmark case 的 extraction/ 都必須通過 check_extraction。

    這是擋下「過緊的不變式」的回歸網:設計期間 index-strict 對應就是被這條
    測試否決的(apis-guru-baseline 的 ep3/ep4/ep5 順序本來就不對位)。
    """
    if not _has_sources(case):
        pytest.skip(f"{case.name}: sources/ not present (operator-provided, gitignored)")

    violations = verify_extraction_dir(
        sources_root=case / "sources",
        extraction_dir=case / "extraction",
        generated_at=_FIXED_TS,
    )

    assert violations == [], f"{case.name}: {violations}"
```

Add the import near the file's other `loop_apidoc` imports:

```python
from loop_apidoc.agentcli.verify import verify_extraction_dir
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_benchmarks.py -k extraction_passes_the_gate -v`
Expected: PASS for every case whose `sources/` exists locally; SKIP otherwise. The spec measured **zero violations across all 10 cases (55 endpoint files)** — if a case fails, the invariant is too tight or the fixture is wrong. Investigate before touching the invariant; report the finding rather than loosening silently.

- [ ] **Step 3: Run the whole suite**

Run: `uv run pytest && uv run ruff check .`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: [benchmarks] 每個 case 的 extraction 必須通過 check_extraction"
```

---

### Task 5: Relax the write contract in `SKILL.md` + align docs

**Files:**
- Modify: `skills/loop-apidoc/SKILL.md` (subagent contract §, steps 2–4, step 5)
- Modify: `skills/loop-apidoc/reference/assemble-and-correction.md` (document `verify-extraction`)
- Modify: `CLAUDE.md` (package table: `agentcli/` row; the six-command sentence)

**Interfaces:**
- Consumes: the `verify-extraction` CLI from Task 3.
- Produces: nothing consumed by code.

- [ ] **Step 1: Rewrite the subagent contract in `SKILL.md`**

Replace the paragraph currently ending `The subagent **returns the JSON only** — no prose, no file writes. **You (the orchestrator) are the only writer.**` with:

```markdown
Write permission is layered. An **endpoint** subagent writes exactly the one
`endpoints/ep<N>.json` path you assign it and returns **one line** of summary
(e.g. `ep05 OK 8 params 1 responses`) — never the JSON body, which would cost
2–4k tokens of pure carriage per endpoint. The **inventory** and **integration**
subagents write nothing and return their JSON object; **you** write those two files.
No subagent may write another subagent's file, `inventory.json`, or `integration.json`.

Grounding and the read-only posture toward *sources* are unchanged: a subagent only
reads sources and never fetches the web. Control is regained by verification, not by
carriage — `verify-extraction` (step 5) enforces the cross-file invariants.
```

- [ ] **Step 2: Rewrite extraction steps 2–4 in `SKILL.md`**

Replace the numbered list under `### 2–4. Extract → write the JSON` with:

```markdown
2. **inventory** — one subagent reads every source and returns one object; **you** write
   `<WORK>/inventory.json`. Include every endpoint and every error code.
3. **endpoints** — one subagent per `inventory.endpoints` entry, **in parallel** (≤6
   concurrent, then batch). Tell each subagent the exact path to write:
   `<WORK>/endpoints/ep<N>.json` (zero-padded, inventory order). It writes that one file
   and returns one summary line. Filename order carries no meaning — the gate matches on
   `method`/`path`, not on `<N>`.
4. **integration** (optional) — one subagent over the encryption/signing/callback/
   field-condition sections; it returns the JSON and **you** write `<WORK>/integration.json`.
   Omit the file entirely only when the sources describe no integration mechanics.
```

- [ ] **Step 3: Insert a verification step before assemble in `SKILL.md`**

Immediately before `### 5. Assemble + validate`, insert:

```markdown
### 5. Verify the extraction

```bash
<APIDOC> verify-extraction \
  --sources "<SOURCES>" --extraction "<WORK>" [--url "<URL>" ...] --json
```

Exit 0 → proceed. Exit 2 → the JSON array on stdout lists every violation (missing or
duplicate endpoint file, an endpoint not in inventory, an unresolvable `schema_ref` or
`security[]`, a localized key, an unrooted `path`, an uncited `source`). Fix the extraction
JSON and re-run. `assemble` runs the same checks, so skipping this step is safe but wastes
a round trip.
```

Renumber the following section from `### 5. Assemble + validate` to `### 6. Assemble + validate`, and check for any later cross-reference to "step 5" in the file (`grep -n "step 5\|### [0-9]" skills/loop-apidoc/SKILL.md`) and renumber consistently.

- [ ] **Step 4: Document the command in `reference/assemble-and-correction.md`**

Add a section at the top of that file:

```markdown
## `verify-extraction`

Runs `assemble`'s input boundary standalone: builds a manifest, checks the agent-written
extraction JSON, writes nothing, creates no run directory.

- `exit 0` clean; `exit 2` with every violation at once. Never `1` (that means validate FAIL).
- `--json` prints a JSON array of violation strings (`[]` when clean).
- `--sources` is required because `source` citations are checked against `manifest.json`.

Cross-file invariants (all `error`, all also enforced by `assemble`):

1. `len(endpoints/*.json) == len(inventory.endpoints)`
2. the `(method, path)` multiset of endpoint files equals inventory's
3. no `(method, path)` appears in two endpoint files
4. every `schema_ref` resolves to an `inventory.schemas[].name`
5. every `security[]` entry resolves to an `inventory.security_schemes[].name`

Hard schema errors (malformed JSON, wrong types) abort on the first one — the remaining
checks would be meaningless.
```

- [ ] **Step 5: Align `CLAUDE.md`**

In the "Execution model" section, change "The six generation/analysis CLI commands are `preprocess` … and `diff` …" to list **seven**, inserting `verify-extraction` (check the extraction JSON against the assemble input boundary; writes nothing) before `assemble`.

In the package table, extend the `loop_apidoc/agentcli/` row to mention the new modules:

```markdown
`cross_file.py` (pure cross-file invariants: endpoint files ↔ inventory — count, `(method, path)` multiset, no duplicates, `schema_ref`/`security[]` resolution), `gate.py` (`check_extraction`, the single aggregator `assemble` and `verify-extraction` both call), `verify.py` (the `verify-extraction` shell: build manifest + load extraction + gate; writes nothing)
```

Also update the "**File-I/O exits**" paragraph only if you added a writer — you did not; `verify.py` reads and writes nothing, so add it to the read-side exception sentence alongside `preparation/coverage.py`.

- [ ] **Step 6: Verify the skill still parses and tests pass**

Run: `uv run pytest tests/test_plugin_manifest.py tests/test_loop_sdk_author_skill.py -v && uv run pytest && uv run ruff check .`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add skills/loop-apidoc/SKILL.md skills/loop-apidoc/reference/assemble-and-correction.md CLAUDE.md
git commit -m "docs: [skill] 端點 subagent 自行寫檔,改以 verify-extraction 把關"
```

---

## Verification checklist

- [ ] `uv run pytest` — full suite green (benchmarks skip without local `sources/`)
- [ ] `uv run pytest tests/test_benchmarks.py -k extraction_passes_the_gate` — zero violations on every case with local sources
- [ ] `uv run ruff check .` — clean
- [ ] `uv run loop-apidoc verify-extraction --help` — command listed and documented
- [ ] `uv run loop-apidoc --help` — seven commands + `foundry` sub-app
- [ ] No run directory is created by `verify-extraction`, and none is left behind when `assemble` rejects input
