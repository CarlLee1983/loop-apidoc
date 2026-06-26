# Loop API 文件 Pipeline — Plan 4：產生 OpenAPI 3.1／繁中 Markdown／來源追溯

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立「產生層」：把 Plan 3 的 `NormalizationPlan`（＋Plan 1 `Manifest`）規格化為三個標準化產物——`openapi.yaml`（OpenAPI 3.1）、`api-guide.zh-TW.md`（繁體中文串接文件）、`provenance.json`（來源追溯），只讓「具來源依據且存在於計畫」的內容進入輸出，缺漏欄位以最小合法占位＋`x-loop-status: missing-source` 標記並完整記錄於 provenance（spec §8）。

**Architecture:** 一個解耦套件 `loop_apidoc/generate/`，純函式為主、無 I/O 直到最外層 writer。`models`：provenance 與彙總結果的 Pydantic 模型。`openapi`：`build_openapi(plan) -> dict`，組裝 3.1 文件（info／servers／paths／components.schemas／components.securitySchemes），對 OpenAPI 必填但來源缺失者填最小合法占位並掛 `x-loop-status: missing-source`。`markdown`：`build_markdown(plan, manifest) -> str`，輸出固定章節順序、敘述用繁中、API 名稱保留原文。`provenance`：`build_provenance(plan) -> ProvenanceDocument`，把每個輸出項目映射到 manifest source／query id／answer artifact／locator／狀態，target 字串對齊 OpenAPI 位置以利 Plan 5 交叉驗證。`writer`：`generate_outputs(plan, manifest, run_dir) -> GenerateResult` 為唯一檔案 I/O 邊界，序列化三檔並回傳結構化結果（供 Plan 5 validate／Plan 6 run 串接，**不在本計畫寫 CLI**）。

**Tech Stack:** Python ≥3.11、Pydantic v2、`pyyaml`（YAML 序列化）、`openapi-spec-validator`（測試中驗證產物合法）、標準庫 `json`／`pathlib`、pytest。沿用 Plan 1/2/3 的 `loop_apidoc/` 套件、注入式副作用與 TDD 流程。**本計畫不新增第三方依賴**（pyyaml／openapi-spec-validator／jsonschema 已在 pyproject）；**不消耗真實 NotebookLM 額度**（產生層純粹消費 Plan 3 的記憶體內計畫物件，不呼叫 adapter）。

這是六份計畫中的第 4 份。Plan 1（基礎建設＋manifest）、Plan 2（NotebookLM adapter＋doctor）、Plan 3（擷取＋規格化計畫）已完成並併入 master。本計畫**消費** Plan 3 的 `loop_apidoc.plan.models.NormalizationPlan`（含 `EndpointEntry`／`SchemaEntry`／`SecuritySchemeEntry`／`EnvironmentEntry`／`ErrorEntry`／`OperationalEntry`／`SystemGroup`／`SourceCitation`／`PlanItemStatus` 與 `missing_items`／`source_conflicts`／`unverified_items`）與 Plan 1 的 `loop_apidoc.manifest.models.Manifest`。本計畫**產出**的 `generate_outputs()`／`build_result()`／`REQUIRED_MARKDOWN_SECTIONS`／`ProvenanceDocument` 會由 Plan 5（validate）與 Plan 6（run）消費。

## Global Constraints

下列為整份 spec 的專案級要求，每個 task 都隱含遵守（值逐字取自 spec）：

- **以來源文件為唯一事實依據；來源未提供的資訊不得推測**（spec §1、§9.4）。產生層**不得**依 REST／OAuth／產業慣例補值；計畫中為 `null`／缺漏者，輸出必須以占位＋`x-loop-status: missing-source` 表示，**不得**自行編造名稱、型別、enum 或狀態碼。
- **OpenAPI 必填但來源缺失的欄位**：使用最小合法占位描述，並以明確 `x-loop-status: missing-source` 與 provenance 記錄缺漏（spec §8.1）。`x-loop-status` 的缺漏值固定字串為 `"missing-source"`。
- **endpoint operation 與 parameter 使用原始 API 名稱**；request／response schema 使用明確型別與 required 規則；security scheme 只根據來源建立（spec §8.1）。
- **Markdown 敘述採繁體中文**；API path、欄位、enum、header、query parameter 與程式碼範例保留原始名稱（spec §8.2、§2 全域語言政策）。
- **provenance 將每個標準化項目映射至 manifest source ID／NotebookLM 查詢 ID／回答 artifact／來源定位資訊／狀態（`supported`／`conflicting`／`missing`／`unverified`）**；NotebookLM 回答非獨立事實，狀態仍連回 manifest（spec §8.3）。
- **機密資料**：輸出及 log 不應保存 Google cookie／browser state／憑證（spec §11）；本計畫只序列化計畫衍生的文字。
- Python ≥3.11；資料模型用 Pydantic v2；不新增第三方依賴（沿用 Plan 1/2/3）。

---

## 參考：產物佈局、目標字串與狀態（供本計畫所有 task 對齊）

本計畫負責 run directory 的三個檔案（spec §8）：

```text
output/<run-id>/
├── openapi.yaml             # OpenAPI 3.1 文件（YAML，allow_unicode）
├── api-guide.zh-TW.md       # 繁體中文串接文件（固定章節順序）
└── provenance.json          # 來源追溯（ProvenanceDocument）
```

**provenance `target` 命名規則（與 OpenAPI 位置對齊，供 Plan 5 §9.3/§9.4 交叉驗證）：**

| 輸出項目 | target 字串 |
|---|---|
| API 標題 | `info.title` |
| API 版本 | `info.version` |
| server（第 i 個有 base_url 的環境） | `servers[{i}]` |
| security scheme（名稱 name） | `components.securitySchemes.{name}` |
| endpoint（path＝P、method＝M 小寫） | `paths.{P}.{m}` |
| 共用 schema（名稱 name） | `components.schemas.{name}` |
| 錯誤碼（code） | `errors.{code}` |
| 維運主題（topic） | `operational.{topic}` |
| 計畫缺漏項（area） | `missing.{area}` |
| 來源衝突項（area） | `conflict.{area}` |
| 無法確認項（area） | `unverified.{area}` |

**狀態值**沿用 `loop_apidoc.plan.models.PlanItemStatus`：`supported`／`conflicting`／`missing`／`unverified`。

**Markdown 固定章節**（`REQUIRED_MARKDOWN_SECTIONS`，逐字、依序、皆為 `## ` 級標題）：

```text
## 文件範圍與來源
## 串接前置條件
## 環境與 base URL
## 驗證／授權
## 共用規則
## Endpoint
## Request／Response 範例
## 錯誤碼
## 限制與注意事項
## 已知缺漏與來源衝突
```

**已知範圍邊界（本計畫刻意排除，列入 carry-forward）：**
- security scheme 型別映射僅辨識 OpenAPI 合法 `type`（`apiKey`／`http`／`oauth2`／`openIdConnect`／`mutualTLS`）；來源型別無法對映時，以 `apiKey` 為最小合法占位＋`x-loop-status: missing-source`＋原始字串入 `description`，由 Plan 5 攔截。更精細的型別推導（如 `http`+`bearer`）延後。
- request／response／parameter 的 schema 採容忍式淺層映射（`{"type": <字串>}` 或原樣 dict），不做巢狀 `$ref` 解析；Plan 3 計畫的內層 dict 為自由格式，深層 schema 正規化延後。
- 共用 schema 的 `$ref` 互引、example 對 schema 的一致性，由 Plan 5 §9.3 驗證 surfacing，本計畫不主動連結。

