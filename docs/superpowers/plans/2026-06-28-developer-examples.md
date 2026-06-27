# `examples/` 開發者請求範例產物 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為每個 OpenAPI 端點產出 curl / TypeScript / Python 三語請求範例（`examples/{operationId}/request.{sh,ts,py}` + `examples/README.md`），值缺漏時輸出顯式佔位符、不臆測。

**Architecture:** 新增純函式模組 `loop_apidoc/generate/examples.py`，消費「已建好的 openapi dict」（與 `openapi.yaml` 同源，operationId 已指派）+ `plan.integration.crypto`（簽章鏈），回傳 `{相對路徑: 內容}` dict。`generate/writer.py::generate_outputs`（唯一 file-I/O 出口）迭代寫出。生成器只允許輸出「來源值」或「顯式佔位符」兩類，靠單元測試鎖死。

**Tech Stack:** Python ≥3.11、pydantic v2、pytest、ruff、uv。

## Global Constraints

- 核心不變式：來源是唯一真實來源；範例不引入新事實，未提供的值一律輸出 `<placeholder>`，**禁止**依型別推導樣本值（`"string"`/`0`/`true`）、編造 URL/金額/金鑰。
- 佔位符格式統一為 `<{snake}>`（欄位名正規化為 snake_case，僅 `[a-z0-9_]`）。此決定取代 spec §3 中 `<your_merchant_id>` 與 `<amount>` 前綴不一致的示意。
- 純函式、無 I/O；唯一寫檔出口是 `generate_outputs`。
- 寫檔一律 `encoding="utf-8"`；JSON/註解 CJK 安全。
- 每個產出檔含檔頭註記常數 `HEADER_NOTE`。
- 既有測試與 lint 必須維持綠：`uv run pytest`、`uv run ruff check .`。

---

### Task 1: 純核心——值解析、佔位符、RequestShape、簽章判定

**Files:**
- Create: `loop_apidoc/generate/examples.py`
- Test: `tests/test_generate_examples.py`

**Interfaces:**
- Consumes: openapi operation dict（`{"operationId","parameters"?,"requestBody"?,"security"?}`）、`doc["servers"]`、`loop_apidoc.plan.models.NormalizationPlan` / `CryptoScheme`。
- Produces:
  - `HEADER_NOTE: str`
  - `_placeholder(name: str) -> str` → 形如 `"<merchant_id>"`
  - `_resolve_value(name: str, node: dict) -> tuple[str, object]` → `("source", value)` 或 `("placeholder", "<name>")`
  - `_request_shape(operation: dict, servers: list[dict], path: str | None) -> dict`，鍵：`method:str, url:str, query/header/path/body: list[tuple[str,str,object]]`（每筆 `(name, kind, value)`，kind ∈ `{"source","placeholder"}`）、`content_type: str | None`、`security: list[str]`
  - `_signature_explicit(scheme: CryptoScheme) -> bool`
  - `_request_signing_schemes(plan: NormalizationPlan) -> list[CryptoScheme]`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_generate_examples.py
from loop_apidoc.generate.examples import (
    HEADER_NOTE,
    _placeholder,
    _resolve_value,
    _request_shape,
    _request_signing_schemes,
    _signature_explicit,
)
from loop_apidoc.plan.models import CryptoScheme, IntegrationContract, NormalizationPlan


def test_placeholder_is_snake_angle_bracketed():
    assert _placeholder("MerchantID") == "<merchant_id>"
    assert _placeholder("Amt") == "<amt>"


def test_resolve_value_prefers_source_example():
    assert _resolve_value("Version", {"example": "2.0"}) == ("source", "2.0")


def test_resolve_value_single_enum_is_source():
    node = {"schema": {"enum": ["S"]}}
    assert _resolve_value("Action", node) == ("source", "S")


def test_resolve_value_missing_falls_to_placeholder_not_type_sample():
    kind, value = _resolve_value("Amount", {"schema": {"type": "integer"}})
    assert kind == "placeholder"
    assert value == "<amount>"
    # 不臆測回歸鎖：絕不依型別塞樣本
    assert value not in (0, "string", "0", True)


