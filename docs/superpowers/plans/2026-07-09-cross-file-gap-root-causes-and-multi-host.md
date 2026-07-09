# 跨檔偵測缺口、根因收斂與多主機端點 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 關閉 null-path webhook 的跨檔偵測缺口(#7),為 validation report 加上純加法的根因收斂(#4),並讓 `endpoints[]` 支援可選的 `server` 以承載多主機事實(#8)。

**Architecture:** 三項改動落在同一組檔案。#7 讓 `summary` 成為 null-path 端點的身份鍵(`generate/naming.py` 早就這樣命名 webhook),並在 `source_guard` 加一條「null path ⇒ summary 必填」的邊界檢查。#4 在 `ValidationReport` 加 `root_causes`,`issues[]` 一字不動,`ok`/exit code/score 不受影響。#8 把 `server` 從 inventory 一路接到 operation-level OpenAPI `servers`。

**Tech Stack:** Python ≥3.11、uv、pydantic v2、pytest、ruff。

## Global Constraints

- 套件管理一律 `uv`,禁用 `pip`。測試 `uv run pytest`,lint `uv run ruff check .`。
- **Source-grounded 是不可協商的核心不變式**:來源沒寫的東西一律 `null` + 記入 `missing`,絕不臆測。本計畫不得引入任何來源文件裡不存在的概念(這是 `webhook_id` 方案被否決的原因)。
- `agentcli/cross_file.py`、`agentcli/source_guard.py`、`validate/` 底下除 `report.py` 外全部是**純函式,不做檔案 I/O**。保持如此。
- `cross_file.py` 的比對**永遠 set-based,絕不 index-based**:generation 只看 `method`/`path`,不看檔名,兩個端點檔內容互換沒有下游後果、不得被拒。
- 驗證閘是 **severity 而非 issue code**:`ValidationReport.ok` 為「不存在任何 `error` severity 的 issue」。本計畫不得改變任何 issue 的 severity,也不得讓 `root_causes` 影響 `ok`。
- 程式碼註解與文件用繁體中文(台灣用語);`skills/loop-apidoc/SKILL.md` 及其 `reference/` 維持**英文**(token economy)。
- commit 格式:`<type>: [ <scope> ] <subject>`。

---

### Task 1: `cross_file` 用 summary 當 null-path 端點的身份鍵(#7)

**Files:**
- Modify: `loop_apidoc/agentcli/cross_file.py:27-33`(`_key`)、`54-57`(`_keyed`)、`60-90`(`_multiset_violations` / `_duplicate_violations`)
- Test: `tests/agentcli/test_cross_file.py`

**Interfaces:**
- Consumes: 無(本任務為起點)
- Produces: `cross_file_violations(inventory: dict, endpoints: list[tuple[str, dict]]) -> list[str]` 簽章不變。內部新增 `_norm_summary(value: Any) -> str | None`(空白正規化,非字串或空字串回 `None`)與 `_key(entry: dict) -> str | None`(**回傳型別改為 `str | None`**;無法定出身份時回 `None`)。

**關鍵設計約束(實作者必讀):**

null path **且** 沒有 summary 的條目,`_key` 回 `None`,這類條目仍**排除在不變式 2、3 之外**,行為與現況相同。理由:此時真正的問題是「缺 summary」,由 Task 2 的 `source_guard` 以 `exit 2` 講清楚;若在這裡把它們的鍵塌成 `POST ?` 再報「同一端點被寫進多個檔案」,訊息是錯的、會誤導 correction loop。缺口之所以關閉,是因為 `source_guard` 保證缺 summary 的輸入到不了 run。

- [ ] **Step 1: 改寫既有的 null-path 豁免測試,並加上失效模式測試(RED)**

取代 `tests/agentcli/test_cross_file.py` 檔案末尾「── null path 端點(webhook/callback)豁免多重集合與重複檢查 ──」整節(從 `def _null_ep` 到檔尾),換成:

```python
# ── null path 端點(webhook/callback)以 summary 當身份鍵 ──────────────

def _null_ep(summary: str | None = None, **extra) -> dict:
    return {"method": "POST", "path": None, "summary": summary, **extra}


def test_distinct_null_path_endpoints_pass():
    """多筆 path: null 端點,靠 summary 彼此區分。"""
    inventory = _inv(_null_ep("Notify"), _null_ep("Return"), _null_ep("Customer"))
    endpoints = [
        ("ep0.json", _null_ep("Notify")),
        ("ep1.json", _null_ep("Return")),
        ("ep2.json", _null_ep("Customer")),
    ]

    assert cross_file_violations(inventory, endpoints) == []


def test_two_files_writing_the_same_webhook_is_a_violation():
    """issue #7 的失效模式:兩個檔寫同一個 webhook,第三個 webhook 沒人寫。
    不變式 1(總數)看到 3 == 3 會通過 —— 必須靠不變式 2、3 抓到。"""
    inventory = _inv(_null_ep("Notify"), _null_ep("Return"), _null_ep("Customer"))
    endpoints = [
        ("ep0.json", _null_ep("Notify")),
        ("ep1.json", _null_ep("Notify")),
        ("ep2.json", _null_ep("Customer")),
    ]

    violations = cross_file_violations(inventory, endpoints)

    assert any("ep0.json" in v and "ep1.json" in v and "Notify" in v
               and "被寫進多個檔案" in v for v in violations)
    assert any("Return" in v and "沒有對應的 endpoints/*.json" in v
               for v in violations)


def test_webhook_summary_whitespace_is_normalized():
    """長敘述跨行複製容易差一個空白;正規化後仍視為同一身份。"""
    inventory = _inv(_null_ep("Notify  結果\n通知"))
    endpoints = [("ep0.json", _null_ep("Notify 結果 通知"))]

    assert cross_file_violations(inventory, endpoints) == []


def test_webhook_summary_mismatch_is_a_violation():
    inventory = _inv(_null_ep("Notify"))
    endpoints = [("ep0.json", _null_ep("Return"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("Return" in v and "不在 inventory.endpoints" in v for v in violations)
    assert any("Notify" in v and "沒有對應的 endpoints/*.json" in v for v in violations)


def test_null_path_without_summary_is_excluded_from_multiset_checks():
    """缺 summary 時無法定出身份 —— 交給 source_guard 以 exit 2 報告,
    這裡不得誤報「重複」。行為與加入 summary 之前相同。"""
    inventory = _inv(_null_ep(), _null_ep())
    endpoints = [("ep0.json", _null_ep()), ("ep1.json", _null_ep())]

    assert cross_file_violations(inventory, endpoints) == []


def test_mix_of_real_and_null_path_endpoints_passes():
    inventory = _inv(_ep("POST", "/orders"), _null_ep("Notify"), _null_ep("Return"))
    endpoints = [
        ("ep0.json", _ep("POST", "/orders")),
        ("ep1.json", _null_ep("Notify")),
        ("ep2.json", _null_ep("Return")),
    ]

    assert cross_file_violations(inventory, endpoints) == []


def test_duplicate_real_path_endpoint_is_still_reported():
    """迴歸守門:真實 path 的重複仍要被抓到。"""
    inventory = _inv(_ep("GET", "/ping"), _null_ep("Notify"))
    endpoints = [
        ("ep0.json", _ep("GET", "/ping")),
        ("ep1.json", _ep("GET", "/ping")),
        ("ep2.json", _null_ep("Notify")),
    ]

    violations = cross_file_violations(inventory, endpoints)

    assert any("ep0.json" in v and "ep1.json" in v and "GET /ping" in v
               for v in violations)


def test_null_path_count_mismatch_is_still_caught_by_invariant_1():
    """迴歸守門:檔數與 inventory 筆數不符,仍要靠不變式 1(總數)抓到。"""
    inventory = _inv(_null_ep("A"), _null_ep("B"), _null_ep("C"))
    endpoints = [("ep0.json", _null_ep("A")), ("ep1.json", _null_ep("B"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("2" in v and "3" in v and "endpoints/*.json" in v for v in violations)
```