---

### Task 1：產生層模型（models）

定義 provenance 與彙總結果模型，作為後續所有 task 的型別契約。

**Files:**
- Create: `loop_apidoc/generate/__init__.py`
- Create: `loop_apidoc/generate/models.py`
- Create: `tests/generate/__init__.py`
- Create: `tests/generate/test_models.py`

**Interfaces:**
- Consumes: `loop_apidoc.plan.models.PlanItemStatus`。
- Produces:
  - `ProvenanceEntry(BaseModel)`：`target: str`、`status: PlanItemStatus`、`manifest_source: str | None = None`、`query_id: str | None = None`、`answer_path: str | None = None`、`locator: str | None = None`。
  - `ProvenanceDocument(BaseModel)`：`notebook_url: str`、`entries: list[ProvenanceEntry] = []`。
  - `GenerateResult(BaseModel)`：`openapi: dict`、`markdown: str`、`provenance: ProvenanceDocument`。

- [ ] **Step 1：建立空檔 `loop_apidoc/generate/__init__.py` 與 `tests/generate/__init__.py`**

`loop_apidoc/generate/__init__.py`：

```python
"""Standardized output generation layer (spec §8)."""
```

`tests/generate/__init__.py`：

```python
```

- [ ] **Step 2：寫失敗測試 `tests/generate/test_models.py`**

```python
from __future__ import annotations

from loop_apidoc.generate.models import (
    GenerateResult,
    ProvenanceDocument,
    ProvenanceEntry,
)
from loop_apidoc.plan.models import PlanItemStatus


def test_provenance_entry_defaults():
    entry = ProvenanceEntry(target="info.title", status=PlanItemStatus.SUPPORTED)
    assert entry.manifest_source is None
    assert entry.query_id is None
    assert entry.answer_path is None
    assert entry.locator is None


def test_provenance_document_roundtrip():
    doc = ProvenanceDocument(
        notebook_url="https://nb/x",
        entries=[
            ProvenanceEntry(
                target="paths./users.get",
                status=PlanItemStatus.SUPPORTED,
                manifest_source="api.md",
                query_id="06-initial",
                answer_path="answers/06-initial.txt",
                locator="p.3",
            )
        ],
    )
    reloaded = ProvenanceDocument.model_validate_json(doc.model_dump_json())
    assert reloaded == doc
    assert reloaded.entries[0].status is PlanItemStatus.SUPPORTED


def test_generate_result_holds_three_artifacts():
    result = GenerateResult(
        openapi={"openapi": "3.1.0"},
        markdown="# x",
        provenance=ProvenanceDocument(notebook_url="https://nb/x"),
    )
    assert result.openapi["openapi"] == "3.1.0"
    assert result.markdown == "# x"
    assert result.provenance.notebook_url == "https://nb/x"
```

- [ ] **Step 3：執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/generate/test_models.py -v`
Expected: FAIL（`ModuleNotFoundError: loop_apidoc.generate.models`）。

- [ ] **Step 4：實作 `loop_apidoc/generate/models.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from loop_apidoc.plan.models import PlanItemStatus


class ProvenanceEntry(BaseModel):
    target: str
    status: PlanItemStatus
    manifest_source: str | None = None
    query_id: str | None = None
    answer_path: str | None = None
    locator: str | None = None


class ProvenanceDocument(BaseModel):
    notebook_url: str
    entries: list[ProvenanceEntry] = Field(default_factory=list)


class GenerateResult(BaseModel):
    openapi: dict
    markdown: str
    provenance: ProvenanceDocument
```

- [ ] **Step 5：執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/generate/test_models.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 6：Commit**

```bash
git add loop_apidoc/generate/__init__.py loop_apidoc/generate/models.py tests/generate/__init__.py tests/generate/test_models.py
git commit -m "feat: [generate] add provenance and result models"
```

---

### Task 2：OpenAPI 文件骨架（info／servers／securitySchemes）

組裝 OpenAPI 3.1 的頂層骨架：`openapi` 版本字串、`info`（title／version，缺漏掛 `x-loop-status`）、`servers`（只取有 base_url 的環境）、`components.securitySchemes`（只根據來源，型別容忍映射）。**paths 與 components.schemas 留待 Task 3／4**——本 task 暫時輸出 `paths: {}`。

**Files:**
- Create: `loop_apidoc/generate/openapi.py`
- Create: `tests/generate/test_openapi.py`

**Interfaces:**
- Consumes: `loop_apidoc.plan.models`（`NormalizationPlan`、`SystemGroup`、`EnvironmentEntry`、`SecuritySchemeEntry`）。
- Produces:
  - `MISSING_STATUS: str = "missing-source"`、`X_LOOP_STATUS: str = "x-loop-status"`。
  - `build_openapi(plan: NormalizationPlan) -> dict`：回傳合法 OpenAPI 3.1 mapping，鍵序為 `openapi`、`info`、（`servers`）、`paths`、（`components`）。本 task `paths` 恆為 `{}`、`components` 只含 `securitySchemes`（若有）。
  - 內部 helper：`_build_info`、`_build_servers`、`_build_security_schemes`、`_build_security_scheme`、`_schema_from_type`（後者供 Task 3/4 共用）。

- [ ] **Step 1：寫失敗測試 `tests/generate/test_openapi.py`**

```python
from __future__ import annotations

from loop_apidoc.generate.openapi import (
    MISSING_STATUS,
    X_LOOP_STATUS,
    build_openapi,
)
from loop_apidoc.plan.models import (
    EnvironmentEntry,
    NormalizationPlan,
    PlanItemStatus,
    SecuritySchemeEntry,
    SystemGroup,
)


def _plan(**kw) -> NormalizationPlan:
    return NormalizationPlan(notebook_url="https://nb/x", **kw)


def test_openapi_version_and_empty_paths():
    doc = build_openapi(_plan())
    assert doc["openapi"] == "3.1.0"
    assert doc["paths"] == {}


def test_info_uses_system_group_title_and_env_version():
    plan = _plan(
        system_groups=[SystemGroup(name="Loop Payments API")],
        environments=[
            EnvironmentEntry(status=PlanItemStatus.SUPPORTED, version="2024-01")
        ],
    )
    info = build_openapi(plan)["info"]
    assert info["title"] == "Loop Payments API"
    assert info["version"] == "2024-01"
    assert X_LOOP_STATUS not in info


def test_info_marks_missing_when_no_source():
    info = build_openapi(_plan())["info"]
    assert info["title"] == "Untitled API"
    assert info["version"] == "0.0.0"
    assert info[X_LOOP_STATUS] == MISSING_STATUS


def test_servers_only_from_base_url():
    plan = _plan(
        environments=[
            EnvironmentEntry(
                status=PlanItemStatus.SUPPORTED, name="prod",
                base_url="https://api.example.com",
            ),
            EnvironmentEntry(status=PlanItemStatus.MISSING, name="staging"),
        ]
    )
    doc = build_openapi(plan)
    assert doc["servers"] == [
        {"url": "https://api.example.com", "description": "prod"}
    ]