def test_request_shape_uses_server_url_and_partitions_fields():
    op = {
        "operationId": "PayOrder",
        "parameters": [
            {"name": "MerchantID", "in": "query", "schema": {"type": "string"}},
            {"name": "Version", "in": "query", "example": "2.0"},
        ],
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"type": "object", "properties": {"Amount": {"type": "integer"}}}
                }
            }
        },
        "security": [{"NewebpayAuth": []}],
    }
    shape = _request_shape(op, [{"url": "https://api.example.com"}], "/pay")
    assert shape["method"] == "POST" or shape["method"]  # filled by caller; see note
    assert shape["url"] == "https://api.example.com/pay"
    assert ("Version", "source", "2.0") in shape["query"]
    assert ("MerchantID", "placeholder", "<merchant_id>") in shape["query"]
    assert ("Amount", "placeholder", "<amount>") in shape["body"]
    assert shape["content_type"] == "application/json"
    assert shape["security"] == ["NewebpayAuth"]


def test_request_shape_webhook_url_placeholder():
    shape = _request_shape({"operationId": "Notify"}, [], None)
    assert shape["url"] == "<your_receiver_url>"


def test_request_shape_missing_server_url_placeholder():
    shape = _request_shape({"operationId": "X"}, [], "/p")
    assert shape["url"] == "<base_url>/p"


def test_signature_explicit_requires_algorithm_and_steps():
    full = CryptoScheme(
        status="supported", name="sig", algorithm="AES-256-CBC", mode="CBC",
        payload_assembly=[{"step": 1, "desc": "join", "fields": ["A", "B"]}],
    )
    assert _signature_explicit(full) is True
    partial = CryptoScheme(status="supported", name="sig", algorithm="AES-256-CBC")
    assert _signature_explicit(partial) is False


def test_request_signing_schemes_filters_callback_only():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            crypto=[
                CryptoScheme(status="supported", name="req", purpose="request"),
                CryptoScheme(status="supported", name="cb", purpose="callback"),
                CryptoScheme(status="supported", name="any", purpose=None),
            ]
        ),
    )
    names = [s.name for s in _request_signing_schemes(plan)]
    assert names == ["req", "any"]
```

> 註：`_request_shape` 的 `method` 由呼叫端（Task 5）決定（operation dict 本身不含 method，method 是 paths 的 key）。為讓 shape 自足，`_request_shape` 簽章補一個 `method` 參數，預設由 Task 5 傳入；本測試先放寬為「非空」。下方實作把 `method` 列入參數。

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_generate_examples.py -q`
Expected: FAIL（`ModuleNotFoundError: loop_apidoc.generate.examples`）

- [ ] **Step 3: 最小實作**

```python
# loop_apidoc/generate/examples.py
from __future__ import annotations

import re

from loop_apidoc.plan.models import CryptoScheme, NormalizationPlan

HEADER_NOTE = (
    "Derived from openapi.yaml + integration-contract.json — NOT a source document.\n"
    "Values shown as <placeholder> are not provided by the source; fill them in."
)


def _snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip())
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return re.sub(r"_+", "_", s) or "value"


def _placeholder(name: str) -> str:
    return f"<{_snake(name)}>"


def _resolve_value(name: str, node: dict) -> tuple[str, object]:
    """Source value only when the source/openapi states one; else placeholder.

    Never derives a type-based sample — that would violate the no-fabrication
    invariant.
    """
    if "example" in node:
        return ("source", node["example"])
    schema = node.get("schema") if isinstance(node.get("schema"), dict) else node
    enum = schema.get("enum") if isinstance(schema, dict) else None
    if isinstance(enum, list) and len(enum) == 1:
        return ("source", enum[0])
    if isinstance(schema, dict) and "const" in schema:
        return ("source", schema["const"])
    if isinstance(schema, dict) and "default" in schema:
        return ("source", schema["default"])
    return ("placeholder", _placeholder(name))


def _request_shape(
    operation: dict, servers: list[dict], path: str | None, method: str = "POST"
) -> dict:
    base = (servers[0].get("url") if servers else None) or "<base_url>"
    if path is None:
        url = "<your_receiver_url>"
    else:
        url = f"{base}{path}"
    buckets: dict[str, list] = {"query": [], "header": [], "path": [], "body": []}
    for raw in operation.get("parameters", []) or []:
        loc = raw.get("in")
        if loc not in buckets:
            continue
        kind, value = _resolve_value(raw.get("name", ""), raw)
        buckets[loc].append((raw.get("name"), kind, value))
    content_type = None
    body = operation.get("requestBody", {}).get("content", {}) if operation.get("requestBody") else {}
    if body:
        content_type = next(iter(body))
        schema = body[content_type].get("schema", {})
        for pname, pnode in (schema.get("properties") or {}).items():
            kind, value = _resolve_value(pname, {"schema": pnode})
            buckets["body"].append((pname, kind, value))
    security = [k for req in operation.get("security", []) or [] for k in req]
    return {
        "method": method,
        "url": url,
        "query": buckets["query"],
        "header": buckets["header"],
        "path": buckets["path"],
        "body": buckets["body"],
        "content_type": content_type,
        "security": security,
    }


def _signature_explicit(scheme: CryptoScheme) -> bool:
    return bool(scheme.algorithm) and bool(scheme.payload_assembly)


def _request_signing_schemes(plan: NormalizationPlan) -> list[CryptoScheme]:
    contract = plan.integration
    if contract is None:
        return []
    return [s for s in contract.crypto if s.purpose in (None, "request", "signature")]
```