- [ ] **Step 2: 跑測試確認失敗(RED)**

Run: `uv run pytest tests/agentcli/test_cross_file.py -v`

Expected: FAIL。`test_two_files_writing_the_same_webhook_is_a_violation` 斷言失敗(目前回傳 `[]`,這正是 issue #7 描述的靜默放行);`test_webhook_summary_mismatch_is_a_violation` 同樣失敗。

- [ ] **Step 3: 實作**

`loop_apidoc/agentcli/cross_file.py`:把 `_key`(27-33 行)與 `_keyed`(54-57 行)換成下列內容,並更新 `_multiset_violations` / `_duplicate_violations` 改用 `_key(...) is not None` 過濾。

```python
def _norm_summary(value: Any) -> str | None:
    """空白正規化:長敘述跨行複製容易差一個空白,除此之外要求逐字相符。"""
    if not isinstance(value, str):
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def _key(entry: dict) -> str | None:
    """端點的跨檔身份鍵;method 大小寫不敏感。

    有 path 用 `(method, path)`。webhook/callback 的 path 為 null,身份改用
    `summary` —— generate/naming.py 的 webhook_items 早就用 summary 命名 webhook,
    所以它本來就是 webhook 的身份。

    兩者皆無時回 None:此時真正的問題是「缺 summary」,由 source_guard 以 exit 2
    報告。在這裡把鍵塌成 `POST ?` 再報「重複」會給出錯誤訊息。
    """
    method = entry.get("method")
    method = method.upper() if isinstance(method, str) else "?"
    path = entry.get("path")
    if isinstance(path, str):
        return f"{method} {path}"
    summary = _norm_summary(entry.get("summary"))
    if summary is None:
        return None
    return f"{method} (webhook) {summary}"
```

刪除 `_keyed`。`_multiset_violations` 改為:

```python
def _multiset_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    inventory_keys = {
        key for key in (_key(e) for e in _entries(inventory, "endpoints"))
        if key is not None
    }
    keyed_endpoints = [
        (name, ep) for name, ep in endpoints if _key(ep) is not None
    ]
    file_keys = {_key(ep) for _, ep in keyed_endpoints}

    out: list[str] = []
    for key in sorted(file_keys - inventory_keys):
        files = sorted(name for name, ep in keyed_endpoints if _key(ep) == key)
        out.append(
            f"{', '.join(files)}: 端點 {key} 不在 inventory.endpoints 中"
        )
    for key in sorted(inventory_keys - file_keys):
        out.append(
            f"inventory.json: 端點 {key} 沒有對應的 endpoints/*.json"
        )
    return out
```

`_duplicate_violations` 改為:

```python
def _duplicate_violations(endpoints: list[tuple[str, dict]]) -> list[str]:
    seen: dict[str, list[str]] = {}
    for name, endpoint in endpoints:
        key = _key(endpoint)
        if key is None:
            continue
        seen.setdefault(key, []).append(name)
    return [
        f"{', '.join(sorted(files))}: 同一端點 {key} 被寫進多個檔案"
        "(兩個 subagent 寫了同一個端點,另一個端點可能因此沒人寫)"
        for key, files in sorted(seen.items()) if len(files) > 1
    ]
```

同時更新檔案頂端 docstring(1-14 行):把「這五條不變式」改為「這六條不變式」(第六條在 Task 5 加入),並把 5-7 行說明補上 null-path 端點以 summary 為身份鍵。

- [ ] **Step 4: 跑測試確認通過(GREEN)**

Run: `uv run pytest tests/agentcli/test_cross_file.py tests/agentcli/test_gate.py -v`
Expected: PASS,全部。

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/agentcli/cross_file.py tests/agentcli/test_cross_file.py
git commit -m "fix: [agentcli] null-path 端點以 summary 為跨檔身份鍵 (#7)"
```

---

### Task 2: `source_guard` 強制 null-path 端點必填 summary(#7)

**Files:**
- Modify: `loop_apidoc/agentcli/input_schema.py:104-114`(`EndpointDetailInput`)
- Modify: `loop_apidoc/agentcli/source_guard.py:1-11`(docstring)、新增 `summary_violations`、`142-152`(`check_extraction_inputs`)
- Test: `tests/agentcli/test_source_guard.py`

**Interfaces:**
- Consumes: Task 1 的 `_norm_summary` 概念(此處獨立實作,不跨模組 import——`source_guard` 與 `cross_file` 刻意互不依賴)
- Produces: `summary_violations(inventory: dict, endpoints: list[tuple[str, dict]]) -> list[str]`;`check_extraction_inputs` 簽章不變,回傳值多含 summary 違規。

- [ ] **Step 1: 寫失敗測試(RED)**

附加到 `tests/agentcli/test_source_guard.py` 末尾:

```python
# ── null path 端點必須有 summary(#7 的身份鍵) ────────────────────────

from loop_apidoc.agentcli.source_guard import summary_violations


def test_null_path_endpoint_file_without_summary_is_a_violation():
    inventory = {"endpoints": [{"method": "POST", "path": None, "summary": "Notify"}]}
    endpoints = [("ep7.json", {"method": "POST", "path": None})]

    violations = summary_violations(inventory, endpoints)

    assert any("ep7.json" in v and "summary" in v for v in violations)


def test_null_path_inventory_entry_without_summary_is_a_violation():
    inventory = {"endpoints": [{"method": "POST", "path": None}]}
    endpoints = [("ep7.json", {"method": "POST", "path": None, "summary": "Notify"})]

    violations = summary_violations(inventory, endpoints)

    assert any("inventory.json" in v and "endpoints[0].summary" in v
               for v in violations)


def test_null_path_with_summary_passes():
    inventory = {"endpoints": [{"method": "POST", "path": None, "summary": "Notify"}]}
    endpoints = [("ep7.json", {"method": "POST", "path": None, "summary": "Notify"})]

    assert summary_violations(inventory, endpoints) == []


def test_blank_summary_counts_as_absent():
    inventory = {"endpoints": [{"method": "POST", "path": None, "summary": "   "}]}
    endpoints = [("ep7.json", {"method": "POST", "path": None, "summary": "Notify"})]

    violations = summary_violations(inventory, endpoints)

    assert any("inventory.json" in v for v in violations)


def test_real_path_endpoint_needs_no_summary():
    inventory = {"endpoints": [{"method": "GET", "path": "/ping"}]}
    endpoints = [("ep0.json", {"method": "GET", "path": "/ping"})]

    assert summary_violations(inventory, endpoints) == []
```

- [ ] **Step 2: 跑測試確認失敗(RED)**

Run: `uv run pytest tests/agentcli/test_source_guard.py -v`
Expected: FAIL with `ImportError: cannot import name 'summary_violations'`

- [ ] **Step 3: 實作**

`loop_apidoc/agentcli/input_schema.py`:在 `EndpointDetailInput` 加 `summary` 欄位(緊接 `path` 之後):

```python
class EndpointDetailInput(_Lax):
    method: str | None = None
    path: str | None = None
    # null-path(webhook/callback)端點的跨檔身份鍵 —— 見 agentcli/cross_file.py。
    # 是否必填由 source_guard.summary_violations 依 path 是否為 null 決定。
    summary: str | None = None
    source: str | None = None
    parameters: list[ParamEntry] = []
    request: dict[str, Any] | None = None
    responses: list[ResponseEntry] = []
    tags: list[str] = []
    security: list[str] = []
    examples: list[Any] = []
    missing: list[Any] = []
```

`loop_apidoc/agentcli/source_guard.py`:在 `path_violations` 之後新增:

```python
def _has_summary(entry: dict) -> bool:
    value = entry.get("summary")
    return isinstance(value, str) and bool(value.strip())


def summary_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    """path 為 null 的 webhook/callback 端點,`summary` 是它唯一的身份。

    沒有它,cross_file 的多重集合與重複檢查無法區分兩個 webhook,
    subagent 把同一個 webhook 寫進兩個檔、另一個從沒被寫出,會靜默通過(issue #7)。
    """
    out: list[str] = []
    for idx, entry in enumerate(_entries(inventory, "endpoints")):
        if entry.get("path") is None and not _has_summary(entry):
            out.append(
                f"inventory.json: endpoints[{idx}].summary 為必填 —— "
                "path 為 null 的 webhook/callback 端點以 summary 為身份鍵"
            )
    for name, endpoint in endpoints:
        if endpoint.get("path") is None and not _has_summary(endpoint):
            out.append(
                f"{name}: summary 為必填 —— "
                "path 為 null 的 webhook/callback 端點以 summary 為身份鍵,"
                "且必須與 inventory.json 對應條目逐字相符"
            )
    return out
```

`check_extraction_inputs` 改為:

```python
def check_extraction_inputs(
    inventory: dict,
    endpoints: list[tuple[str, dict]],
    integration: dict | None,
    manifest: Manifest,
) -> list[str]:
    """All violations at once — the fix is one rewrite of the extraction JSON,
    so reporting only the first would force a needless round trip."""
    return (
        path_violations(inventory, endpoints)
        + summary_violations(inventory, endpoints)
        + source_violations(inventory, endpoints, integration, manifest)
    )
```

同時更新 `source_guard.py` 頂端 docstring:第 1-2 行的「the two extraction-schema contracts」改為「the three extraction-schema contracts」,並補上 `summary` 這一項。

- [ ] **Step 4: 跑測試確認通過(GREEN)**

Run: `uv run pytest tests/agentcli/ -v`
Expected: PASS,全部。

- [ ] **Step 5: Commit**

```bash
git add loop_apidoc/agentcli/source_guard.py loop_apidoc/agentcli/input_schema.py tests/agentcli/test_source_guard.py
git commit -m "fix: [agentcli] null-path 端點強制必填 summary (#7)"
```

---

### Task 3: 補上 benchmark 的 null-path summary 並確認迴歸

**Files:**
- Modify: `benchmarks/newebpay-mpg/extraction/endpoints/ep7.json`、`ep8.json`、`ep9.json`
- Test: `tests/test_benchmarks.py`(不改,只跑)

**Interfaces:**
- Consumes: Task 1 的 `_key`、Task 2 的 `summary_violations`
- Produces: 無新介面。這是**修正前會靜默放行、修正後必須仍 PASS** 的真實迴歸證據。

**背景:** `benchmarks/newebpay-mpg/` 正好是 issue #7 的形狀——三個 null-path webhook(NotifyURL / ReturnURL / CustomerURL),端點檔目前都沒有 `summary`。Task 2 之後這三個檔會被 `exit 2` 擋下,必須補上。

- [ ] **Step 1: 跑 benchmark 確認現在失敗(RED)**

Run: `uv run pytest tests/test_benchmarks.py -k newebpay -v`
Expected: FAIL —— `AssembleInputError`,訊息含 `ep7.json: summary 為必填`(若本機缺 sources,該 case 會 skip;此時改跑 Step 2 後直接進 Step 3 並在 commit message 註明 skip)。

- [ ] **Step 2: 逐字抄入 summary**

從 `benchmarks/newebpay-mpg/extraction/inventory.json` 取三筆 null-path 端點的 `summary`,逐字寫進對應的端點檔。用這支腳本做,避免手抄出錯(它依 `method` + 既有內容順序配對,寫入後請用 `git diff` 人眼確認):

```bash
uv run python - <<'PY'
import json, pathlib
root = pathlib.Path("benchmarks/newebpay-mpg/extraction")
inv = json.loads((root / "inventory.json").read_text(encoding="utf-8"))
webhooks = [e for e in inv["endpoints"] if e.get("path") is None]
# ep7/ep8/ep9 依 inventory 中 null-path 端點的出現順序對應
for filename, entry in zip(["ep7.json", "ep8.json", "ep9.json"], webhooks):
    p = root / "endpoints" / filename
    ep = json.loads(p.read_text(encoding="utf-8"))
    assert ep.get("path") is None, f"{filename} 不是 null-path 端點"
    ep["summary"] = entry["summary"]
    p.write_text(json.dumps(ep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{filename}: {entry['summary'][:40]}…")
PY
git diff --stat benchmarks/newebpay-mpg/extraction/endpoints/
```

**注意:** 腳本假設 `ep7/ep8/ep9` 的順序對應 inventory 中 null-path 端點的出現順序。寫入後必須用 `git diff` 確認每個檔的 summary 與該檔既有的 `source` / `responses` 內容相符(NotifyURL 講幕後通知、ReturnURL 講導回商店、CustomerURL 講取號結果)。若不符,手動對調。

- [ ] **Step 3: 跑 benchmark 確認通過(GREEN)**

Run: `uv run pytest tests/test_benchmarks.py -v`
Expected: PASS(或 skip,若本機無 sources)。這證明新的必填欄位沒有打破既有行為。

- [ ] **Step 4: 全套測試**

Run: `uv run pytest`
Expected: PASS,全部。

- [ ] **Step 5: Commit**

```bash
git add benchmarks/newebpay-mpg/extraction/endpoints/
git commit -m "test: [benchmarks] newebpay 三個 webhook 端點補上 summary 身份鍵 (#7)"
```

---

### Task 4: `root_causes` 根因收斂(#4)

**Files:**
- Modify: `loop_apidoc/validate/models.py:22-48`
- Create: `loop_apidoc/validate/root_cause.py`
- Modify: `loop_apidoc/validate/validator.py:29-36`
- Modify: `loop_apidoc/validate/report.py:17-32`(`render_markdown`)
- Test: `tests/validate/test_root_cause.py`(新建)
- Test: `tests/validate/test_report.py`(附加)

**Interfaces:**
- Consumes: 既有的 `Issue`(含 `code` / `severity` / `location` / `suggested_fix` / `target_file`)
- Produces:
  - `class RootCause(BaseModel)`:`code: IssueCode`、`severity: Severity`、`target_file: str`、`fix_once: str`、`affected_locations: list[str]`
  - `ValidationReport.root_causes: list[RootCause]`(預設空 list)
  - `derive_root_causes(issues: list[Issue]) -> list[RootCause]`(純函式)

- [ ] **Step 1: 寫失敗測試(RED)**

新建 `tests/validate/test_root_cause.py`:

```python
from __future__ import annotations

from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport
from loop_apidoc.validate.root_cause import derive_root_causes


def _issue(location: str, *, code=IssueCode.SOURCE_UNVERIFIED,
           severity=Severity.ERROR, target_file="integration.json",
           fix="確認來源以取得 supported 引用") -> Issue:
    return Issue(code=code, severity=severity, location=location,
                 evidence="契約條目僅有 unverified 來源", suggested_fix=fix,
                 target_file=target_file)


def test_same_code_and_target_file_converge_into_one_root_cause():
    issues = [_issue("integration.crypto.0"), _issue("integration.crypto.1")]

    causes = derive_root_causes(issues)

    assert len(causes) == 1
    assert causes[0].code is IssueCode.SOURCE_UNVERIFIED
    assert causes[0].target_file == "integration.json"
    assert causes[0].affected_locations == [
        "integration.crypto.0", "integration.crypto.1"]


def test_single_issue_is_not_a_root_cause():
    """一筆就不叫根因 —— 逐筆 issue 已經夠精確。"""
    assert derive_root_causes([_issue("integration.crypto.0")]) == []


def test_issue_without_target_file_is_not_grouped():
    """沒有可靠的一次修完目標,硬分組只會製造假的根因。"""
    issues = [_issue("unverified.06", target_file=None),
              _issue("unverified.07", target_file=None)]

    assert derive_root_causes(issues) == []


def test_different_severity_does_not_group():
    issues = [_issue("a", severity=Severity.ERROR),
              _issue("b", severity=Severity.WARNING)]

    assert derive_root_causes(issues) == []


def test_different_target_file_does_not_group():
    issues = [_issue("a", target_file="integration.json"),
              _issue("b", target_file="inventory.json")]

    assert derive_root_causes(issues) == []


def test_source_unverified_gets_a_one_shot_fix_text():
    """有實證的 code 用對照表的一次修完動作,而非逐筆重複的「確認來源」。"""
    causes = derive_root_causes([_issue("a"), _issue("b")])

    assert "一次" in causes[0].fix_once or "統一" in causes[0].fix_once
    assert causes[0].fix_once != "確認來源以取得 supported 引用"


def test_uncatalogued_code_falls_back_to_shared_suggested_fix():
    issues = [_issue("a", code=IssueCode.OUTPUT_MISMATCH, fix="修正參照後重新產生"),
              _issue("b", code=IssueCode.OUTPUT_MISMATCH, fix="修正參照後重新產生")]

    causes = derive_root_causes(issues)

    assert causes[0].fix_once == "修正參照後重新產生"


def test_root_causes_do_not_change_report_ok():
    """不變式:root_causes 是純加法,絕不影響 severity 閘。"""
    warnings = [_issue("a", severity=Severity.WARNING),
                _issue("b", severity=Severity.WARNING)]
    report = ValidationReport(issues=warnings,
                              root_causes=derive_root_causes(warnings))

    assert report.root_causes  # 有分組
    assert report.ok is True   # 但仍然 PASS


def test_report_defaults_to_no_root_causes():
    assert ValidationReport(issues=[]).root_causes == []
```

- [ ] **Step 2: 跑測試確認失敗(RED)**

Run: `uv run pytest tests/validate/test_root_cause.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'loop_apidoc.validate.root_cause'`

- [ ] **Step 3: 實作 model**

`loop_apidoc/validate/models.py`:在 `Issue` 之後、`ValidationReport` 之前插入 `RootCause`,並在 `ValidationReport` 加欄位。

```python
class RootCause(BaseModel):
    """多筆同源 issue 收斂成的一次修完動作。

    純加法:`issues[]` 一字不動,`ok` / exit code / score 全不受影響。
    correction loop 應優先消費 root_causes,再處理未被分組的 issues。
    """

    code: IssueCode
    severity: Severity
    target_file: str
    fix_once: str
    affected_locations: list[str]


class ValidationReport(BaseModel):
    issues: list[Issue] = Field(default_factory=list)
    # 見 validate/root_cause.py;不參與 `ok` 的計算。
    root_causes: list[RootCause] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity is Severity.ERROR for i in self.issues)

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]
```

- [ ] **Step 4: 實作 `derive_root_causes`**

新建 `loop_apidoc/validate/root_cause.py`:

```python
"""把多筆同源 issue 收斂成一次修完的根因(issue #4)。

一個根因(例如 integration.json 的 source 格式不合)會在 issues[] 裡展開成數十筆
各自獨立的 entry,evidence 全是同一句話。orchestrator 依 location 逐一重讀 scope
的話,會把 O(1) 的修法變成 O(n) 的 requery。

純加法:issues[] 一字不動,ValidationReport.ok 不受影響。純函式,不做檔案 I/O。
"""

from __future__ import annotations

from loop_apidoc.validate.models import Issue, IssueCode, RootCause

# 只填有實證的 code。查不到就沿用組內共同的 suggested_fix —— 憑空編一句
# 「一次修完」的動作,反而會把 correction loop 導向錯的地方。
_FIX_ONCE: dict[IssueCode, str] = {
    IssueCode.SOURCE_UNVERIFIED: (
        "統一改寫該檔所有 source 為 '<relative_path> p.<N>' 或 "
        "'<relative_path>#<anchor>' 格式,一次修完;不需逐筆重讀來源"
    ),
}


def derive_root_causes(issues: list[Issue]) -> list[RootCause]:
    """依 (code, severity, target_file) 分組。

    只在 `target_file` 非 None 且組內 ≥2 筆時產出根因:
    - `target_file` 為 None → 沒有可靠的一次修完目標,硬分組只會製造假的根因。
    - 單筆 → 逐筆 issue 已經夠精確,不需要收斂。
    - `severity` 進分組鍵 → 混合嚴重度的組無法給出單一 fix_once。

    分組順序依首次出現順序,組內 location 依原始順序 —— 決定性輸出。
    """
    groups: dict[tuple[IssueCode, str, str], list[Issue]] = {}
    for issue in issues:
        if issue.target_file is None:
            continue
        key = (issue.code, issue.severity.value, issue.target_file)
        groups.setdefault(key, []).append(issue)

    return [
        RootCause(
            code=code,
            severity=members[0].severity,
            target_file=target_file,
            fix_once=_FIX_ONCE.get(code, members[0].suggested_fix),
            affected_locations=[m.location for m in members],
        )
        for (code, _severity, target_file), members in groups.items()
        if len(members) > 1
    ]
```

- [ ] **Step 5: 跑測試確認通過(GREEN)**

Run: `uv run pytest tests/validate/test_root_cause.py -v`
Expected: PASS,全部 9 個。

- [ ] **Step 6: 接進 validator**

`loop_apidoc/validate/validator.py`:import `derive_root_causes`,並把最後一行改為:

```python
    return ValidationReport(issues=issues, root_causes=derive_root_causes(issues))
```

import 區塊加入(依字母序,放在 `models` 之後):

```python
from loop_apidoc.validate.root_cause import derive_root_causes
```

- [ ] **Step 7: report.md 渲染根因**

`loop_apidoc/validate/report.py`:在 `_bullet` 之後新增 `_root_cause_bullet`,並改寫 `render_markdown`。

```python
def _root_cause_bullet(cause) -> str:
    return (
        f"- **{cause.code.value}** ({cause.severity.value}) @ `{cause.target_file}`"
        f" — 影響 {len(cause.affected_locations)} 處\n"
        f"  - 一次修完：{cause.fix_once}\n"
        f"  - 影響位置：{'、'.join(f'`{loc}`' for loc in cause.affected_locations)}"
    )


def render_markdown(report: ValidationReport) -> str:
    errors = report.errors()
    warnings = report.warnings()
    status = "PASS" if report.ok else "FAIL"
    lines = [
        "# 驗證報告",
        "",
        f"結果：**{status}**（error：{len(errors)}，warning：{len(warnings)}）",
        "",
    ]
    if report.root_causes:
        lines += ["## 根因（優先處理）", ""]
        lines += [_root_cause_bullet(c) for c in report.root_causes]
        lines += ["", "## 逐筆問題", ""]
    ordered = errors + warnings
    if not ordered:
        lines.append("_未發現問題。_")
    else:
        lines.extend(_bullet(issue) for issue in ordered)
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 8: 加 report 渲染測試**

附加到 `tests/validate/test_report.py` 末尾:

```python
from loop_apidoc.validate.models import RootCause


def test_render_markdown_lists_root_causes_before_issues():
    report = ValidationReport(
        issues=[
            Issue(code=IssueCode.SOURCE_UNVERIFIED, severity=Severity.ERROR,
                  location="integration.crypto.0", evidence="缺 supported 依據",
                  suggested_fix="確認來源", target_file="integration.json"),
            Issue(code=IssueCode.SOURCE_UNVERIFIED, severity=Severity.ERROR,
                  location="integration.crypto.1", evidence="缺 supported 依據",
                  suggested_fix="確認來源", target_file="integration.json"),
        ],
        root_causes=[
            RootCause(code=IssueCode.SOURCE_UNVERIFIED, severity=Severity.ERROR,
                      target_file="integration.json", fix_once="統一改寫 source 格式",
                      affected_locations=["integration.crypto.0",
                                          "integration.crypto.1"]),
        ],
    )

    md = render_markdown(report)

    assert md.index("## 根因（優先處理）") < md.index("## 逐筆問題")
    assert "統一改寫 source 格式" in md
    assert "影響 2 處" in md


def test_render_markdown_omits_root_cause_section_when_empty():
    report = ValidationReport(issues=[])

    assert "## 根因" not in render_markdown(report)
```

若 `tests/validate/test_report.py` 頂端尚未 import `Issue` / `IssueCode` / `Severity` / `ValidationReport` / `render_markdown`,補齊。

- [ ] **Step 9: 跑全套測試(GREEN)**

Run: `uv run pytest tests/validate/ -v && uv run pytest`
Expected: PASS,全部。特別確認 `tests/test_quality_gate.py` 與 `tests/score/` 未受影響——`root_causes` 不得改變 `ok`。

- [ ] **Step 10: Commit**

```bash
git add loop_apidoc/validate/ tests/validate/
git commit -m "feat: [validate] root_causes 根因收斂,純加法不影響 severity 閘 (#4)"
```

---

### Task 5: `endpoints[].server` 多主機支援(#8)

**Files:**
- Modify: `loop_apidoc/plan/models.py:40-51`(`EndpointEntry`)
- Modify: `loop_apidoc/agentcli/cross_file.py`(新增 `_server_violations`,接進 `cross_file_violations`)
- Modify: `loop_apidoc/generate/openapi.py:440-443`(`_build_operation` 簽章)、`526-558`(`_build_paths`)
- Test: `tests/agentcli/test_cross_file.py`(附加)
- Test: `tests/generate/`(附加至既有的 openapi 測試檔;若無則新建 `tests/generate/test_openapi_servers.py`)

**Interfaces:**
- Consumes: Task 1 的 `cross_file_violations`
- Produces:
  - `EndpointEntry.server: str | None`
  - `_server_violations(inventory: dict) -> list[str]`(cross_file 內部,第六條不變式)
  - `_build_operation(endpoints, name_to_key=None, scheme_keys=None, environments=None)` —— 新增第四個**具名可選**參數 `environments: list | None`,型別為 `list[EnvironmentEntry]`

**關鍵設計約束(實作者必讀):**

`server` 住在 `inventory.endpoints[]`,**不在**端點檔裡。因此第六條不變式的迭代對象是 inventory,不是端點檔——**不要**塞進逐檔迭代的 `_reference_violations`,獨立成 `_server_violations(inventory)`。

- [ ] **Step 1: 寫 cross_file 失敗測試(RED)**

附加到 `tests/agentcli/test_cross_file.py` 末尾:

```python
# ── 不變式 6:endpoints[].server 必須指向 inventory.environments[].name ──

def _inv_env(*endpoints: dict, environments=()) -> dict:
    return {
        "endpoints": list(endpoints),
        "environments": [{"name": n, "base_url": f"https://{n}"} for n in environments],
        "schemas": [],
        "security_schemes": [],
    }


def test_unknown_server_name_is_a_violation():
    inventory = _inv_env(_ep("GET", "/ping", server="reporting"),
                         environments=("production",))
    endpoints = [("ep0.json", _ep("GET", "/ping"))]

    violations = cross_file_violations(inventory, endpoints)

    assert any("endpoints[0].server" in v and "reporting" in v for v in violations)


def test_known_server_name_passes():
    inventory = _inv_env(_ep("GET", "/ping", server="production"),
                         environments=("production",))
    endpoints = [("ep0.json", _ep("GET", "/ping"))]

    assert cross_file_violations(inventory, endpoints) == []


def test_absent_server_is_allowed():
    inventory = _inv_env(_ep("GET", "/ping"), environments=("production",))
    endpoints = [("ep0.json", _ep("GET", "/ping"))]

    assert cross_file_violations(inventory, endpoints) == []
```

- [ ] **Step 2: 跑測試確認失敗(RED)**

Run: `uv run pytest tests/agentcli/test_cross_file.py -k server -v`
Expected: FAIL —— `test_unknown_server_name_is_a_violation` 回傳 `[]`。

- [ ] **Step 3: 實作第六條不變式**

`loop_apidoc/agentcli/cross_file.py`:新增

```python
def _server_violations(inventory: dict) -> list[str]:
    """不變式 6:`endpoints[].server` 若存在,必須指向某個 environments[].name。

    迭代對象是 inventory 而非端點檔 —— `server` 住在 inventory 側,
    是「這支端點在哪個主機」的事實,由 generator 翻成 operation-level servers。
    """
    env_names = _names(inventory, "environments")
    out: list[str] = []
    for idx, entry in enumerate(_entries(inventory, "endpoints")):
        server = entry.get("server")
        if isinstance(server, str) and server not in env_names:
            out.append(
                f"inventory.json: endpoints[{idx}].server 未指向任何 "
                f"environments[].name:{server!r}"
            )
    return out
```

`cross_file_violations` 改為:

```python
def cross_file_violations(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> list[str]:
    """一次列出所有跨檔違規——修正是一次重寫擷取 JSON,不是逐筆往返。"""
    return (
        _count_violations(inventory, endpoints)
        + _multiset_violations(inventory, endpoints)
        + _duplicate_violations(endpoints)
        + _reference_violations(inventory, endpoints)
        + _server_violations(inventory)
    )
```

- [ ] **Step 4: 跑測試確認通過(GREEN)**

Run: `uv run pytest tests/agentcli/test_cross_file.py -v`
Expected: PASS,全部。

- [ ] **Step 5: 寫 OpenAPI 產出的失敗測試(RED)**

新建 `tests/generate/test_openapi_servers.py`:

```python
from __future__ import annotations

from loop_apidoc.generate.openapi import build_openapi
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    NormalizationPlan,
    PlanItemStatus,
)


def _plan(server: str | None) -> NormalizationPlan:
    # notebook_url 是 NormalizationPlan 唯一的必填欄位(無預設值)。
    plan = NormalizationPlan(notebook_url="")
    plan.environments = [
        EnvironmentEntry(name="production", base_url="https://api.example.com",
                         status=PlanItemStatus.SUPPORTED),
        EnvironmentEntry(name="reporting", base_url="https://report.example.com",
                         status=PlanItemStatus.SUPPORTED),
    ]
    plan.endpoints = [
        EndpointEntry(method="GET", path="/bets", summary="查詢投注",
                      server=server, status=PlanItemStatus.SUPPORTED),
    ]
    return plan


def test_endpoint_server_becomes_operation_level_servers():
    doc = build_openapi(_plan("reporting"))

    op = doc["paths"]["/bets"]["get"]
    assert op["servers"] == [
        {"url": "https://report.example.com", "description": "reporting"}
    ]


def test_absent_server_leaves_operation_without_servers():
    """欄位缺席時,產物與現況逐字相同 —— 沿用 root-level servers。"""
    doc = build_openapi(_plan(None))

    assert "servers" not in doc["paths"]["/bets"]["get"]
    assert doc["servers"][0]["url"] == "https://api.example.com"


def test_unknown_server_name_produces_no_operation_servers():
    """cross_file 已在輸入邊界擋下;generator 不臆測,靜默略過而非產出壞 URL。"""
    doc = build_openapi(_plan("nonexistent"))

    assert "servers" not in doc["paths"]["/bets"]["get"]
```

(已實證:`loop_apidoc/generate/openapi.py:629` 的簽章就是 `def build_openapi(plan: NormalizationPlan) -> dict`,只吃 `plan` 一個參數。)

- [ ] **Step 6: 跑測試確認失敗(RED)**

Run: `uv run pytest tests/generate/test_openapi_servers.py -v`
Expected: FAIL —— `EndpointEntry` 沒有 `server` 欄位(pydantic `ValidationError`)。

- [ ] **Step 7: 實作**

`loop_apidoc/plan/models.py`:`EndpointEntry` 加欄位(緊接 `summary` 之後):

```python
class EndpointEntry(_Cited):
    method: str | None = None
    path: str | None = None
    summary: str | None = None
    # 來源明載此端點屬於哪個 environments[].name(多主機文件);
    # generator 翻成 operation-level servers。缺席時沿用 root-level servers。
    server: str | None = None
    parameters: list[dict] = Field(default_factory=list)
    request: dict | None = None
    responses: list[dict] = Field(default_factory=list)
    examples: list[dict] = Field(default_factory=list)
    # Source-stated grouping labels and the names of security_schemes this
    # endpoint requires; both feed the OpenAPI operation (tags / security).
    tags: list[str] = Field(default_factory=list)
    security: list[str] = Field(default_factory=list)
```

`loop_apidoc/generate/openapi.py`:`_build_operation` 加第四個具名可選參數,並在函式體末尾(`return op` 之前)加入 operation-level servers。

```python
def _build_operation(
    endpoints: list,
    name_to_key: dict[str, str] | None = None,
    scheme_keys: dict[str, str] | None = None,
    environments: list | None = None,
) -> dict:
```

在 `return op` 之前插入:

```python
    # 來源明載的 per-endpoint 主機:翻成 operation-level servers,覆寫 root servers。
    # 未解析到 environment 時靜默略過 —— cross_file 已在輸入邊界擋下不存在的名字,
    # 這裡不臆測、不產出壞 URL。
    server_name = next(
        (e.server for e in endpoints if getattr(e, "server", None)), None
    )
    if server_name:
        env = next(
            (e for e in (environments or [])
             if e.name == server_name and e.base_url), None
        )
        if env is not None:
            entry: dict = {"url": env.base_url}
            if env.name:
                entry["description"] = env.name
            op["servers"] = [entry]
```

`_build_paths`:把 `plan.environments` 傳下去。`_build_operation` 有兩個呼叫點(已實證):

- `openapi.py:543`(在 `_build_paths` 內):`op = _build_operation(endpoints, name_to_key, scheme_keys)` → 改為 `op = _build_operation(endpoints, name_to_key, scheme_keys, environments=plan.environments)`
- `openapi.py:570`(在 `_build_webhooks` 內):**不改**。webhook 由呼叫方投遞到自訂 URL,沒有 server 的概念;不傳 `environments`,`server_name` 查不到就靜默略過。

- [ ] **Step 8: 跑測試確認通過(GREEN)**

Run: `uv run pytest tests/generate/ tests/agentcli/ -v`
Expected: PASS,全部。

- [ ] **Step 9: 確認 OpenAPI 3.1 schema 仍然有效**

Run: `uv run pytest -k "structure or openapi" -v`
Expected: PASS。operation-level `servers` 是 OpenAPI 3.1 的合法欄位,`openapi-spec-validator` 應接受。

- [ ] **Step 10: 全套測試 + lint**

Run: `uv run pytest && uv run ruff check .`
Expected: PASS,全部。

- [ ] **Step 11: Commit**

```bash
git add loop_apidoc/plan/models.py loop_apidoc/agentcli/cross_file.py loop_apidoc/generate/openapi.py tests/
git commit -m "feat: [agentcli] endpoints[].server 支援多主機,產出 operation-level servers (#8)"
```

---

### Task 6: 文件對齊

**Files:**
- Modify: `skills/loop-apidoc/reference/extraction-schemas.md`
- Modify: `skills/loop-apidoc/reference/assemble-and-correction.md`
- Modify: `CLAUDE.md`(`loop_apidoc/agentcli/` 那一列)

**Interfaces:**
- Consumes: Task 1–5 的全部行為
- Produces: 無程式碼介面。這是契約的對外面貌——subagent 只讀得到這些文件,讀不到程式碼。

**注意:** `skills/` 底下的檔案寫**英文**(token economy),`CLAUDE.md` 寫繁體中文。

- [ ] **Step 1: `extraction-schemas.md` 補上 null-path summary 規則**

在 inventory `endpoints[].path` 那段(約 50 行)之後插入:

```markdown
- A webhook/callback endpoint has `method` but `path: null` (it is delivered to a
  caller-defined URL, so it has no server path). For these, **`summary` is required**
  and is the endpoint's identity: it is how `assemble` matches an `endpoints/ep<N>.json`
  file to its `inventory.endpoints[]` entry, and how the OpenAPI `webhooks` key is named.
  Two webhooks with no `summary` are indistinguishable, and a subagent writing one
  webhook into two files would go undetected. Copy the `summary` **verbatim** from
  inventory into the endpoint file (whitespace is normalized before comparison).

  ```
  ✓ inventory: {"method":"POST","path":null,"summary":"NotifyURL 幕後付款結果通知"}
    ep7.json:  {"method":"POST","path":null,"summary":"NotifyURL 幕後付款結果通知"}
  ✗ ep7.json:  {"method":"POST","path":null}          ← rejected at the input boundary
  ```
```

在同一節再插入 `server` 欄位說明:

```markdown
- `endpoints[].server` (optional): when the source documents **more than one** base URL
  and states which endpoints live on which host, set `server` to the matching
  `environments[].name`. `assemble` rejects a name that resolves to no environment.
  The generator turns it into an operation-level OpenAPI `servers` entry. Omit the field
  when the source states a single host — the endpoint then inherits the root `servers`.

  ```
  environments: [{"name":"api","base_url":"https://api.example.com"},
                 {"name":"reporting","base_url":"https://report.example.com"}]
  endpoints:    [{"method":"GET","path":"/bets","server":"reporting", ...}]
  ```
```

- [ ] **Step 2: `assemble-and-correction.md` 補上 root_causes**

在描述 `--json` 輸出與 issue 欄位的段落之後插入:

```markdown
### `root_causes` — fix once, not N times

`validation/report.json` carries an additive `root_causes[]` alongside `issues[]`.
Each entry groups issues sharing `(code, severity, target_file)` when there are two
or more of them:

```json
{"code": "SOURCE_UNVERIFIED", "severity": "error",
 "target_file": "integration.json",
 "fix_once": "統一改寫該檔所有 source 為 '<relative_path> p.<N>' …",
 "affected_locations": ["integration.crypto.0", "integration.crypto.1", "…"]}
```

**Consume `root_causes` first.** One rewrite of `target_file` clears every location in
`affected_locations` — do not spawn one requery subagent per location. Then handle the
`issues[]` entries that no root cause covers (those with `target_file: null`, and
single-occurrence issues).

`root_causes` never affects pass/fail: the gate remains "any `error`-severity issue in
`issues[]`". A report can have root causes and still PASS if they are all warnings.
```

- [ ] **Step 3: `CLAUDE.md` 更新 agentcli 那一列**

把 `loop_apidoc/agentcli/` 該列中的 `cross_file.py` 描述:

> `cross_file.py` (pure cross-file invariants: endpoint files ↔ inventory — count, `(method, path)` multiset, no duplicates, `schema_ref`/`security[]` resolution)

改為:

> `cross_file.py` (pure cross-file invariants: endpoint files ↔ inventory — count, identity multiset (`(method, path)`, or `(method, summary)` for null-path webhooks), no duplicates, `schema_ref`/`security[]` resolution, `endpoints[].server` → `environments[].name` resolution)

並把同列 `source_guard.py` 的「the two schema contracts」改為「the three schema contracts」,補上「null-path endpoints must carry a `summary`」。

- [ ] **Step 4: 驗證文件測試**

Run: `uv run pytest tests/docs/ tests/test_plugin_manifest.py -v`
Expected: PASS(若 `tests/docs/` 有檢查 skill 文件結構的測試)。

- [ ] **Step 5: 全套測試 + lint**

Run: `uv run pytest && uv run ruff check .`
Expected: PASS,全部。

- [ ] **Step 6: Commit**

```bash
git add skills/loop-apidoc/reference/ CLAUDE.md
git commit -m "docs: [skill] null-path summary 身份鍵、endpoints[].server、root_causes 消費順序 (#7 #4 #8)"
```

---

## 收尾

三個 issue 全部有測試覆蓋後,關閉:

```bash
gh issue close 7 -c "已修正:null-path 端點以 summary 為跨檔身份鍵,source_guard 強制必填。benchmarks/newebpay-mpg 的三個 webhook 為迴歸證據。"
gh issue close 4 -c "已修正:ValidationReport 新增 root_causes(純加法,不影響 ok / exit code / score)。"
gh issue close 8 -c "已修正:endpoints[].server 指向 environments[].name,產出 operation-level OpenAPI servers。"
```