def test_no_servers_key_when_none_have_base_url():
    doc = build_openapi(_plan(environments=[
        EnvironmentEntry(status=PlanItemStatus.MISSING, name="prod")
    ]))
    assert "servers" not in doc


def test_security_scheme_known_apikey():
    plan = _plan(security_schemes=[
        SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth",
            type="apiKey", location="header", details="X-API-Key",
        )
    ])
    schemes = build_openapi(plan)["components"]["securitySchemes"]
    assert schemes["ApiKeyAuth"] == {
        "type": "apiKey", "in": "header", "name": "X-API-Key"
    }


def test_security_scheme_unknown_type_is_placeholder():
    plan = _plan(security_schemes=[
        SecuritySchemeEntry(
            status=PlanItemStatus.UNVERIFIED, name="WeirdAuth",
            type="hmac-signature", location="header", details="X-Sig",
        )
    ])
    scheme = build_openapi(plan)["components"]["securitySchemes"]["WeirdAuth"]
    assert scheme["type"] == "apiKey"
    assert scheme[X_LOOP_STATUS] == MISSING_STATUS
    assert scheme["description"] == "hmac-signature"
```

- [ ] **Step 2：執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/generate/test_openapi.py -v`
Expected: FAIL（`ModuleNotFoundError: loop_apidoc.generate.openapi`）。

- [ ] **Step 3：實作 `loop_apidoc/generate/openapi.py`（本 task 範圍）**

```python
from __future__ import annotations

from loop_apidoc.plan.models import NormalizationPlan

MISSING_STATUS = "missing-source"
X_LOOP_STATUS = "x-loop-status"

_OPENAPI_SECURITY_TYPES = {"apiKey", "http", "oauth2", "openIdConnect", "mutualTLS"}
_APIKEY_LOCATIONS = {"header", "query", "cookie"}


def _schema_from_type(value) -> dict | None:
    """Tolerant mapping of a free-form type hint to a JSON-Schema fragment."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        return {"type": value}
    return None


def _build_info(plan: NormalizationPlan) -> dict:
    title = plan.system_groups[0].name if plan.system_groups else None
    version = next((e.version for e in plan.environments if e.version), None)
    info: dict = {"title": title or "Untitled API", "version": version or "0.0.0"}
    if not title or not version:
        info[X_LOOP_STATUS] = MISSING_STATUS
    return info


def _build_servers(plan: NormalizationPlan) -> list[dict]:
    servers: list[dict] = []
    for env in plan.environments:
        if not env.base_url:
            continue
        entry: dict = {"url": env.base_url}
        if env.name:
            entry["description"] = env.name
        servers.append(entry)
    return servers


def _build_security_scheme(scheme) -> dict:
    raw = (scheme.type or "").strip()
    if raw in _OPENAPI_SECURITY_TYPES:
        out: dict = {"type": raw}
        if raw == "apiKey":
            location = scheme.location if scheme.location in _APIKEY_LOCATIONS else "header"
            out["in"] = location
            out["name"] = scheme.details or "Authorization"
        return out
    # Unmapped source type: minimal legal apiKey placeholder, never a guess.
    location = scheme.location if scheme.location in _APIKEY_LOCATIONS else "header"
    out = {
        "type": "apiKey",
        "in": location,
        "name": scheme.details or "Authorization",
        X_LOOP_STATUS: MISSING_STATUS,
    }
    if raw:
        out["description"] = raw
    return out


def _build_security_schemes(plan: NormalizationPlan) -> dict:
    out: dict = {}
    for idx, scheme in enumerate(plan.security_schemes):
        name = scheme.name or f"scheme{idx}"
        out[name] = _build_security_scheme(scheme)
    return out


def build_openapi(plan: NormalizationPlan) -> dict:
    doc: dict = {"openapi": "3.1.0", "info": _build_info(plan)}
    servers = _build_servers(plan)
    if servers:
        doc["servers"] = servers
    doc["paths"] = {}
    components: dict = {}
    security_schemes = _build_security_schemes(plan)
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        doc["components"] = components
    return doc
```

- [ ] **Step 4：執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/generate/test_openapi.py -v`
Expected: PASS（8 passed）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/generate/openapi.py tests/generate/test_openapi.py
git commit -m "feat: [generate] build OpenAPI 3.1 skeleton (info/servers/security)"
```

---

### Task 3：OpenAPI paths（operations／parameters／requestBody／responses）

把 `plan.endpoints` 組裝成 `paths`。只有同時具備 `path` 與 `method` 的 endpoint 能進入 paths；缺其一者略過（由 Task 5 provenance 記為 `missing`）。每個 operation 至少要有 `responses`；來源未提供回應時填 `default` 占位＋`x-loop-status`。

**Files:**
- Modify: `loop_apidoc/generate/openapi.py`
- Modify: `tests/generate/test_openapi.py`

**Interfaces:**
- Consumes: Task 2 的 `_schema_from_type`、`X_LOOP_STATUS`、`MISSING_STATUS`；`loop_apidoc.plan.models.EndpointEntry`。
- Produces：`build_openapi` 的 `paths` 由 `_build_paths(plan)` 填入。新增 helper：`_build_paths`、`_build_operation`、`_build_parameter`、`_build_request_body`、`_build_responses`。
  - 容忍式輸入契約（自由格式 dict）：
    - parameter dict：`name`（必要，無則略過該參數）、`in`／`location`（預設 `query`，非 `query|path|header|cookie` 則退回 `query`）、`required`（path 一律 `True`）、`type`／`schema`、`description`。
    - request dict：`schema`、`content_type`（預設 `application/json`）、`required`、`description`。
    - response dict：`status`（必要，無則略過）、`description`、`schema`、`content_type`。

- [ ] **Step 1：在 `tests/generate/test_openapi.py` 末尾追加失敗測試**

```python
from loop_apidoc.plan.models import EndpointEntry  # add to existing imports block


def test_endpoint_becomes_path_operation():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List users",
            parameters=[{"name": "limit", "in": "query", "type": "integer"}],
            responses=[{"status": "200", "description": "ok", "schema": {"type": "array"}}],
        )
    ])
    op = build_openapi(plan)["paths"]["/users"]["get"]
    assert op["summary"] == "List users"
    assert op["parameters"] == [
        {"name": "limit", "in": "query", "schema": {"type": "integer"}}
    ]
    assert op["responses"]["200"]["description"] == "ok"
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {"type": "array"}


def test_path_parameter_forced_required():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="get", path="/users/{id}",
            parameters=[{"name": "id", "in": "path", "type": "string"}],
            responses=[{"status": "200", "description": "ok"}],
        )
    ])
    param = build_openapi(plan)["paths"]["/users/{id}"]["get"]["parameters"][0]
    assert param["required"] is True


def test_request_body_mapped():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/users",
            request={"schema": {"type": "object"}, "required": True},
            responses=[{"status": "201", "description": "created"}],
        )
    ])
    body = build_openapi(plan)["paths"]["/users"]["post"]["requestBody"]
    assert body["required"] is True
    assert body["content"]["application/json"]["schema"] == {"type": "object"}


def test_missing_responses_get_default_placeholder():
    plan = _plan(endpoints=[
        EndpointEntry(status=PlanItemStatus.SUPPORTED, method="GET", path="/ping")
    ])
    responses = build_openapi(plan)["paths"]["/ping"]["get"]["responses"]
    assert responses["default"][X_LOOP_STATUS] == MISSING_STATUS


def test_endpoint_without_path_or_method_skipped():
    plan = _plan(endpoints=[
        EndpointEntry(status=PlanItemStatus.MISSING, method=None, path="/x"),
        EndpointEntry(status=PlanItemStatus.MISSING, method="GET", path=None),
    ])
    assert build_openapi(plan)["paths"] == {}
```