> 將 `test_request_shape_uses_server_url_and_partitions_fields` 的 method 斷言改為實際：呼叫端傳 method；測試裡 `_request_shape(op, [...], "/pay", "POST")` → 斷言 `shape["method"] == "POST"`。

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_generate_examples.py -q && uv run ruff check loop_apidoc/generate/examples.py`
Expected: PASS、ruff clean

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/examples.py tests/test_generate_examples.py
git commit -m "feat: [generate] examples 純核心(值解析/佔位符/RequestShape/簽章判定)"
```

---

### Task 2: curl 範例渲染（`request.sh`）

**Files:**
- Modify: `loop_apidoc/generate/examples.py`
- Test: `tests/test_generate_examples.py`

**Interfaces:**
- Consumes: Task 1 的 `_request_shape` 輸出 dict、`HEADER_NOTE`、`_request_signing_schemes` 回傳的 `list[CryptoScheme]`。
- Produces: `_render_curl(shape: dict, schemes: list[CryptoScheme]) -> str`

- [ ] **Step 1: 寫失敗測試**

```python
def test_render_curl_has_header_note_url_and_signature_comment():
    from loop_apidoc.generate.examples import _render_curl
    from loop_apidoc.plan.models import CryptoScheme

    shape = {
        "method": "POST",
        "url": "https://api.example.com/pay",
        "query": [],
        "header": [],
        "path": [],
        "body": [("MerchantID", "placeholder", "<merchant_id>"), ("Version", "source", "2.0")],
        "content_type": "application/x-www-form-urlencoded",
        "security": [],
    }
    scheme = CryptoScheme(
        status="supported", name="CheckValue", algorithm="AES-256-CBC",
        payload_assembly=[{"step": 1, "desc": "排序欄位後組字串"}],
    )
    out = _render_curl(shape, [scheme])
    assert out.startswith("# Derived from openapi.yaml")
    assert "https://api.example.com/pay" in out
    assert "MerchantID=<merchant_id>" in out
    assert "Version=2.0" in out
    # curl 簽章一律註解步驟，且指向 script
    assert "# 簽章步驟" in out
    assert "request.py" in out
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_generate_examples.py::test_render_curl_has_header_note_url_and_signature_comment -q`
Expected: FAIL（`cannot import name '_render_curl'`）

- [ ] **Step 3: 最小實作**

```python
def _comment(text: str, prefix: str = "# ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.split("\n"))


def _signature_comment_steps(schemes: list[CryptoScheme]) -> str:
    if not schemes:
        return ""
    lines = ["# 簽章步驟（shell 無法內嵌加密，請先跑 request.py / request.ts 取得簽章值）"]
    for s in schemes:
        algo = s.algorithm or "<來源未指明演算法>"
        lines.append(f"#   {s.name or 'signature'}：{algo}")
        for step in s.payload_assembly:
            lines.append(f"#     {step.step or '-'}. {step.desc or '<來源未說明>'}")
    return "\n".join(lines)


def _render_curl(shape: dict, schemes: list[CryptoScheme]) -> str:
    parts = [_comment(HEADER_NOTE), ""]
    sig = _signature_comment_steps(schemes)
    if sig:
        parts += [sig, ""]
    data_fields = shape["body"] or shape["query"]
    lines = [f"curl -X {shape['method']} '{shape['url']}' \\"]
    if shape["content_type"]:
        lines.append(f"  -H 'Content-Type: {shape['content_type']}' \\")
    for name, _kind, value in shape["header"]:
        lines.append(f"  -H '{name}: {value}' \\")
    for i, (name, _kind, value) in enumerate(data_fields):
        tail = "" if i == len(data_fields) - 1 else " \\"
        lines.append(f"  --data-urlencode '{name}={value}'{tail}")
    parts.append("\n".join(lines))
    return "\n".join(parts) + "\n"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_generate_examples.py -q && uv run ruff check loop_apidoc/generate/examples.py`