- [ ] **Step 2：執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/generate/test_openapi.py -v`
Expected: FAIL（5 個新測試 fail：`paths` 仍為 `{}`）。

- [ ] **Step 3：在 `loop_apidoc/generate/openapi.py` 加入 paths helper 並接上 `build_openapi`**

在 `_build_security_schemes` 之後、`build_openapi` 之前插入：

```python
_PARAMETER_LOCATIONS = {"query", "path", "header", "cookie"}


def _build_parameter(raw: dict) -> dict | None:
    name = raw.get("name")
    if not name:
        return None
    location = raw.get("in") or raw.get("location") or "query"
    if location not in _PARAMETER_LOCATIONS:
        location = "query"
    param: dict = {"name": name, "in": location}
    if location == "path":
        param["required"] = True
    elif "required" in raw:
        param["required"] = bool(raw["required"])
    schema = _schema_from_type(raw.get("type") if "type" in raw else raw.get("schema"))
    if schema:
        param["schema"] = schema
    if raw.get("description"):
        param["description"] = raw["description"]
    return param


def _build_request_body(raw: dict) -> dict:
    content_type = raw.get("content_type") or "application/json"
    schema = _schema_from_type(raw.get("schema")) or {}
    body: dict = {"content": {content_type: {"schema": schema}}}
    if raw.get("required") is not None:
        body["required"] = bool(raw["required"])
    if raw.get("description"):
        body["description"] = raw["description"]
    return body


def _build_responses(responses: list[dict]) -> dict:
    out: dict = {}
    for raw in responses:
        status = str(raw.get("status") or "").strip()
        if not status:
            continue
        resp: dict = {"description": raw.get("description") or ""}
        schema = _schema_from_type(raw.get("schema"))
        if schema:
            content_type = raw.get("content_type") or "application/json"
            resp["content"] = {content_type: {"schema": schema}}
        out[status] = resp
    if not out:
        out["default"] = {
            "description": "來源未提供回應定義",
            X_LOOP_STATUS: MISSING_STATUS,
        }
    return out


def _build_operation(endpoint) -> dict:
    op: dict = {}
    if endpoint.summary:
        op["summary"] = endpoint.summary
    params = [p for p in (_build_parameter(r) for r in endpoint.parameters) if p]
    if params:
        op["parameters"] = params
    if endpoint.request:
        op["requestBody"] = _build_request_body(endpoint.request)
    op["responses"] = _build_responses(endpoint.responses)
    return op


def _build_paths(plan: NormalizationPlan) -> dict:
    paths: dict = {}
    for endpoint in plan.endpoints:
        if not endpoint.path or not endpoint.method:
            continue
        method = endpoint.method.lower()
        paths.setdefault(endpoint.path, {})[method] = _build_operation(endpoint)
    return paths
```

把 `build_openapi` 中的 `doc["paths"] = {}` 改成：

```python
    doc["paths"] = _build_paths(plan)
```

- [ ] **Step 4：執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/generate/test_openapi.py -v`
Expected: PASS（13 passed）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/generate/openapi.py tests/generate/test_openapi.py
git commit -m "feat: [generate] build OpenAPI paths from plan endpoints"
```

---

### Task 4：OpenAPI components.schemas（共用 schema／enum／constraints）

把 `plan.schemas` 組裝成 `components.schemas`。每個 `SchemaEntry` → 一個 `type: object`，欄位映射為 `properties`，`required` 欄位收集成 `required` 陣列，欄位上的 enum 與 schema 級 `constraints`／具名 `enums` 原樣保留（不推測）。

**Files:**
- Modify: `loop_apidoc/generate/openapi.py`
- Modify: `tests/generate/test_openapi.py`

**Interfaces:**
- Consumes: Task 2 的 `_schema_from_type`；`loop_apidoc.plan.models.SchemaEntry`。
- Produces：`build_openapi` 的 `components.schemas` 由 `_build_schemas(plan)` 填入。新增 helper：`_build_schemas`、`_build_object_schema`。
  - field dict 契約：`name`（必要，無則略過）、`type`／`schema`、`required`（bool）、`description`、`enum`（list，原樣）。
  - schema 級：`constraints`（str→`description`）、`enums`（list of `{name, values}`→額外具名 enum component，`{"type": "string", "enum": values}`，無 name 或 values 則略過）。

- [ ] **Step 1：在 `tests/generate/test_openapi.py` 追加失敗測試**

```python
from loop_apidoc.plan.models import SchemaEntry  # add to existing imports block


def test_schema_object_with_required_and_enum_field():
    plan = _plan(schemas=[
        SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="User",
            fields=[
                {"name": "id", "type": "string", "required": True},
                {"name": "role", "type": "string", "enum": ["admin", "user"]},
            ],
            constraints="id 為 UUID v4",
        )
    ])
    schemas = build_openapi(plan)["components"]["schemas"]
    user = schemas["User"]
    assert user["type"] == "object"
    assert user["properties"]["id"] == {"type": "string"}
    assert user["properties"]["role"]["enum"] == ["admin", "user"]
    assert user["required"] == ["id"]
    assert user["description"] == "id 為 UUID v4"


def test_named_enum_becomes_component():
    plan = _plan(schemas=[
        SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="Order",
            fields=[{"name": "status", "type": "string"}],
            enums=[{"name": "OrderStatus", "values": ["new", "paid"]}],
        )
    ])
    schemas = build_openapi(plan)["components"]["schemas"]
    assert schemas["OrderStatus"] == {"type": "string", "enum": ["new", "paid"]}


def test_schema_without_name_skipped():
    plan = _plan(schemas=[SchemaEntry(status=PlanItemStatus.MISSING)])
    doc = build_openapi(plan)
    assert "schemas" not in doc.get("components", {})
```

- [ ] **Step 2：執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/generate/test_openapi.py -v`
Expected: FAIL（3 個新測試 fail）。

- [ ] **Step 3：在 `loop_apidoc/generate/openapi.py` 加入 schemas helper 並接上 `build_openapi`**

在 `_build_paths` 之後插入：

```python
def _build_object_schema(entry) -> dict:
    properties: dict = {}
    required: list[str] = []
    for field in entry.fields:
        name = field.get("name")
        if not name:
            continue
        prop = _schema_from_type(field.get("type") if "type" in field else field.get("schema")) or {}
        if field.get("description"):
            prop["description"] = field["description"]
        if field.get("enum"):
            prop["enum"] = field["enum"]
        properties[name] = prop
        if field.get("required"):
            required.append(name)
    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    if entry.constraints:
        schema["description"] = entry.constraints
    return schema


def _build_schemas(plan: NormalizationPlan) -> dict:
    out: dict = {}
    for entry in plan.schemas:
        if entry.name:
            out[entry.name] = _build_object_schema(entry)
        for enum in entry.enums:
            enum_name = enum.get("name")
            values = enum.get("values")
            if enum_name and values:
                out[enum_name] = {"type": "string", "enum": values}
    return out
```

把 `build_openapi` 中組 `components` 的段落改成（在 `security_schemes` 之前加入 schemas）：

```python
    components: dict = {}
    schemas = _build_schemas(plan)
    if schemas:
        components["schemas"] = schemas
    security_schemes = _build_security_schemes(plan)
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        doc["components"] = components
```

- [ ] **Step 4：執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/generate/test_openapi.py -v`
Expected: PASS（16 passed）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/generate/openapi.py tests/generate/test_openapi.py
git commit -m "feat: [generate] build OpenAPI components.schemas from plan"
```

---

### Task 5：來源追溯（provenance）

把計畫中每個輸出項目映射成 `ProvenanceEntry`，`target` 字串對齊 OpenAPI 位置（見上方「target 命名規則」），`status` 取自項目本身，來源欄位取自第一筆 `SourceCitation`（多 citation 各出一筆 entry）。同時把 `missing_items`／`source_conflicts`／`unverified_items` 也納入 provenance。

**Files:**
- Create: `loop_apidoc/generate/provenance.py`
- Create: `tests/generate/test_provenance.py`

**Interfaces:**
- Consumes: `loop_apidoc.plan.models`（全部 entry 型別＋三個 list 型別）；`loop_apidoc.generate.models`（`ProvenanceEntry`、`ProvenanceDocument`）。
- Produces：`build_provenance(plan: NormalizationPlan) -> ProvenanceDocument`。entry 產生順序：info.title → info.version → servers → securitySchemes → paths → schemas → errors → operational → missing → conflict → unverified。

- [ ] **Step 1：寫失敗測試 `tests/generate/test_provenance.py`**

```python
from __future__ import annotations

from loop_apidoc.generate.provenance import build_provenance
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    MissingItem,
    NormalizationPlan,
    PlanItemStatus,
    SchemaEntry,
    SecuritySchemeEntry,
    SourceCitation,
    SourceConflict,
    SystemGroup,
    UnverifiedItem,
)


def _cite(**kw):
    return SourceCitation(query_id="q1", answer_path="answers/q1.txt", **kw)


def _targets(doc) -> dict[str, list]:
    out: dict[str, list] = {}
    for entry in doc.entries:
        out.setdefault(entry.target, []).append(entry)
    return out


def test_endpoint_target_and_citation():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
                citations=[_cite(manifest_source="api.md", locator="p.2")],
            )
        ],
    )
    doc = build_provenance(plan)
    assert doc.notebook_url == "https://nb/x"
    entry = _targets(doc)["paths./users.get"][0]
    assert entry.status is PlanItemStatus.SUPPORTED
    assert entry.manifest_source == "api.md"
    assert entry.query_id == "q1"
    assert entry.answer_path == "answers/q1.txt"
    assert entry.locator == "p.2"


def test_info_targets_present():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="API")],
        environments=[EnvironmentEntry(status=PlanItemStatus.SUPPORTED, version="1")],
    )
    targets = _targets(build_provenance(plan))
    assert "info.title" in targets
    assert "info.version" in targets


def test_info_missing_status_when_absent():
    targets = _targets(build_provenance(NormalizationPlan(notebook_url="https://nb/x")))
    assert targets["info.title"][0].status is PlanItemStatus.MISSING
    assert targets["info.version"][0].status is PlanItemStatus.MISSING


def test_server_target_indexed():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        environments=[
            EnvironmentEntry(
                status=PlanItemStatus.SUPPORTED, base_url="https://a",
                citations=[_cite(manifest_source="env.md")],
            )
        ],
    )
    assert "servers[0]" in _targets(build_provenance(plan))


def test_security_schema_error_operational_targets():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth",
            citations=[_cite()])],
        schemas=[SchemaEntry(status=PlanItemStatus.SUPPORTED, name="User",
                             citations=[_cite()])],
    )
    targets = _targets(build_provenance(plan))
    assert "components.securitySchemes.ApiKeyAuth" in targets
    assert "components.schemas.User" in targets


def test_missing_conflict_unverified_included():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        missing_items=[MissingItem(area="05", detail="no endpoints", query_id="05-initial")],
        source_conflicts=[SourceConflict(area="03", detail="two base urls")],
        unverified_items=[UnverifiedItem(area="06", detail="/x")],
    )
    targets = _targets(build_provenance(plan))
    assert targets["missing.05"][0].status is PlanItemStatus.MISSING
    assert targets["missing.05"][0].query_id == "05-initial"
    assert targets["conflict.03"][0].status is PlanItemStatus.CONFLICTING
    assert targets["unverified.06"][0].status is PlanItemStatus.UNVERIFIED


def test_endpoint_without_path_skipped_from_paths_target():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[EndpointEntry(status=PlanItemStatus.MISSING, method="GET", path=None,
                                 citations=[_cite()])],
    )
    assert not any(t.startswith("paths.") for t in _targets(build_provenance(plan)))
```

- [ ] **Step 2：執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/generate/test_provenance.py -v`
Expected: FAIL（`ModuleNotFoundError: loop_apidoc.generate.provenance`）。

- [ ] **Step 3：實作 `loop_apidoc/generate/provenance.py`**

```python
from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceDocument, ProvenanceEntry
from loop_apidoc.plan.models import NormalizationPlan, PlanItemStatus


def _entries(target: str, cited) -> list[ProvenanceEntry]:
    if not cited.citations:
        return [ProvenanceEntry(target=target, status=cited.status)]
    return [
        ProvenanceEntry(
            target=target,
            status=cited.status,
            manifest_source=c.manifest_source,
            query_id=c.query_id,
            answer_path=c.answer_path,
            locator=c.locator,
        )
        for c in cited.citations
    ]


def _info_entries(plan: NormalizationPlan) -> list[ProvenanceEntry]:
    title = plan.system_groups[0].name if plan.system_groups else None
    version = next((e.version for e in plan.environments if e.version), None)
    return [
        ProvenanceEntry(
            target="info.title",
            status=PlanItemStatus.SUPPORTED if title else PlanItemStatus.MISSING,
        ),
        ProvenanceEntry(
            target="info.version",
            status=PlanItemStatus.SUPPORTED if version else PlanItemStatus.MISSING,
        ),
    ]