Expected: PASS、ruff clean

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/examples.py tests/test_generate_examples.py
git commit -m "feat: [generate] examples curl 渲染(註解簽章步驟)"
```

---

### Task 3: TypeScript 範例渲染（`request.ts`）

**Files:**
- Modify: `loop_apidoc/generate/examples.py`
- Test: `tests/test_generate_examples.py`

**Interfaces:**
- Consumes: Task 1 shape、`_signature_explicit`、`CryptoScheme`。
- Produces: `_render_ts(shape: dict, schemes: list[CryptoScheme]) -> str`

- [ ] **Step 1: 寫失敗測試**

```python
def test_render_ts_runnable_signature_when_explicit():
    from loop_apidoc.generate.examples import _render_ts
    from loop_apidoc.plan.models import CryptoScheme, KeySource

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json", "security": [],
    }
    explicit = CryptoScheme(
        status="supported", name="CheckValue", algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "組字串"}],
    )
    out = _render_ts(shape, [explicit])
    assert out.startswith("// Derived from openapi.yaml")
    assert "createCipheriv" in out  # 可跑簽章函式
    assert "amount" in out  # body 佔位變數


def test_render_ts_skeleton_with_gap_when_not_explicit():
    from loop_apidoc.generate.examples import _render_ts
    from loop_apidoc.plan.models import CryptoScheme

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [], "body": [],
        "content_type": "application/json", "security": [],
    }
    partial = CryptoScheme(status="supported", name="Sig", algorithm="AES-256-CBC")
    out = _render_ts(shape, [partial])
    assert "createCipheriv" not in out
    assert "// gap:" in out
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_generate_examples.py -k render_ts -q`
Expected: FAIL（`cannot import name '_render_ts'`）

- [ ] **Step 3: 最小實作**

```python
def _ts_value(kind: str, value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _ts_signature(schemes: list[CryptoScheme]) -> str:
    if not schemes:
        return ""
    blocks = []
    for s in schemes:
        if _signature_explicit(s):
            key = (s.key_source.key if s.key_source else None) or "<hash_key>"
            iv = (s.key_source.iv if s.key_source else None) or "<hash_iv>"
            algo = (s.algorithm or "aes-256-cbc").lower()
            blocks.append(
                "import { createCipheriv, createHash } from 'node:crypto'\n\n"
                f"// 簽章 {s.name or ''}：{s.algorithm}\n"
                "function sign(payload: string): string {\n"
                f"  const key = process.env.{_snake(key).upper()} ?? '{key}'\n"
                f"  const iv = process.env.{_snake(iv).upper()} ?? '{iv}'\n"
                f"  const cipher = createCipheriv('{algo}', key, iv)\n"
                "  const enc = cipher.update(payload, 'utf8', 'hex') + cipher.final('hex')\n"
                "  return createHash('sha256').update(enc).digest('hex').toUpperCase()\n"
                "}\n"
            )
        else:
            missing = [f for f in ("algorithm", "mode", "payload_assembly") if not getattr(s, f, None)]
            blocks.append(
                f"// gap: 簽章 {s.name or ''} 來源未提供 {', '.join(missing)}；無法生成可跑函式\n"
                "function sign(payload: string): string {\n"
                "  throw new Error('來源未提供完整簽章演算法，請依文件補完')\n"
                "}\n"
            )
    return "\n".join(blocks)


def _render_ts(shape: dict, schemes: list[CryptoScheme]) -> str:
    parts = [_comment(HEADER_NOTE, prefix="// "), ""]
    sig = _ts_signature(schemes)
    if sig:
        parts += [sig, ""]
    fields = shape["body"] or shape["query"]
    body_lines = "\n".join(
        f"  {_snake(name)}: {_ts_value(kind, value)}," for name, kind, value in fields
    )
    parts.append(
        f"const url = {_ts_value('source', shape['url'])}\n"
        "const body = {\n" + body_lines + "\n}\n\n"
        f"const res = await fetch(url, {{\n"
        f"  method: '{shape['method']}',\n"
        f"  headers: {{ 'Content-Type': '{shape['content_type'] or 'application/json'}' }},\n"
        "  body: JSON.stringify(body),\n"
        "})\n"
        "console.log(await res.text())\n"
    )
    return "\n".join(parts) + "\n"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_generate_examples.py -k render_ts -q && uv run ruff check loop_apidoc/generate/examples.py`
Expected: PASS、ruff clean

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/examples.py tests/test_generate_examples.py
git commit -m "feat: [generate] examples TypeScript 渲染(可跑/骨架簽章)"
```

---

### Task 4: Python 範例渲染（`request.py`）

**Files:**
- Modify: `loop_apidoc/generate/examples.py`
- Test: `tests/test_generate_examples.py`

**Interfaces:**
- Consumes: Task 1 shape、`_signature_explicit`、`CryptoScheme`。
- Produces: `_render_py(shape: dict, schemes: list[CryptoScheme]) -> str`

- [ ] **Step 1: 寫失敗測試**

```python
def test_render_py_runnable_signature_when_explicit():
    from loop_apidoc.generate.examples import _render_py
    from loop_apidoc.plan.models import CryptoScheme, KeySource

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json", "security": [],
    }
    explicit = CryptoScheme(
        status="supported", name="CheckValue", algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "組字串"}],
    )
    out = _render_py(shape, [explicit])
    assert out.startswith("# Derived from openapi.yaml")
    assert "import httpx" in out
    assert "AES" in out and "def sign" in out


def test_render_py_skeleton_with_gap_when_not_explicit():
    from loop_apidoc.generate.examples import _render_py
    from loop_apidoc.plan.models import CryptoScheme

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [], "body": [],
        "content_type": "application/json", "security": [],
    }
    out = _render_py(shape, [CryptoScheme(status="supported", name="Sig")])
    assert "# gap:" in out
    assert "def sign" in out
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_generate_examples.py -k render_py -q`
Expected: FAIL（`cannot import name '_render_py'`）

- [ ] **Step 3: 最小實作**

```python
def _py_signature(schemes: list[CryptoScheme]) -> str:
    if not schemes:
        return ""
    blocks = []
    for s in schemes:
        if _signature_explicit(s):
            key = (s.key_source.key if s.key_source else None) or "<hash_key>"
            iv = (s.key_source.iv if s.key_source else None) or "<hash_iv>"
            blocks.append(
                "import hashlib\nimport os\n"
                "from Crypto.Cipher import AES  # pip install pycryptodome\n"
                "from Crypto.Util.Padding import pad\n\n"
                f"# 簽章 {s.name or ''}：{s.algorithm}\n"
                "def sign(payload: str) -> str:\n"
                f"    key = os.environ.get('{_snake(key).upper()}', '{key}').encode()\n"
                f"    iv = os.environ.get('{_snake(iv).upper()}', '{iv}').encode()\n"
                "    cipher = AES.new(key, AES.MODE_CBC, iv)\n"
                "    enc = cipher.encrypt(pad(payload.encode(), 16)).hex()\n"
                "    return hashlib.sha256(enc.encode()).hexdigest().upper()\n"
            )
        else:
            missing = [f for f in ("algorithm", "mode", "payload_assembly") if not getattr(s, f, None)]
            blocks.append(
                f"# gap: 簽章 {s.name or ''} 來源未提供 {', '.join(missing)}；無法生成可跑函式\n"
                "def sign(payload: str) -> str:\n"
                "    raise NotImplementedError('來源未提供完整簽章演算法，請依文件補完')\n"
            )
    return "\n".join(blocks)


def _render_py(shape: dict, schemes: list[CryptoScheme]) -> str:
    import json

    parts = [_comment(HEADER_NOTE), "", "import httpx", ""]
    sig = _py_signature(schemes)
    if sig:
        parts += [sig, ""]
    fields = shape["body"] or shape["query"]
    body_lines = "\n".join(
        f"    {json.dumps(name, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False)},"
        for name, _kind, value in fields
    )
    parts.append(
        f"url = {json.dumps(shape['url'], ensure_ascii=False)}\n"
        "payload = {\n" + body_lines + "\n}\n\n"
        f"resp = httpx.request({json.dumps(shape['method'])}, url, "
        + ("json=payload)" if (shape["content_type"] or "").endswith("json") else "data=payload)")
        + "\nprint(resp.text)\n"
    )
    return "\n".join(parts) + "\n"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_generate_examples.py -k render_py -q && uv run ruff check loop_apidoc/generate/examples.py`
Expected: PASS、ruff clean

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/examples.py tests/test_generate_examples.py
git commit -m "feat: [generate] examples Python 渲染(可跑/骨架簽章)"
```

---

### Task 5: `build_examples` 編排 + README + 端點/webhook 迭代

**Files:**
- Modify: `loop_apidoc/generate/examples.py`
- Test: `tests/test_generate_examples.py`

**Interfaces:**
- Consumes: `_request_shape`、`_render_curl/_render_ts/_render_py`、`_request_signing_schemes`、openapi dict（`paths`、`webhooks`、`servers`）、`NormalizationPlan`。
- Produces: `build_examples(openapi: dict, plan: NormalizationPlan) -> dict[str, str]`

- [ ] **Step 1: 寫失敗測試**

```python
def test_build_examples_emits_three_files_per_operation_and_readme():
    from loop_apidoc.generate.examples import build_examples
    from loop_apidoc.plan.models import NormalizationPlan

    openapi = {
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/pay": {
                "post": {
                    "operationId": "PayOrder",
                    "requestBody": {
                        "content": {"application/json": {"schema": {"type": "object",
                            "properties": {"Amount": {"type": "integer"}}}}}
                    },
                }
            }
        },
    }
    out = build_examples(openapi, NormalizationPlan(notebook_url="x"))
    assert "examples/README.md" in out
    assert "examples/PayOrder/request.sh" in out
    assert "examples/PayOrder/request.ts" in out
    assert "examples/PayOrder/request.py" in out
    assert "POST" in out["examples/PayOrder/request.sh"]