def build_provenance(plan: NormalizationPlan) -> ProvenanceDocument:
    entries: list[ProvenanceEntry] = list(_info_entries(plan))

    server_idx = 0
    for env in plan.environments:
        if not env.base_url:
            continue
        entries.extend(_entries(f"servers[{server_idx}]", env))
        server_idx += 1

    for idx, scheme in enumerate(plan.security_schemes):
        name = scheme.name or f"scheme{idx}"
        entries.extend(_entries(f"components.securitySchemes.{name}", scheme))

    for endpoint in plan.endpoints:
        if not endpoint.path or not endpoint.method:
            continue
        entries.extend(_entries(f"paths.{endpoint.path}.{endpoint.method.lower()}", endpoint))

    for schema in plan.schemas:
        if schema.name:
            entries.extend(_entries(f"components.schemas.{schema.name}", schema))

    for error in plan.errors:
        if error.code:
            entries.extend(_entries(f"errors.{error.code}", error))

    for op in plan.operational:
        if op.topic:
            entries.extend(_entries(f"operational.{op.topic}", op))

    for item in plan.missing_items:
        entries.append(ProvenanceEntry(
            target=f"missing.{item.area}", status=PlanItemStatus.MISSING,
            query_id=item.query_id))
    for item in plan.source_conflicts:
        entries.append(ProvenanceEntry(
            target=f"conflict.{item.area}", status=PlanItemStatus.CONFLICTING,
            query_id=item.query_id))
    for item in plan.unverified_items:
        entries.append(ProvenanceEntry(
            target=f"unverified.{item.area}", status=PlanItemStatus.UNVERIFIED,
            query_id=item.query_id))

    return ProvenanceDocument(notebook_url=plan.notebook_url, entries=entries)
```

- [ ] **Step 4：執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/generate/test_provenance.py -v`
Expected: PASS（7 passed）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/generate/provenance.py tests/generate/test_provenance.py
git commit -m "feat: [generate] build provenance mapping aligned to OpenAPI targets"
```

---

### Task 6：繁體中文 Markdown（固定章節）

把計畫組裝成 `api-guide.zh-TW.md`：固定 10 個 `## ` 章節（順序逐字如「Markdown 固定章節」表），敘述繁中、API 名稱保留原文（path／欄位／enum／header／參數以 backtick code span 或 fenced block 呈現）。匯出 `REQUIRED_MARKDOWN_SECTIONS` 供 Plan 5 §9.1 章節檢查重用。

**Files:**
- Create: `loop_apidoc/generate/markdown.py`
- Create: `tests/generate/test_markdown.py`

**Interfaces:**
- Consumes: `loop_apidoc.plan.models.NormalizationPlan`、`loop_apidoc.manifest.models.Manifest`。
- Produces：
  - `REQUIRED_MARKDOWN_SECTIONS: tuple[str, ...]`：10 個章節標題（含前綴 `## `），順序逐字如上表。
  - `build_markdown(plan: NormalizationPlan, manifest: Manifest) -> str`：第一行為 `# {title}`（title 同 OpenAPI info.title 規則），其後依序輸出 10 章節；每章節即使無資料也要輸出標題（內容空時填「來源未提供」字句），確保 Plan 5 章節存在性檢查恆過。

- [ ] **Step 1：寫失敗測試 `tests/generate/test_markdown.py`**

```python
from __future__ import annotations

from datetime import datetime

from loop_apidoc.generate.markdown import REQUIRED_MARKDOWN_SECTIONS, build_markdown
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    ErrorEntry,
    MissingItem,
    NormalizationPlan,
    PlanItemStatus,
    SecuritySchemeEntry,
    SystemGroup,
)

_NOW = datetime(2026, 6, 25, 12, 0, 0)


def _manifest() -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="api.md", mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN, size_bytes=10,
                sha256="abc", scanned_at=_NOW, supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )


def _full_plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="Loop Payments API")],
        overview_note="這是支付 API。",
        environments=[EnvironmentEntry(
            status=PlanItemStatus.SUPPORTED, name="prod",
            base_url="https://api.example.com", version="2024-01")],
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth",
            type="apiKey", location="header", details="X-API-Key")],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List users",
            examples=[{"title": "list", "body": "GET /users"}])],
        errors=[ErrorEntry(status=PlanItemStatus.SUPPORTED, code="40001",
                           meaning="參數錯誤", http_status="400")],
        missing_items=[MissingItem(area="09", detail="未提供 rate limit")],
    )


def test_all_required_sections_present_and_ordered():
    md = build_markdown(_full_plan(), _manifest())
    positions = [md.find(section) for section in REQUIRED_MARKDOWN_SECTIONS]
    assert all(p >= 0 for p in positions)
    assert positions == sorted(positions)


def test_title_heading_first_line():
    md = build_markdown(_full_plan(), _manifest())
    assert md.splitlines()[0] == "# Loop Payments API"


def test_original_api_names_preserved():
    md = build_markdown(_full_plan(), _manifest())
    assert "`/users`" in md
    assert "`GET`" in md
    assert "`X-API-Key`" in md
    assert "`40001`" in md


def test_source_listed_in_scope_section():
    md = build_markdown(_full_plan(), _manifest())
    assert "api.md" in md


def test_missing_item_surfaced():
    md = build_markdown(_full_plan(), _manifest())
    assert "未提供 rate limit" in md


def test_empty_plan_still_has_all_sections():
    md = build_markdown(NormalizationPlan(notebook_url="https://nb/x"), _manifest())
    for section in REQUIRED_MARKDOWN_SECTIONS:
        assert section in md
```

- [ ] **Step 2：執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/generate/test_markdown.py -v`
Expected: FAIL（`ModuleNotFoundError: loop_apidoc.generate.markdown`）。

- [ ] **Step 3：實作 `loop_apidoc/generate/markdown.py`**

```python
from __future__ import annotations

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan

REQUIRED_MARKDOWN_SECTIONS: tuple[str, ...] = (
    "## 文件範圍與來源",
    "## 串接前置條件",
    "## 環境與 base URL",
    "## 驗證／授權",
    "## 共用規則",
    "## Endpoint",
    "## Request／Response 範例",
    "## 錯誤碼",
    "## 限制與注意事項",
    "## 已知缺漏與來源衝突",
)

_EMPTY = "_來源未提供此項資訊。_"


def _title(plan: NormalizationPlan) -> str:
    return plan.system_groups[0].name if plan.system_groups else "Untitled API"


def _scope(plan: NormalizationPlan, manifest: Manifest) -> list[str]:
    lines = [plan.overview_note or _EMPTY, "", "本文件涵蓋的來源："]
    sources = [s.relative_path for s in manifest.local_sources]
    sources += [u.url for u in manifest.url_sources]
    if sources:
        lines += [f"- `{s}`" for s in sources]
    else:
        lines.append(_EMPTY)
    return lines


def _environments(plan: NormalizationPlan) -> list[str]:
    rows = [e for e in plan.environments if e.base_url or e.name or e.version]
    if not rows:
        return [_EMPTY]
    out = ["| 環境 | base URL | 版本 |", "| --- | --- | --- |"]
    for e in rows:
        out.append(f"| {e.name or '-'} | `{e.base_url or '-'}` | `{e.version or '-'}` |")
    return out


def _security(plan: NormalizationPlan) -> list[str]:
    if not plan.security_schemes:
        return [_EMPTY]
    out = []
    for s in plan.security_schemes:
        out.append(f"- **{s.name or '-'}**（type：`{s.type or '-'}`，位置：`{s.location or '-'}`，"
                   f"名稱：`{s.details or '-'}`）")
    return out


def _schemas(plan: NormalizationPlan) -> list[str]:
    if not plan.schemas:
        return [_EMPTY]
    out = []
    for s in plan.schemas:
        out.append(f"### `{s.name or '-'}`")
        if s.constraints:
            out.append(s.constraints)
        for f in s.fields:
            name = f.get("name")
            if not name:
                continue
            enum = f.get("enum")
            enum_text = f"，enum：{enum}" if enum else ""
            out.append(f"- `{name}`：型別 `{f.get('type') or '-'}`"
                       f"{'（必填）' if f.get('required') else ''}{enum_text}")
    return out


def _endpoints(plan: NormalizationPlan) -> list[str]:
    rows = [e for e in plan.endpoints if e.path or e.method]
    if not rows:
        return [_EMPTY]
    out = []
    for e in rows:
        out.append(f"### `{e.method or '-'}` `{e.path or '-'}`")
        if e.summary:
            out.append(e.summary)
        for p in e.parameters:
            name = p.get("name")
            if name:
                out.append(f"- 參數 `{name}`（位置 `{p.get('in') or p.get('location') or '-'}`，"
                           f"型別 `{p.get('type') or '-'}`）")
        for r in e.responses:
            status = r.get("status")
            if status:
                out.append(f"- 回應 `{status}`：{r.get('description') or '-'}")
    return out


def _examples(plan: NormalizationPlan) -> list[str]:
    out = []
    for e in plan.endpoints:
        for ex in e.examples:
            body = ex.get("body") or ex.get("value")
            if body is None:
                continue
            title = ex.get("title") or f"{e.method or ''} {e.path or ''}".strip()
            out.append(f"**{title}**")
            out.append("```")
            out.append(str(body))
            out.append("```")
    return out or [_EMPTY]


def _errors(plan: NormalizationPlan) -> list[str]:
    if not plan.errors:
        return [_EMPTY]
    out = ["| code | HTTP | 意義 |", "| --- | --- | --- |"]
    for e in plan.errors:
        out.append(f"| `{e.code or '-'}` | `{e.http_status or '-'}` | {e.meaning or '-'} |")
    return out


def _operational(plan: NormalizationPlan) -> list[str]:
    if not plan.operational:
        return [_EMPTY]
    return [f"- **{o.topic or '-'}**：{o.detail or '-'}" for o in plan.operational]


def _gaps(plan: NormalizationPlan) -> list[str]:
    out: list[str] = []
    if plan.missing_items:
        out.append("**已知缺漏：**")
        out += [f"- [{m.area}] {m.detail}" for m in plan.missing_items]
    if plan.source_conflicts:
        out.append("**來源衝突：**")
        out += [f"- [{c.area}] {c.detail}" for c in plan.source_conflicts]
    if plan.unverified_items:
        out.append("**無法確認：**")
        out += [f"- [{u.area}] {u.detail}" for u in plan.unverified_items]
    if plan.conflicts_note:
        out += ["", plan.conflicts_note]
    return out or [_EMPTY]


def build_markdown(plan: NormalizationPlan, manifest: Manifest) -> str:
    sections = [
        _scope(plan, manifest),
        ["完成串接前，請先確認已取得 Notebook 對應的來源並完成驗證設定。"],
        _environments(plan),
        _security(plan),
        _schemas(plan),
        _endpoints(plan),
        _examples(plan),
        _errors(plan),
        _operational(plan),
        _gaps(plan),
    ]
    lines = [f"# {_title(plan)}", ""]
    for heading, body in zip(REQUIRED_MARKDOWN_SECTIONS, sections):
        lines.append(heading)
        lines.append("")
        lines.extend(body)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4：執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/generate/test_markdown.py -v`
Expected: PASS（6 passed）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/generate/markdown.py tests/generate/test_markdown.py
git commit -m "feat: [generate] build zh-TW markdown guide with fixed sections"
```

---

### Task 7：序列化 seam（writer）＋整合測試

新增唯一檔案 I/O 邊界 `generate_outputs()`（供 Plan 5/6 串接）與純函式 `build_result()`，把三個 builder 彙整、序列化成 `openapi.yaml`／`api-guide.zh-TW.md`／`provenance.json`。整合測試驗證：完整計畫產出可通過 `openapi-spec-validator`、Markdown 含全部章節、provenance target 對齊、缺漏案例正確標記。

**Files:**
- Create: `loop_apidoc/generate/writer.py`
- Modify: `loop_apidoc/generate/__init__.py`
- Create: `tests/generate/test_writer.py`
- Create: `tests/integration/test_plan_to_outputs.py`

**Interfaces:**
- Consumes: `build_openapi`、`build_markdown`、`build_provenance`、`GenerateResult`。
- Produces：
  - `build_result(plan: NormalizationPlan, manifest: Manifest) -> GenerateResult`（純函式、無 I/O）。
  - `generate_outputs(plan: NormalizationPlan, manifest: Manifest, run_dir: Path) -> GenerateResult`：`run_dir.mkdir(parents=True, exist_ok=True)` 後寫三檔（YAML 用 `yaml.safe_dump(..., sort_keys=False, allow_unicode=True)`；provenance 用 `model_dump_json(indent=2)`），回傳同一 `GenerateResult`。
  - `loop_apidoc/generate/__init__.py` 重新匯出 `generate_outputs`、`build_result`、`GenerateResult`、`ProvenanceDocument`、`REQUIRED_MARKDOWN_SECTIONS`。

- [ ] **Step 1：寫失敗測試 `tests/generate/test_writer.py`**

```python
from __future__ import annotations

from datetime import datetime

import yaml

from loop_apidoc.generate.writer import build_result, generate_outputs
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import (
    EndpointEntry,
    NormalizationPlan,
    PlanItemStatus,
)

_NOW = datetime(2026, 6, 25, 12, 0, 0)


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/ping",
            responses=[{"status": "200", "description": "ok"}])],
    )


def _manifest() -> Manifest:
    return Manifest(sources_root="./s", generated_at=_NOW)


def test_build_result_holds_three_artifacts():
    result = build_result(_plan(), _manifest())
    assert result.openapi["openapi"] == "3.1.0"
    assert result.markdown.startswith("#")
    assert result.provenance.notebook_url == "https://nb/x"


def test_generate_outputs_writes_three_files(tmp_path):
    result = generate_outputs(_plan(), _manifest(), tmp_path)
    openapi_file = tmp_path / "openapi.yaml"
    md_file = tmp_path / "api-guide.zh-TW.md"
    prov_file = tmp_path / "provenance.json"
    assert openapi_file.exists() and md_file.exists() and prov_file.exists()
    loaded = yaml.safe_load(openapi_file.read_text(encoding="utf-8"))
    assert loaded["paths"]["/ping"]["get"]["responses"]["200"]["description"] == "ok"
    assert result.openapi == loaded


def test_generate_outputs_creates_nested_run_dir(tmp_path):
    run_dir = tmp_path / "output" / "run-1"
    generate_outputs(_plan(), _manifest(), run_dir)
    assert (run_dir / "openapi.yaml").exists()
```

- [ ] **Step 2：執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/generate/test_writer.py -v`
Expected: FAIL（`ModuleNotFoundError: loop_apidoc.generate.writer`）。

- [ ] **Step 3：實作 `loop_apidoc/generate/writer.py`**

```python
from __future__ import annotations