def test_build_examples_empty_when_no_operations():
    from loop_apidoc.generate.examples import build_examples
    from loop_apidoc.plan.models import NormalizationPlan

    assert build_examples({"paths": {}}, NormalizationPlan(notebook_url="x")) == {}


def test_build_examples_webhook_uses_receiver_placeholder():
    from loop_apidoc.generate.examples import build_examples
    from loop_apidoc.plan.models import NormalizationPlan

    openapi = {"webhooks": {"Notify": {"post": {"operationId": "Notify"}}}}
    out = build_examples(openapi, NormalizationPlan(notebook_url="x"))
    assert "<your_receiver_url>" in out["examples/Notify/request.sh"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_generate_examples.py -k build_examples -q`
Expected: FAIL（`cannot import name 'build_examples'`）

- [ ] **Step 3: 最小實作**

```python
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def _render_readme(operation_ids: list[str], plan: NormalizationPlan) -> str:
    schemes = _request_signing_schemes(plan)
    lines = [
        "# 請求範例（examples/）",
        "",
        HEADER_NOTE,
        "",
        "每個端點一資料夾，含 curl / TypeScript / Python 三語版本。",
        "`<...>` 為來源未提供的值，請自行填入。簽章值請先跑 request.py / request.ts 取得。",
        "",
        "## 端點",
    ]
    lines += [f"- `{oid}/`" for oid in operation_ids]
    if schemes:
        lines += ["", "## 通用簽章機制"]
        for s in schemes:
            lines.append(f"- {s.name or 'signature'}：{s.algorithm or '<來源未指明演算法>'}")
    return "\n".join(lines) + "\n"


def _iter_operations(openapi: dict):
    for path, item in (openapi.get("paths") or {}).items():
        for method, op in item.items():
            if method.lower() in _HTTP_METHODS and isinstance(op, dict):
                yield op.get("operationId"), method.upper(), path, op
    for _name, item in (openapi.get("webhooks") or {}).items():
        for method, op in item.items():
            if method.lower() in _HTTP_METHODS and isinstance(op, dict):
                yield op.get("operationId"), method.upper(), None, op


def build_examples(openapi: dict, plan: NormalizationPlan) -> dict[str, str]:
    servers = openapi.get("servers") or []
    schemes = _request_signing_schemes(plan)
    out: dict[str, str] = {}
    operation_ids: list[str] = []
    for operation_id, method, path, op in _iter_operations(openapi):
        if not operation_id:
            continue
        operation_ids.append(operation_id)
        shape = _request_shape(op, servers, path, method)
        base = f"examples/{operation_id}"
        out[f"{base}/request.sh"] = _render_curl(shape, schemes)
        out[f"{base}/request.ts"] = _render_ts(shape, schemes)
        out[f"{base}/request.py"] = _render_py(shape, schemes)
    if not out:
        return {}
    out["examples/README.md"] = _render_readme(operation_ids, plan)
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_generate_examples.py -q && uv run ruff check loop_apidoc/generate/examples.py`
Expected: PASS、ruff clean

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/examples.py tests/test_generate_examples.py
git commit -m "feat: [generate] build_examples 編排 + README + webhook 迭代"
```

---

### Task 6: writer / GenerateResult 整合（寫檔出口）

**Files:**
- Modify: `loop_apidoc/generate/models.py`（`GenerateResult` 加 `examples`）
- Modify: `loop_apidoc/generate/writer.py:15-46`（`build_result` + `generate_outputs`）
- Test: `tests/test_generate_writer_examples.py`

**Interfaces:**
- Consumes: `build_examples`、`GenerateResult`。
- Produces: `GenerateResult.examples: dict[str, str]`；run-dir 下實體 `examples/...` 檔案。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_generate_writer_examples.py
from pathlib import Path

from loop_apidoc.generate.writer import generate_outputs
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import EndpointEntry, NormalizationPlan


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="x",
        endpoints=[EndpointEntry(status="supported", method="POST", path="/pay",
            summary="付款", request={"content_type": "application/json"})],
    )


def test_generate_outputs_writes_example_files(tmp_path: Path):
    result = generate_outputs(_plan(), Manifest(sources=[]), tmp_path)
    assert result.examples  # 非空 dict
    sh = list(tmp_path.glob("examples/*/request.sh"))
    assert sh, "expected at least one request.sh under examples/"
    assert (tmp_path / "examples" / "README.md").exists()
    assert "NOT a source document" in sh[0].read_text(encoding="utf-8")
```

> 注意：`Manifest` 的實際必填欄位以 `loop_apidoc/manifest/models.py` 為準；若 `Manifest(sources=[])` 不合法，改用既有測試（如 `tests/test_generate_*`）建立 manifest 的同款 helper/fixture。

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_generate_writer_examples.py -q`
Expected: FAIL（`AttributeError: ... 'examples'` 或無 examples 檔）

- [ ] **Step 3: 最小實作**

`loop_apidoc/generate/models.py` — `GenerateResult` 末尾新增欄位：

```python
class GenerateResult(BaseModel):
    openapi: dict
    markdown: str
    provenance: ProvenanceDocument
    integration: dict | None = None
    examples: dict[str, str] = Field(default_factory=dict)
```

`loop_apidoc/generate/writer.py` — import 與 `build_result`：

```python
from loop_apidoc.generate.examples import build_examples
```