from pathlib import Path

import yaml

from loop_apidoc.generate.markdown import build_markdown
from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.generate.openapi import build_openapi
from loop_apidoc.generate.provenance import build_provenance
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import NormalizationPlan


def build_result(plan: NormalizationPlan, manifest: Manifest) -> GenerateResult:
    return GenerateResult(
        openapi=build_openapi(plan),
        markdown=build_markdown(plan, manifest),
        provenance=build_provenance(plan),
    )


def generate_outputs(
    plan: NormalizationPlan, manifest: Manifest, run_dir: Path
) -> GenerateResult:
    result = build_result(plan, manifest)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "openapi.yaml").write_text(
        yaml.safe_dump(result.openapi, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (run_dir / "api-guide.zh-TW.md").write_text(result.markdown, encoding="utf-8")
    (run_dir / "provenance.json").write_text(
        result.provenance.model_dump_json(indent=2), encoding="utf-8"
    )
    return result
```

- [ ] **Step 4：更新 `loop_apidoc/generate/__init__.py` 重新匯出公開 seam**

```python
"""Standardized output generation layer (spec §8)."""

from loop_apidoc.generate.markdown import REQUIRED_MARKDOWN_SECTIONS
from loop_apidoc.generate.models import (
    GenerateResult,
    ProvenanceDocument,
    ProvenanceEntry,
)
from loop_apidoc.generate.writer import build_result, generate_outputs

__all__ = [
    "REQUIRED_MARKDOWN_SECTIONS",
    "GenerateResult",
    "ProvenanceDocument",
    "ProvenanceEntry",
    "build_result",
    "generate_outputs",
]
```

- [ ] **Step 5：執行 writer 測試確認通過**

Run: `.venv/bin/python -m pytest tests/generate/test_writer.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 6：寫整合測試 `tests/integration/test_plan_to_outputs.py`**

```python
from __future__ import annotations

from datetime import datetime

from openapi_spec_validator import validate

from loop_apidoc.generate import REQUIRED_MARKDOWN_SECTIONS, build_result
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    ErrorEntry,
    NormalizationPlan,
    PlanItemStatus,
    SchemaEntry,
    SecuritySchemeEntry,
    SourceCitation,
    SystemGroup,
)

_NOW = datetime(2026, 6, 25, 12, 0, 0)


def _cite() -> SourceCitation:
    return SourceCitation(query_id="06-initial", answer_path="answers/06-initial.txt",
                          manifest_source="api.md", locator="p.3")


def _manifest() -> Manifest:
    return Manifest(
        sources_root="./sources", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="api.md", mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=10, sha256="abc",
            scanned_at=_NOW, supported=True, status=ProcessingStatus.PENDING)],
    )


def _full_plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="Loop Payments API")],
        overview_note="支付 API。",
        environments=[EnvironmentEntry(
            status=PlanItemStatus.SUPPORTED, name="prod",
            base_url="https://api.example.com", version="2024-01",
            citations=[_cite()])],
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth", type="apiKey",
            location="header", details="X-API-Key", citations=[_cite()])],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List users",
            parameters=[{"name": "limit", "in": "query", "type": "integer"}],
            responses=[{"status": "200", "description": "ok",
                        "schema": {"type": "array"}}],
            citations=[_cite()])],
        schemas=[SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="User",
            fields=[{"name": "id", "type": "string", "required": True}],
            citations=[_cite()])],
        errors=[ErrorEntry(status=PlanItemStatus.SUPPORTED, code="40001",
                           meaning="參數錯誤", http_status="400", citations=[_cite()])],
    )


def test_full_plan_produces_valid_openapi():
    result = build_result(_full_plan(), _manifest())
    validate(result.openapi)  # raises on invalid 3.1 document


def test_markdown_has_all_sections():
    md = build_result(_full_plan(), _manifest()).markdown
    for section in REQUIRED_MARKDOWN_SECTIONS:
        assert section in md


def test_provenance_targets_align_with_openapi():
    result = build_result(_full_plan(), _manifest())
    targets = {e.target for e in result.provenance.entries}
    assert "paths./users.get" in targets
    assert "components.schemas.User" in targets
    assert "components.securitySchemes.ApiKeyAuth" in targets
    assert "servers[0]" in targets
    supported = next(e for e in result.provenance.entries
                     if e.target == "paths./users.get")
    assert supported.status is PlanItemStatus.SUPPORTED
    assert supported.manifest_source == "api.md"


def test_missing_source_marked_in_openapi_and_provenance():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[EndpointEntry(status=PlanItemStatus.SUPPORTED,
                                 method="GET", path="/ping")],
    )
    result = build_result(plan, _manifest())
    validate(result.openapi)
    responses = result.openapi["paths"]["/ping"]["get"]["responses"]
    assert responses["default"]["x-loop-status"] == "missing-source"
    info = result.openapi["info"]
    assert info["x-loop-status"] == "missing-source"
    statuses = {e.target: e.status for e in result.provenance.entries}
    assert statuses["info.title"] is PlanItemStatus.MISSING
```

- [ ] **Step 7：執行整合測試確認通過**

Run: `.venv/bin/python -m pytest tests/integration/test_plan_to_outputs.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 8：執行全套件確認無回歸**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS（全部既有 105＋本計畫新增測試）。

- [ ] **Step 9：Commit**

```bash
git add loop_apidoc/generate/writer.py loop_apidoc/generate/__init__.py tests/generate/test_writer.py tests/integration/test_plan_to_outputs.py
git commit -m "feat: [generate] add generate_outputs seam and plan-to-outputs integration tests"
```

---

## Carry-forward 給 Plan 5／6

- **security scheme 型別映射**：本計畫只辨識 OpenAPI 合法 `type`；無法對映者以 `apiKey`＋`x-loop-status: missing-source` 占位。Plan 5 §9.4 應把帶 `x-loop-status` 的 security scheme 視為 `UNSUPPORTED_ASSERTION`／需來源補強。
- **深層 schema／`$ref`**：parameter／request／response／field 採容忍式淺層映射，不解析巢狀 `$ref`。Plan 5 §9.3 共用 schema 引用一致性、example 與 schema 一致性需自行驗證。
- **info.title／info.version 的 provenance**：目前 title 來自敘事 `system_groups`（無結構化 citation），故 provenance 無 query_id／manifest_source。Plan 5 §9.4「任何規格欄位都必須存在 `supported` provenance」需決定是否要求 info 欄位連回具體 query；可能需 Plan 6 在擷取階段補一條 API 標題的結構化查詢。
- **Markdown↔OpenAPI 一致性（§9.3）**：本計畫兩者由同一計畫物件生成、天然一致，但未主動 assert。Plan 5 應以 `REQUIRED_MARKDOWN_SECTIONS` 與 OpenAPI inventory 做交叉一致性檢查。
- **CLI 串接**：`generate_outputs(plan, manifest, run_dir)` 是對外 seam；Plan 6 `run` 在擷取→計畫後呼叫它，並把 `openapi.yaml`／`api-guide.zh-TW.md`／`provenance.json` 落在 `output/<run-id>/`。
- 沿用 Plan 3 既有 carry-forward（per-endpoint fan-out、跨來源衝突自動偵測、§6 內容主題比對等）。