```python
def build_result(plan: NormalizationPlan, manifest: Manifest) -> GenerateResult:
    openapi = build_openapi(plan)
    return GenerateResult(
        openapi=openapi,
        markdown=build_markdown(plan, manifest),
        provenance=build_provenance(plan),
        integration=build_integration_document(plan),
        examples=build_examples(openapi, plan),
    )
```

`generate_outputs` — 在回傳前迭代寫出（緊接 integration 區塊之後）：

```python
    for relpath, content in result.examples.items():
        target = run_dir / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return result
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_generate_writer_examples.py -q && uv run ruff check loop_apidoc/generate/`
Expected: PASS、ruff clean

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/generate/models.py loop_apidoc/generate/writer.py tests/test_generate_writer_examples.py
git commit -m "feat: [generate] writer 寫出 examples/ 並掛上 GenerateResult"
```

---

### Task 7: 2-source builder 路徑回歸（教訓：別用手刻 model）

**Files:**
- Test: `tests/test_generate_examples_two_source.py`

**Interfaces:**
- Consumes: 真實 `build_openapi` + `build_examples`（不手刻空 model）。
- Produces: 回歸測試。

**背景（必讀）：** 過往 source-grounding 不變式曾因「單源遮蔽多源」變成 dead code（見 memory `integration-contract-feature`）。本測試用 2-source manifest 跑真實 plan→openapi→examples 全鏈，鎖死：(a) 跨源端點 operationId 唯一、examples 資料夾無碰撞；(b) 某源缺值的欄位落為佔位、不被另一源「升級」遮蔽。

- [ ] **Step 1: 寫失敗測試（先驗證盲點存在/不存在）**

```python
# tests/test_generate_examples_two_source.py
from loop_apidoc.generate.examples import build_examples
from loop_apidoc.generate.openapi import build_openapi
from loop_apidoc.plan.models import EndpointEntry, NormalizationPlan, SourceCitation


def _cite(src: str) -> SourceCitation:
    return SourceCitation(query_id="q", answer_path="a", manifest_source=src)


def test_two_source_operation_ids_unique_no_folder_collision():
    # 兩個來源各一個 POST /pay（summary 帶不同 operation code），openapi 不應碰撞，
    # examples 資料夾名隨 operationId 唯一。
    plan = NormalizationPlan(
        notebook_url="x",
        endpoints=[
            EndpointEntry(status="supported", method="POST", path="/a",
                summary="[NPA-F01] 付款", citations=[_cite("src1.pdf")]),
            EndpointEntry(status="supported", method="POST", path="/b",
                summary="[NPA-F02] 退款", citations=[_cite("src2.pdf")]),
        ],
    )
    openapi = build_openapi(plan)
    out = build_examples(openapi, plan)
    folders = {p.split("/")[1] for p in out if p != "examples/README.md"}
    assert len(folders) == 2  # 無碰撞


def test_two_source_missing_value_stays_placeholder():
    # 某端點欄位來源未給範例值 → 範例必為佔位，不得出現型別樣本。
    plan = NormalizationPlan(
        notebook_url="x",
        endpoints=[
            EndpointEntry(status="supported", method="POST", path="/pay",
                summary="付款",
                parameters=[{"name": "Amount", "in": "query", "schema": {"type": "integer"}}],
                citations=[_cite("src1.pdf")]),
        ],
    )
    openapi = build_openapi(plan)
    out = build_examples(openapi, plan)
    sh = next(v for k, v in out.items() if k.endswith("request.sh"))
    assert "Amount=<amount>" in sh
    assert "Amount=0" not in sh and "Amount=string" not in sh
```

- [ ] **Step 2: 跑測試**

Run: `uv run pytest tests/test_generate_examples_two_source.py -q`
Expected: 若實作正確應 PASS；若 FAIL 表示 operationId/佔位有真實 bug，依失敗訊息修 `examples.py`（這正是此測試的目的）。

- [ ] **Step 3:（若需要）修正實作**

依 Step 2 失敗訊息，於 `loop_apidoc/generate/examples.py` 修正（例：folder 命名未用 operationId、或 `_resolve_value` 誤升級）。無失敗則跳過。

- [ ] **Step 4: 全測試 + lint 綠**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 全 PASS、ruff clean

- [ ] **Step 5: Commit**

```bash
git add tests/test_generate_examples_two_source.py loop_apidoc/generate/examples.py
git commit -m "test: [generate] examples 2-source 回歸(operationId 唯一/佔位不被遮蔽)"
```

---

## 驗收（全部 Task 完成後）

- `uv run pytest -q` 全綠、`uv run ruff check .` clean。
- 對既有 NewebPay/ECPay e2e run-dir 重跑 `assemble`，人眼抽看一個端點的 `request.{sh,ts,py}`：URL/欄位/佔位符正確、簽章鏈呈現符合混合策略（呼應 memory「validation PASS≠產物好，要人眼看產物」）。

## Self-Review 對照 spec

- §2 架構/資料流 → Task 1、5、6 ✓
- §3 不臆測規則（來源值 vs 佔位、禁型別樣本）→ Task 1（`_resolve_value` + 回歸鎖）、Task 7 ✓
- §4 簽章鏈混合（curl 註解／TS·Py 可跑或骨架+gap）→ Task 2/3/4 ✓
- §5 佈局 + operationId 對齊 + webhook → Task 5 ✓
- §6 純衍生、無新 provenance、無 validate gate（靠生成器不變式 + 單元測試）→ Task 1/7（無新增 provenance/validate 任務，符合）✓
- §7 測試策略含 2-source 回歸 → Task 7 ✓
- §8 驗收 → 驗收段 ✓
- 型別一致性：`build_examples(openapi, plan)`、`_request_shape(operation, servers, path, method)`、`_render_curl/_render_ts/_render_py(shape, schemes)`、`_request_signing_schemes(plan)`、`_signature_explicit(scheme)` 全 Task 間一致。
