# Loop API 文件 Pipeline — Plan 3：擷取與規格化計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立「擷取層」與「規格化計畫層」：以 Plan 2 的 `NotebookLMAdapter` 對 NotebookLM 執行分段、彼此獨立且自帶完整上下文的多輪查詢，保存每輪原始 artifact（`extraction/queries.jsonl` 與 `extraction/answers/`），再將結構化回答組裝成機器可讀、帶來源追溯的 `plan/normalization-plan.json`。

**Architecture:** 兩個解耦套件。`loop_apidoc/extraction/`：`stages` 定義 spec §7.1 的十個查詢階段與每階段的問題種類（initial／conditional follow-up／reverse-check，§7.2）；`questions` 建構自帶上下文的提示（notebook 身分、已知摘要、待確認項目、預期格式，§4.2）；`orchestrator` 透過 adapter＋`run_with_retries` 逐階段查詢並由 `store` 把每輪保存成 jsonl＋答案檔（§7.1「不直接覆蓋或丟棄」）。`loop_apidoc/plan/`：`models` 定義 §7.3 計畫 schema；`parsing` 抽取結構化階段的 ```json 區塊；`builder` 把最新結構區塊組裝成 `NormalizationPlan`，每項帶 `SourceCitation` 並依與 manifest 名稱比對結果指派 `supported`／`unverified`／`missing` 狀態（§6、§8.3）。**混合答案契約**：inventory 階段（env／security／endpoints／details／schemas／errors／operational）要求 NotebookLM 回傳符合 mini-schema 的 ```json 區塊；敘事階段（來源盤點／概覽／衝突）保留純文字 artifact。

**Tech Stack:** Python ≥3.11、Pydantic v2（資料模型）、標準庫 `json` / `re` / `pathlib`、pytest。沿用 Plan 1/2 的 `loop_apidoc/` 套件、注入式副作用與 TDD 流程。**本計畫不新增第三方依賴，亦不消耗真實 NotebookLM 額度（單元／整合測試一律以 fake adapter＋fixture 回答驅動，spec §12.2）。**

這是六份計畫中的第 3 份。Plan 1（基礎建設＋manifest）、Plan 2（NotebookLM adapter＋doctor）已完成並併入 master。本計畫消費 Plan 2 的 `NotebookLMAdapter.ask(question, notebook_url) -> AskResult`、`run_with_retries(operation, *, max_attempts)`、型別化例外，與 Plan 1 的 `Manifest`／`LocalSource`／`UrlSource`。Plan 4（產生 OpenAPI／Markdown／provenance）會消費本計畫的 `NormalizationPlan`；本計畫**不**寫 CLI 命令（`run` 由 Plan 6 串接），擷取與計畫產出由 `run_extraction()` 與 `build_normalization_plan()` 這兩個整合 seam 對外提供。

## Global Constraints

下列為整份 spec 的專案級要求，每個 task 都隱含遵守（值逐字取自 spec）：

- **以來源文件為唯一事實依據；來源未提供的資訊不得推測**（spec §1）。結構化提示一律指示：來源未提供的欄位填 `null` 並列入 `missing`，**不得依 REST／OAuth／產業慣例自行補值**（spec §7.2、§9.4）。
- **核心流程不得直接耦合瀏覽器自動化細節**，一律透過 Plan 2 的 adapter（spec §4.1）。
- **每個 follow-up 問題必須自帶完整上下文**（notebook 身分、目前已知摘要、待確認項目、預期輸出格式），不可依賴「上一個回答」（spec §4.2）。
- **每輪回答保存為原始擷取 artifact，不直接覆蓋或丟棄**（spec §7.1）。
- **NotebookLM 明確表示來源沒有資訊時保存為缺漏，不得繼續用引導式問題誘導推測**（spec §7.2）→ follow-up 至多一輪、措辭接受「來源未提供」為合法答案。
- **只存在於計畫且具來源依據的內容才可進入後續輸出**（spec §7.3）；NotebookLM 回答是來源整理層、非獨立事實，最終狀態仍須連回 manifest（spec §8.3）。
- **無法確認的來源標記 `unverified`**；回答與 manifest 做名稱及內容主題比對（spec §6）。
- **查詢額度或暫時錯誤 → 有限次技術重試**，與三輪內容修正分開計數（spec §11）→ 一律經 `run_with_retries`。
- **機密資料**：artifact 與 log 不應保存 Google cookie、browser state 或憑證；只保存被呼叫 script 的答案文字（spec §11）。
- Python ≥3.11；資料模型用 Pydantic v2；不新增第三方依賴（沿用 Plan 1/2）。

---

## 參考：產物佈局與識別碼（供本計畫所有 task 對齊）

run directory 中本計畫負責的兩個子樹（spec §8）：

```text
output/<run-id>/
├── extraction/
│   ├── queries.jsonl        # 每行一筆 QueryRecord（依詢問順序）
│   └── answers/
│       └── <query_id>.txt   # 每次查詢的原始答案文字
└── plan/
    └── normalization-plan.json
```

- **stage_id**：兩位數零填，`"01"`..`"10"`，對應 spec §7.1 的十個階段順序。
- **query_id**：`f"{stage_id}-{kind}"`，例如 `"05-initial"`、`"05-followup"`、`"05-reverse"`。每階段每種 kind 至多一筆，故 query_id 唯一且**確定性**（不需隨機或時間，符合本環境對 `Date.now()`/`random` 的限制）。
- **answer_path**：相對於 `extraction/` 的 `"answers/<query_id>.txt"`。
- **manifest source id**：沿用 Plan 1，本機來源用 `LocalSource.relative_path`，URL 來源用 `UrlSource.url`。

十個階段與模式（`STRUCTURED` 走 ```json 區塊；`NARRATIVE` 保留純文字）：

| stage_id | 主題（spec §7.1） | mode | 結構區塊頂層鍵 |
|---|---|---|---|
| 01 | Notebook 與來源盤點 | NARRATIVE | — |
| 02 | API 系統概覽與術語 | NARRATIVE | — |
| 03 | 環境、base URL 與版本 | STRUCTURED | `environments` |
| 04 | 驗證、授權與簽章 | STRUCTURED | `security_schemes` |
| 05 | Endpoint 清單 | STRUCTURED | `endpoints` |
| 06 | 逐 endpoint 細節 | STRUCTURED | `endpoint_details` |
| 07 | 共用 schema、enum、資料限制 | STRUCTURED | `schemas` |
| 08 | 錯誤碼與失敗行為 | STRUCTURED | `errors` |
| 09 | rate limit／timeout／retry／idempotency／webhook | STRUCTURED | `operational` |
| 10 | 來源衝突、缺漏、無法確認 | NARRATIVE | — |

**已知範圍邊界（本計畫刻意排除，列入 carry-forward）：**
- stage 06 以**單一**合併查詢取得所有 endpoint 細節，而非依 stage 05 結果逐 endpoint fan-out。逐 endpoint 動態展開能提高完整性，但需要由 stage 05 結果動態生成查詢、顯著增加 orchestrator 複雜度；本計畫保持確定性與可測性，缺漏的細節經 `missing` 機制記錄、由 Plan 5 驗證攔截。
- 自動跨來源衝突偵測不在本計畫；stage 10 以純文字保存衝突敘述（`conflicts_note`），`source_conflicts` 結構列表僅在結構區塊明確提供 `conflicts` 陣列時填入。真正的一致性衝突由 Plan 5 §9.3 驗證surfacing。

---

### Task 1：擷取階段定義（stages）

定義查詢種類、階段模式與 spec §7.1 的十個階段（含每個結構化階段要嵌入提示的 mini-schema 提示文字）。

**Files:**
- Create: `loop_apidoc/extraction/__init__.py`
- Create: `loop_apidoc/extraction/stages.py`
- Create: `tests/extraction/__init__.py`
- Create: `tests/extraction/test_stages.py`

**Interfaces:**
- Consumes: 無。
- Produces：
  - `QueryKind(str, Enum)`：`INITIAL = "initial"`、`FOLLOWUP = "followup"`、`REVERSE = "reverse"`。
  - `StageMode(str, Enum)`：`STRUCTURED = "structured"`、`NARRATIVE = "narrative"`。
  - `QueryStage(BaseModel)`：`stage_id: str`、`title: str`、`mode: StageMode`、`goal: str`、`json_key: str | None = None`、`json_hint: str | None = None`。
  - `STAGES: tuple[QueryStage, ...]`：十個階段，依 stage_id `"01"`..`"10"` 排序，模式與頂層鍵如上表；每個 `STRUCTURED` 階段 `json_key` 非空且 `json_hint` 含該階段的 mini-schema 描述與「未提供填 null 並列入 missing、不得推測」字句。
  - `stage_by_id(stage_id: str) -> QueryStage`：查無則 `raise KeyError`。

- [ ] **Step 1：建立 `tests/extraction/__init__.py`（空檔）**

```python
```

- [ ] **Step 2：寫失敗測試 `tests/extraction/test_stages.py`**

```python
from __future__ import annotations

from loop_apidoc.extraction.stages import (
    STAGES,
    QueryKind,
    QueryStage,
    StageMode,
    stage_by_id,
)


def test_ten_stages_in_order():
    assert len(STAGES) == 10
    assert [s.stage_id for s in STAGES] == [f"{i:02d}" for i in range(1, 11)]


def test_structured_stages_have_json_contract():
    structured = {"03", "04", "05", "06", "07", "08", "09"}
    for stage in STAGES:
        if stage.stage_id in structured:
            assert stage.mode is StageMode.STRUCTURED
            assert stage.json_key
            assert stage.json_hint and "missing" in stage.json_hint
        else:
            assert stage.mode is StageMode.NARRATIVE
            assert stage.json_key is None


def test_endpoint_stage_key():
    assert stage_by_id("05").json_key == "endpoints"
    assert stage_by_id("05").mode is StageMode.STRUCTURED


def test_query_kinds():
    assert QueryKind.INITIAL.value == "initial"
    assert QueryKind.FOLLOWUP.value == "followup"
    assert QueryKind.REVERSE.value == "reverse"


def test_stage_by_id_unknown_raises():
    import pytest

    with pytest.raises(KeyError):
        stage_by_id("99")


def test_stage_is_a_model():
    assert isinstance(STAGES[0], QueryStage)
```

- [ ] **Step 3：執行測試確認失敗**

Run: `uv run pytest tests/extraction/test_stages.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.extraction'`）。

- [ ] **Step 4：建立 `loop_apidoc/extraction/__init__.py`**

```python
"""NotebookLM extraction and normalization-plan layers (spec §7)."""
```

- [ ] **Step 5：實作 `loop_apidoc/extraction/stages.py`**

```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

_NO_SPECULATION = (
    "For any field the sources do not provide, use null and add a short label "
    "for it to the `missing` array. Do not infer or fill values from REST, OAuth, "
    "or industry conventions. Only report what the sources state."
)


class QueryKind(str, Enum):
    INITIAL = "initial"
    FOLLOWUP = "followup"
    REVERSE = "reverse"


class StageMode(str, Enum):
    STRUCTURED = "structured"
    NARRATIVE = "narrative"


class QueryStage(BaseModel):
    stage_id: str
    title: str
    mode: StageMode
    goal: str
    json_key: str | None = None
    json_hint: str | None = None


def _structured(stage_id: str, title: str, goal: str, key: str, schema: str) -> QueryStage:
    hint = (
        f'Return ONLY one fenced ```json block of the form: {schema} '
        f"The top-level array key MUST be `{key}`, plus a `missing` array of strings. "
        f"{_NO_SPECULATION}"
    )
    return QueryStage(
        stage_id=stage_id, title=title, mode=StageMode.STRUCTURED, goal=goal,
        json_key=key, json_hint=hint,
    )


def _narrative(stage_id: str, title: str, goal: str) -> QueryStage:
    return QueryStage(stage_id=stage_id, title=title, mode=StageMode.NARRATIVE, goal=goal)


STAGES: tuple[QueryStage, ...] = (
    _narrative(
        "01", "Notebook and source inventory",
        "Describe every source document and URL you can see in this notebook, "
        "including file names and the topics each covers. State explicitly if you "
        "cannot see a source.",
    ),
    _narrative(
        "02", "API system overview and terminology",
        "Summarize the overall purpose of the API and define its key terms, strictly "
        "from the sources. Note anything the sources do not cover.",
    ),
    _structured(
        "03", "Environments, base URLs and versions",
        "List every environment, base URL and API version stated by the sources.",
        "environments",
        '{"environments": [{"name": str|null, "base_url": str|null, "version": '
        'str|null, "source": str|null}], "missing": [str]}',
    ),
    _structured(
        "04", "Authentication, authorization and signing",
        "List every authentication, authorization and request-signing scheme stated "
        "by the sources.",
        "security_schemes",
        '{"security_schemes": [{"name": str|null, "type": str|null, "location": '
        'str|null, "details": str|null, "source": str|null}], "missing": [str]}',
    ),
    _structured(
        "05", "Endpoint inventory",
        "List every endpoint stated by the sources with its HTTP method, path and a "
        "short summary.",
        "endpoints",
        '{"endpoints": [{"method": str|null, "path": str|null, "summary": str|null, '
        '"source": str|null}], "missing": [str]}',
    ),
    _structured(
        "06", "Per-endpoint details",
        "For every endpoint, give parameters, request body, response statuses and "
        "schemas, and examples, strictly from the sources.",
        "endpoint_details",
        '{"endpoint_details": [{"method": str|null, "path": str|null, "parameters": '
        '[obj], "request": obj|null, "responses": [obj], "examples": [obj], "source": '
        'str|null}], "missing": [str]}',
    ),
    _structured(
        "07", "Shared schemas, enums and data constraints",
        "List shared schemas, their fields and types, enum value sets and data "
        "constraints stated by the sources.",
        "schemas",
        '{"schemas": [{"name": str|null, "fields": [obj], "enums": [obj], '
        '"constraints": str|null, "source": str|null}], "missing": [str]}',
    ),
    _structured(
        "08", "Error codes and failure behavior",
        "List every error code, its meaning and HTTP status stated by the sources.",
        "errors",
        '{"errors": [{"code": str|null, "meaning": str|null, "http_status": str|null, '
        '"source": str|null}], "missing": [str]}',
    ),
    _structured(
        "09", "Rate limits, timeouts, retry, idempotency and webhooks",
        "List rate limits, timeouts, retry rules, idempotency rules and webhook "
        "behavior stated by the sources.",
        "operational",
        '{"operational": [{"topic": str|null, "detail": str|null, "source": str|null}],'
        ' "missing": [str]}',
    ),
    _narrative(
        "10", "Source conflicts, gaps and unconfirmable items",
        "List anything the earlier answers may have missed, where the sources conflict, "
        "and any claim that has no source support. Do not resolve conflicts by guessing.",
    ),
)

_BY_ID = {stage.stage_id: stage for stage in STAGES}


def stage_by_id(stage_id: str) -> QueryStage:
    return _BY_ID[stage_id]
```

- [ ] **Step 6：執行測試確認通過**

Run: `uv run pytest tests/extraction/test_stages.py -v`
Expected: PASS（6 passed）。

- [ ] **Step 7：Commit**

```bash
git add loop_apidoc/extraction/__init__.py loop_apidoc/extraction/stages.py tests/extraction/__init__.py tests/extraction/test_stages.py
git commit -m "feat: add extraction query stage definitions"
```

---

### Task 2：```json 區塊抽取與缺口偵測（jsonblock）

提供從純文字答案抽取第一個 ```json 區塊的確定性 helper，及從結構區塊算出「仍缺欄位」的 helper（供 orchestrator 決定是否追問、供 builder 解析）。

**Files:**
- Create: `loop_apidoc/extraction/jsonblock.py`
- Create: `tests/extraction/test_jsonblock.py`

**Interfaces:**
- Consumes: 無。
- Produces：
  - `extract_json_block(text: str) -> dict | None`：回傳答案中第一個 fenced ```json 區塊 `json.loads` 後的 dict；無區塊、解析失敗或非 dict 時回 `None`。優先比對 ```` ```json ````；退而比對無語言標註的 ```` ``` ```` 區塊。
  - `find_gaps(block: dict) -> list[str]`：回傳「值為 `None` 的頂層鍵」加上「頂層 `missing` 陣列中的字串項」，去重並保序。

- [ ] **Step 1：寫失敗測試 `tests/extraction/test_jsonblock.py`**

```python
from __future__ import annotations

from loop_apidoc.extraction.jsonblock import extract_json_block, find_gaps


def test_extract_labeled_json_block():
    text = 'Here you go:\n```json\n{"endpoints": [], "missing": ["auth"]}\n```\nThanks.'
    block = extract_json_block(text)
    assert block == {"endpoints": [], "missing": ["auth"]}


def test_extract_unlabeled_block_fallback():
    text = "```\n{\"a\": 1}\n```"
    assert extract_json_block(text) == {"a": 1}


def test_extract_returns_none_when_absent():
    assert extract_json_block("The sources do not provide this.") is None


def test_extract_returns_none_on_invalid_json():
    assert extract_json_block("```json\n{not valid}\n```") is None


def test_extract_returns_none_when_block_is_not_object():
    assert extract_json_block("```json\n[1, 2, 3]\n```") is None


def test_find_gaps_collects_nulls_and_missing():
    block = {"base_url": None, "version": "v1", "missing": ["signing", "base_url"]}
    gaps = find_gaps(block)
    assert gaps == ["base_url", "signing"]


def test_find_gaps_empty_when_complete():
    assert find_gaps({"x": 1, "missing": []}) == []
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/extraction/test_jsonblock.py -v`
Expected: FAIL（`ModuleNotFoundError: ... jsonblock`）。

- [ ] **Step 3：實作 `loop_apidoc/extraction/jsonblock.py`**

```python
from __future__ import annotations

import json
import re

_LABELED = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)
_ANY = re.compile(r"```\s*\n(.*?)```", re.DOTALL)


def _try_load(candidate: str) -> dict | None:
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_json_block(text: str) -> dict | None:
    for pattern in (_LABELED, _ANY):
        match = pattern.search(text)
        if match:
            block = _try_load(match.group(1).strip())
            if block is not None:
                return block
    return None


def find_gaps(block: dict) -> list[str]:
    gaps: list[str] = []
    for key, value in block.items():
        if key == "missing":
            continue
        if value is None:
            gaps.append(key)
    missing = block.get("missing")
    if isinstance(missing, list):
        for item in missing:
            gaps.append(str(item))
    seen: set[str] = set()
    ordered: list[str] = []
    for gap in gaps:
        if gap not in seen:
            seen.add(gap)
            ordered.append(gap)
    return ordered
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/extraction/test_jsonblock.py -v`
Expected: PASS（7 passed）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/extraction/jsonblock.py tests/extraction/test_jsonblock.py
git commit -m "feat: add json-block extraction and gap detection"
```

---

### Task 3：自帶上下文的問題建構（questions）

把 spec §4.2 的「自帶完整上下文」要求落實成確定性的問題字串建構：每個問題嵌入 notebook 身分、累積已知摘要、本階段目標、（結構化階段）mini-schema 與（follow-up）待確認欄位。

**Files:**
- Create: `loop_apidoc/extraction/questions.py`
- Create: `tests/extraction/test_questions.py`

**Interfaces:**
- Consumes: Task 1 的 `QueryStage`、`QueryKind`、`StageMode`。
- Produces：
  - `build_known_summary(prior_answers: list[tuple[str, str]]) -> str`：輸入為 `(stage_title, answer_text)` 串列（僅含已完成階段的 initial 答案）；輸出每階段一行 `「- {title}: {answer 前 280 字、換行壓成空白}」`；空輸入回傳 `"(none yet)"`。
  - `build_question(stage: QueryStage, kind: QueryKind, *, notebook_url: str, known_summary: str, pending_fields: list[str] | None = None) -> str`：組裝自帶上下文的提示。必含 `notebook_url`、`known_summary`、`stage.goal`；`STRUCTURED` 階段含 `stage.json_hint`；`FOLLOWUP` 含 `pending_fields` 並要求「重新輸出完整 JSON 區塊、仍未提供者保留於 missing」；`REVERSE` 改問「前述回答可能遺漏／衝突／無來源支持之處」。

- [ ] **Step 1：寫失敗測試 `tests/extraction/test_questions.py`**

```python
from __future__ import annotations

from loop_apidoc.extraction.questions import build_known_summary, build_question
from loop_apidoc.extraction.stages import QueryKind, stage_by_id

NB = "https://notebooklm.google.com/notebook/abc"


def test_known_summary_formats_lines():
    summary = build_known_summary([("Overview", "It is a payments API.\nWith webhooks.")])
    assert "- Overview: It is a payments API. With webhooks." in summary


def test_known_summary_empty():
    assert build_known_summary([]) == "(none yet)"


def test_initial_structured_question_is_self_contained():
    stage = stage_by_id("05")
    q = build_question(stage, QueryKind.INITIAL, notebook_url=NB, known_summary="(none yet)")
    assert NB in q
    assert "(none yet)" in q
    assert stage.goal in q
    assert stage.json_hint in q


def test_followup_lists_pending_and_demands_full_block():
    stage = stage_by_id("03")
    q = build_question(
        stage, QueryKind.FOLLOWUP, notebook_url=NB, known_summary="x",
        pending_fields=["base_url", "version"],
    )
    assert "base_url" in q and "version" in q
    assert "full" in q.lower()
    assert "missing" in q


def test_reverse_question_asks_for_omissions():
    stage = stage_by_id("05")
    q = build_question(stage, QueryKind.REVERSE, notebook_url=NB, known_summary="x")
    assert "miss" in q.lower() or "conflict" in q.lower()
    assert NB in q


def test_narrative_initial_has_no_json_hint():
    stage = stage_by_id("02")
    q = build_question(stage, QueryKind.INITIAL, notebook_url=NB, known_summary="x")
    assert "```json" not in q
    assert stage.goal in q
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/extraction/test_questions.py -v`
Expected: FAIL（`ModuleNotFoundError: ... questions`）。

- [ ] **Step 3：實作 `loop_apidoc/extraction/questions.py`**

```python
from __future__ import annotations

from loop_apidoc.extraction.stages import QueryKind, QueryStage, StageMode

_HEADER = (
    "You are answering one independent question about a NotebookLM notebook. There is "
    "no conversation history, so this message carries all the context you need.\n"
    "Notebook: {notebook_url}\n"
    "Known so far (from earlier questions, for context only — re-verify against the "
    "sources):\n{known_summary}\n"
)


def build_known_summary(prior_answers: list[tuple[str, str]]) -> str:
    if not prior_answers:
        return "(none yet)"
    lines = []
    for title, answer in prior_answers:
        flat = " ".join(answer.split())[:280]
        lines.append(f"- {title}: {flat}")
    return "\n".join(lines)


def _context(stage: QueryStage, notebook_url: str, known_summary: str) -> str:
    return _HEADER.format(notebook_url=notebook_url, known_summary=known_summary)


def build_question(
    stage: QueryStage,
    kind: QueryKind,
    *,
    notebook_url: str,
    known_summary: str,
    pending_fields: list[str] | None = None,
) -> str:
    context = _context(stage, notebook_url, known_summary)

    if kind is QueryKind.REVERSE:
        body = (
            f"Topic: {stage.title}. Review the earlier answers on this topic and list "
            "anything they may have missed, anything where the sources conflict, and any "
            "claim that is not supported by the sources. If the sources are silent on "
            "something, say so plainly — do not guess."
        )
        return context + body

    if kind is QueryKind.FOLLOWUP:
        fields = ", ".join(pending_fields or [])
        body = (
            f"Topic: {stage.title}. The following items are still unfilled: {fields}. "
            "For each, state only what the sources provide. Then re-output the FULL JSON "
            "block for this topic; keep any item the sources still do not provide in the "
            f"`missing` array. {stage.json_hint}"
        )
        return context + body

    # INITIAL
    if stage.mode is StageMode.STRUCTURED:
        body = f"Task: {stage.goal}\n{stage.json_hint}"
    else:
        body = (
            f"Task: {stage.goal} Answer in prose, strictly from the sources, and state "
            "explicitly anything the sources do not cover."
        )
    return context + body
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/extraction/test_questions.py -v`
Expected: PASS（6 passed）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/extraction/questions.py tests/extraction/test_questions.py
git commit -m "feat: add context-rich extraction question builder"
```

---

### Task 4：擷取 artifact 模型與持久化（models＋store）

定義擷取 artifact 的資料模型，並把每輪查詢確定性地保存為 `extraction/queries.jsonl`（每行一筆）與 `extraction/answers/<query_id>.txt`（原始答案文字），不覆蓋既有檔案以外的內容。

**Files:**
- Create: `loop_apidoc/extraction/models.py`
- Create: `loop_apidoc/extraction/store.py`
- Create: `tests/extraction/test_store.py`

**Interfaces:**
- Consumes: Task 1 的 `QueryKind`。
- Produces：
  - `QueryRecord(BaseModel)`：`query_id: str`、`stage_id: str`、`kind: QueryKind`、`question: str`、`answer_path: str`、`returncode: int`。
  - `AnswerArtifact(BaseModel)`：`query_id: str`、`stage_id: str`、`kind: QueryKind`、`answer: str`、`answer_path: str`、`returncode: int`。
  - `ExtractionResult(BaseModel)`：`notebook_url: str`、`artifacts: list[AnswerArtifact]`；方法 `for_stage(stage_id: str) -> list[AnswerArtifact]`（保序）、`latest_structured(stage_id: str) -> AnswerArtifact | None`（同階段 `FOLLOWUP` 優先於 `INITIAL`；無則 `None`）、`initial(stage_id: str) -> AnswerArtifact | None`。
  - `ExtractionStore`：`__init__(self, extraction_dir: Path)`；`record(self, *, query_id, stage_id, kind: QueryKind, question: str, answer: str, returncode: int) -> AnswerArtifact`。首次寫入時建立 `extraction_dir/answers/`；把答案寫入 `answers/<query_id>.txt`，把 `QueryRecord` 以單行 JSON append 到 `queries.jsonl`，回傳對應 `AnswerArtifact`。

- [ ] **Step 1：寫失敗測試 `tests/extraction/test_store.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.extraction.store import ExtractionStore


def test_record_writes_answer_and_jsonl(tmp_path: Path):
    store = ExtractionStore(tmp_path)
    art = store.record(
        query_id="05-initial", stage_id="05", kind=QueryKind.INITIAL,
        question="List endpoints", answer="```json\n{}\n```", returncode=0,
    )
    assert isinstance(art, AnswerArtifact)
    assert art.answer_path == "answers/05-initial.txt"
    answer_file = tmp_path / "answers" / "05-initial.txt"
    assert answer_file.read_text(encoding="utf-8") == "```json\n{}\n```"

    lines = (tmp_path / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["query_id"] == "05-initial"
    assert rec["kind"] == "initial"
    assert rec["answer_path"] == "answers/05-initial.txt"


def test_record_appends_in_order(tmp_path: Path):
    store = ExtractionStore(tmp_path)
    store.record(query_id="05-initial", stage_id="05", kind=QueryKind.INITIAL,
                 question="q1", answer="a1", returncode=0)
    store.record(query_id="05-reverse", stage_id="05", kind=QueryKind.REVERSE,
                 question="q2", answer="a2", returncode=0)
    lines = (tmp_path / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["query_id"] for l in lines] == ["05-initial", "05-reverse"]


def test_extraction_result_selectors():
    arts = [
        AnswerArtifact(query_id="05-initial", stage_id="05", kind=QueryKind.INITIAL,
                       answer="i", answer_path="answers/05-initial.txt", returncode=0),
        AnswerArtifact(query_id="05-followup", stage_id="05", kind=QueryKind.FOLLOWUP,
                       answer="f", answer_path="answers/05-followup.txt", returncode=0),
        AnswerArtifact(query_id="02-initial", stage_id="02", kind=QueryKind.INITIAL,
                       answer="n", answer_path="answers/02-initial.txt", returncode=0),
    ]
    result = ExtractionResult(notebook_url="https://nb/x", artifacts=arts)
    assert [a.query_id for a in result.for_stage("05")] == ["05-initial", "05-followup"]
    assert result.latest_structured("05").kind is QueryKind.FOLLOWUP
    assert result.initial("02").answer == "n"
    assert result.latest_structured("99") is None
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/extraction/test_store.py -v`
Expected: FAIL（`ModuleNotFoundError: ... models`）。

- [ ] **Step 3：實作 `loop_apidoc/extraction/models.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from loop_apidoc.extraction.stages import QueryKind


class QueryRecord(BaseModel):
    query_id: str
    stage_id: str
    kind: QueryKind
    question: str
    answer_path: str
    returncode: int


class AnswerArtifact(BaseModel):
    query_id: str
    stage_id: str
    kind: QueryKind
    answer: str
    answer_path: str
    returncode: int


class ExtractionResult(BaseModel):
    notebook_url: str
    artifacts: list[AnswerArtifact] = Field(default_factory=list)

    def for_stage(self, stage_id: str) -> list[AnswerArtifact]:
        return [a for a in self.artifacts if a.stage_id == stage_id]

    def initial(self, stage_id: str) -> AnswerArtifact | None:
        for art in self.artifacts:
            if art.stage_id == stage_id and art.kind is QueryKind.INITIAL:
                return art
        return None

    def latest_structured(self, stage_id: str) -> AnswerArtifact | None:
        followup = None
        initial = None
        for art in self.artifacts:
            if art.stage_id != stage_id:
                continue
            if art.kind is QueryKind.FOLLOWUP:
                followup = art
            elif art.kind is QueryKind.INITIAL:
                initial = art
        return followup or initial
```

- [ ] **Step 4：實作 `loop_apidoc/extraction/store.py`**

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.extraction.models import AnswerArtifact, QueryRecord
from loop_apidoc.extraction.stages import QueryKind


class ExtractionStore:
    """Persists each query round to extraction/queries.jsonl and
    extraction/answers/<query_id>.txt without discarding prior rounds (spec §7.1)."""

    def __init__(self, extraction_dir: Path) -> None:
        self._dir = extraction_dir
        self._answers = extraction_dir / "answers"
        self._queries = extraction_dir / "queries.jsonl"

    def record(
        self,
        *,
        query_id: str,
        stage_id: str,
        kind: QueryKind,
        question: str,
        answer: str,
        returncode: int,
    ) -> AnswerArtifact:
        self._answers.mkdir(parents=True, exist_ok=True)
        answer_path = f"answers/{query_id}.txt"
        (self._answers / f"{query_id}.txt").write_text(answer, encoding="utf-8")
        record = QueryRecord(
            query_id=query_id, stage_id=stage_id, kind=kind, question=question,
            answer_path=answer_path, returncode=returncode,
        )
        with self._queries.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
        return AnswerArtifact(
            query_id=query_id, stage_id=stage_id, kind=kind, answer=answer,
            answer_path=answer_path, returncode=returncode,
        )
```

- [ ] **Step 5：執行測試確認通過**

Run: `uv run pytest tests/extraction/test_store.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 6：Commit**

```bash
git add loop_apidoc/extraction/models.py loop_apidoc/extraction/store.py tests/extraction/test_store.py
git commit -m "feat: add extraction artifact models and store"
```

---

### Task 5：擷取 orchestrator（orchestrator）

逐階段驅動查詢：每階段先問 initial；結構化階段若有缺口再問一次 follow-up（接受「來源未提供」，§7.2）；每階段再問 reverse-check。每次查詢經 `run_with_retries` 包裝（§11），並由 store 保存。回傳彙整的 `ExtractionResult`。

**Files:**
- Create: `loop_apidoc/extraction/orchestrator.py`
- Create: `tests/extraction/test_orchestrator.py`

**Interfaces:**
- Consumes: Task 1 `STAGES`/`QueryKind`/`StageMode`、Task 2 `extract_json_block`/`find_gaps`、Task 3 `build_known_summary`/`build_question`、Task 4 `ExtractionStore`/`ExtractionResult`/`AnswerArtifact`；Plan 2 的 `NotebookLMAdapter.ask(question, notebook_url) -> AskResult`（`AskResult.answer: str`、`.returncode: int`）、`run_with_retries(operation, *, max_attempts)`。
- Produces：
  - `run_extraction(adapter: NotebookLMAdapter, notebook_url: str, store: ExtractionStore, *, max_attempts: int = 3) -> ExtractionResult`：依 `STAGES` 順序執行；累積 initial 答案供 `build_known_summary`；對結構化階段以 `extract_json_block`＋`find_gaps` 判斷是否追問；所有 `adapter.ask` 呼叫包在 `run_with_retries(lambda: adapter.ask(q, notebook_url), max_attempts=max_attempts)`。
- 注意：本函式只在 adapter 拋出**非** transient 例外（`AuthRequired`／`NotebookInaccessible`／`MalformedOutput`）時讓其向上傳播而中止擷取（§11「停止」分支）；transient 由 `run_with_retries` 處理。

- [ ] **Step 1：寫失敗測試 `tests/extraction/test_orchestrator.py`**

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.extraction.orchestrator import run_extraction
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.extraction.store import ExtractionStore

NB = "https://notebooklm.google.com/notebook/abc"


class _FakeAskResult:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.returncode = 0


class _FakeAdapter:
    """Returns a complete endpoints block for stage 05, a gappy environments block for
    stage 03 (to force a follow-up that then returns a complete block), and prose
    otherwise. Matches on the quoted JSON keys that the question builder embeds via
    `json_hint` — reverse questions carry no json_hint and fall through to prose.
    Records every question asked."""

    def __init__(self) -> None:
        self.questions: list[str] = []

    def ask(self, question: str, notebook_url: str) -> _FakeAskResult:
        self.questions.append(question)
        if "still unfilled" in question:  # follow-up: re-emit the FULL block, now complete
            return _FakeAskResult('```json\n{"environments": [{"name": "prod", '
                                  '"base_url": "https://api", "version": "v1", '
                                  '"source": "api.pdf"}], "missing": []}\n```')
        if '"endpoints"' in question:
            return _FakeAskResult('```json\n{"endpoints": [{"method": "GET", '
                                  '"path": "/u", "summary": "s", "source": "api.pdf"}], '
                                  '"missing": []}\n```')
        if '"environments"' in question:  # stage 03 initial: null fields -> gaps
            return _FakeAskResult('```json\n{"environments": [{"name": "prod", '
                                  '"base_url": null, "version": null, "source": null}], '
                                  '"missing": ["base_url", "version"]}\n```')
        return _FakeAskResult("Prose answer. The sources cover the basics.")


def test_run_extraction_persists_and_returns(tmp_path: Path):
    store = ExtractionStore(tmp_path)
    adapter = _FakeAdapter()
    result = run_extraction(adapter, NB, store)

    # 10 stages: each has initial + reverse; structured stage 03 also has a followup.
    ids = [a.query_id for a in result.artifacts]
    assert "01-initial" in ids and "01-reverse" in ids
    assert "03-initial" in ids and "03-followup" in ids and "03-reverse" in ids
    assert "05-initial" in ids
    # stage 05 had no gaps -> no follow-up
    assert "05-followup" not in ids

    # persisted
    assert (tmp_path / "answers" / "03-followup.txt").exists()
    assert (tmp_path / "queries.jsonl").exists()


def test_followup_only_when_gaps(tmp_path: Path):
    store = ExtractionStore(tmp_path)
    result = run_extraction(_FakeAdapter(), NB, store)
    assert result.latest_structured("03").kind is QueryKind.FOLLOWUP
    assert result.latest_structured("05").kind is QueryKind.INITIAL


def test_questions_carry_notebook_and_context(tmp_path: Path):
    adapter = _FakeAdapter()
    run_extraction(adapter, NB, ExtractionStore(tmp_path))
    assert all(NB in q for q in adapter.questions)
    # later stages should include accumulated known-summary context
    assert any("Known so far" in q for q in adapter.questions)
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/extraction/test_orchestrator.py -v`
Expected: FAIL（`ModuleNotFoundError: ... orchestrator`）。

- [ ] **Step 3：實作 `loop_apidoc/extraction/orchestrator.py`**

```python
from __future__ import annotations

from loop_apidoc.extraction.jsonblock import extract_json_block, find_gaps
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.questions import build_known_summary, build_question
from loop_apidoc.extraction.stages import STAGES, QueryKind, QueryStage, StageMode
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.notebooklm.adapter import NotebookLMAdapter
from loop_apidoc.notebooklm.retry import run_with_retries


def _ask_and_store(
    adapter: NotebookLMAdapter,
    store: ExtractionStore,
    stage: QueryStage,
    kind: QueryKind,
    question: str,
    notebook_url: str,
    max_attempts: int,
) -> AnswerArtifact:
    result = run_with_retries(
        lambda: adapter.ask(question, notebook_url), max_attempts=max_attempts
    )
    return store.record(
        query_id=f"{stage.stage_id}-{kind.value}",
        stage_id=stage.stage_id,
        kind=kind,
        question=question,
        answer=result.answer,
        returncode=result.returncode,
    )


def run_extraction(
    adapter: NotebookLMAdapter,
    notebook_url: str,
    store: ExtractionStore,
    *,
    max_attempts: int = 3,
) -> ExtractionResult:
    artifacts: list[AnswerArtifact] = []
    prior_initials: list[tuple[str, str]] = []

    for stage in STAGES:
        known = build_known_summary(prior_initials)

        initial_q = build_question(
            stage, QueryKind.INITIAL, notebook_url=notebook_url, known_summary=known
        )
        initial = _ask_and_store(
            adapter, store, stage, QueryKind.INITIAL, initial_q, notebook_url, max_attempts
        )
        artifacts.append(initial)
        prior_initials.append((stage.title, initial.answer))

        if stage.mode is StageMode.STRUCTURED:
            block = extract_json_block(initial.answer)
            gaps = find_gaps(block) if block is not None else []
            if gaps:
                followup_q = build_question(
                    stage, QueryKind.FOLLOWUP, notebook_url=notebook_url,
                    known_summary=known, pending_fields=gaps,
                )
                artifacts.append(
                    _ask_and_store(adapter, store, stage, QueryKind.FOLLOWUP,
                                   followup_q, notebook_url, max_attempts)
                )

        reverse_q = build_question(
            stage, QueryKind.REVERSE, notebook_url=notebook_url, known_summary=known
        )
        artifacts.append(
            _ask_and_store(adapter, store, stage, QueryKind.REVERSE,
                           reverse_q, notebook_url, max_attempts)
        )

    return ExtractionResult(notebook_url=notebook_url, artifacts=artifacts)
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/extraction/test_orchestrator.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/extraction/orchestrator.py tests/extraction/test_orchestrator.py
git commit -m "feat: add extraction orchestrator over staged queries"
```

---

### Task 6：規格化計畫模型（plan/models）

定義 spec §7.3 的機器可讀計畫 schema：系統分組、endpoint／schema／security／error／environment／operational inventory、每項的來源追溯與狀態，以及缺漏／衝突／無法確認的彙整列表。

**Files:**
- Create: `loop_apidoc/plan/__init__.py`
- Create: `loop_apidoc/plan/models.py`
- Create: `tests/plan/__init__.py`
- Create: `tests/plan/test_models.py`

**Interfaces:**
- Consumes: 無。
- Produces：
  - `PlanItemStatus(str, Enum)`：`SUPPORTED = "supported"`、`CONFLICTING = "conflicting"`、`MISSING = "missing"`、`UNVERIFIED = "unverified"`（值逐字取自 spec §8.3）。
  - `SourceCitation(BaseModel)`：`query_id: str`、`answer_path: str`、`manifest_source: str | None = None`、`locator: str | None = None`。
  - 各 inventory 條目（皆含 `status: PlanItemStatus` 與 `citations: list[SourceCitation]`）：
    - `EnvironmentEntry`：`name`、`base_url`、`version`（皆 `str | None`）。
    - `SecuritySchemeEntry`：`name`、`type`、`location`、`details`（皆 `str | None`）。
    - `EndpointEntry`：`method`、`path`、`summary`（皆 `str | None`）、`parameters: list[dict] = []`、`request: dict | None = None`、`responses: list[dict] = []`、`examples: list[dict] = []`。
    - `SchemaEntry`：`name: str | None`、`fields: list[dict] = []`、`enums: list[dict] = []`、`constraints: str | None = None`。
    - `ErrorEntry`：`code`、`meaning`、`http_status`（皆 `str | None`）。
    - `OperationalEntry`：`topic`、`detail`（皆 `str | None`）。
  - `SystemGroup(BaseModel)`：`name: str`、`description: str | None = None`。
  - `MissingItem(BaseModel)`：`area: str`、`detail: str`、`query_id: str | None = None`。
  - `SourceConflict(BaseModel)`：`area: str`、`detail: str`、`query_id: str | None = None`。
  - `UnverifiedItem(BaseModel)`：`area: str`、`detail: str`、`query_id: str | None = None`。
  - `NormalizationPlan(BaseModel)`：`notebook_url: str`、`source_inventory_note: str = ""`、`overview_note: str = ""`、`conflicts_note: str = ""`、`system_groups: list[SystemGroup] = []`、`environments: list[EnvironmentEntry] = []`、`security_schemes: list[SecuritySchemeEntry] = []`、`endpoints: list[EndpointEntry] = []`、`schemas: list[SchemaEntry] = []`、`errors: list[ErrorEntry] = []`、`operational: list[OperationalEntry] = []`、`missing_items: list[MissingItem] = []`、`source_conflicts: list[SourceConflict] = []`、`unverified_items: list[UnverifiedItem] = []`。

- [ ] **Step 1：建立 `tests/plan/__init__.py`（空檔）**

```python
```

- [ ] **Step 2：寫失敗測試 `tests/plan/test_models.py`**

```python
from __future__ import annotations

import json

from loop_apidoc.plan.models import (
    EndpointEntry,
    NormalizationPlan,
    PlanItemStatus,
    SourceCitation,
)


def test_status_values():
    assert PlanItemStatus.SUPPORTED.value == "supported"
    assert PlanItemStatus.UNVERIFIED.value == "unverified"
    assert PlanItemStatus.MISSING.value == "missing"
    assert PlanItemStatus.CONFLICTING.value == "conflicting"


def test_endpoint_entry_defaults():
    entry = EndpointEntry(
        method="GET", path="/u", summary="s", status=PlanItemStatus.SUPPORTED,
        citations=[SourceCitation(query_id="05-initial", answer_path="answers/05-initial.txt",
                                  manifest_source="api.pdf", locator="api.pdf")],
    )
    assert entry.parameters == []
    assert entry.responses == []
    assert entry.citations[0].manifest_source == "api.pdf"


def test_plan_round_trips_json():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        overview_note="It is an API.",
        endpoints=[EndpointEntry(method="GET", path="/u", summary=None,
                                 status=PlanItemStatus.UNVERIFIED, citations=[])],
    )
    payload = plan.model_dump_json(indent=2)
    restored = NormalizationPlan.model_validate(json.loads(payload))
    assert restored.endpoints[0].status is PlanItemStatus.UNVERIFIED
    assert restored.notebook_url == "https://nb/x"
    assert restored.environments == []
```

- [ ] **Step 3：執行測試確認失敗**

Run: `uv run pytest tests/plan/test_models.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'loop_apidoc.plan'`）。

- [ ] **Step 4：建立 `loop_apidoc/plan/__init__.py`**

```python
"""Machine-readable normalization plan layer (spec §7.3)."""
```

- [ ] **Step 5：實作 `loop_apidoc/plan/models.py`**

```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PlanItemStatus(str, Enum):
    SUPPORTED = "supported"
    CONFLICTING = "conflicting"
    MISSING = "missing"
    UNVERIFIED = "unverified"


class SourceCitation(BaseModel):
    query_id: str
    answer_path: str
    manifest_source: str | None = None
    locator: str | None = None


class _Cited(BaseModel):
    status: PlanItemStatus
    citations: list[SourceCitation] = Field(default_factory=list)


class EnvironmentEntry(_Cited):
    name: str | None = None
    base_url: str | None = None
    version: str | None = None


class SecuritySchemeEntry(_Cited):
    name: str | None = None
    type: str | None = None
    location: str | None = None
    details: str | None = None


class EndpointEntry(_Cited):
    method: str | None = None
    path: str | None = None
    summary: str | None = None
    parameters: list[dict] = Field(default_factory=list)
    request: dict | None = None
    responses: list[dict] = Field(default_factory=list)
    examples: list[dict] = Field(default_factory=list)


class SchemaEntry(_Cited):
    name: str | None = None
    fields: list[dict] = Field(default_factory=list)
    enums: list[dict] = Field(default_factory=list)
    constraints: str | None = None


class ErrorEntry(_Cited):
    code: str | None = None
    meaning: str | None = None
    http_status: str | None = None


class OperationalEntry(_Cited):
    topic: str | None = None
    detail: str | None = None


class SystemGroup(BaseModel):
    name: str
    description: str | None = None


class MissingItem(BaseModel):
    area: str
    detail: str
    query_id: str | None = None


class SourceConflict(BaseModel):
    area: str
    detail: str
    query_id: str | None = None


class UnverifiedItem(BaseModel):
    area: str
    detail: str
    query_id: str | None = None


class NormalizationPlan(BaseModel):
    notebook_url: str
    source_inventory_note: str = ""
    overview_note: str = ""
    conflicts_note: str = ""
    system_groups: list[SystemGroup] = Field(default_factory=list)
    environments: list[EnvironmentEntry] = Field(default_factory=list)
    security_schemes: list[SecuritySchemeEntry] = Field(default_factory=list)
    endpoints: list[EndpointEntry] = Field(default_factory=list)
    schemas: list[SchemaEntry] = Field(default_factory=list)
    errors: list[ErrorEntry] = Field(default_factory=list)
    operational: list[OperationalEntry] = Field(default_factory=list)
    missing_items: list[MissingItem] = Field(default_factory=list)
    source_conflicts: list[SourceConflict] = Field(default_factory=list)
    unverified_items: list[UnverifiedItem] = Field(default_factory=list)
```

- [ ] **Step 6：執行測試確認通過**

Run: `uv run pytest tests/plan/test_models.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 7：Commit**

```bash
git add loop_apidoc/plan/__init__.py loop_apidoc/plan/models.py tests/plan/__init__.py tests/plan/test_models.py
git commit -m "feat: add normalization plan schema models"
```

---

### Task 7：來源比對與狀態分類（plan/classify）

把結構化條目的 `source` 定位字串與 manifest 做名稱比對（spec §6），並依比對結果指派 `PlanItemStatus` 與建立 `SourceCitation`（spec §8.3）。

**Files:**
- Create: `loop_apidoc/plan/classify.py`
- Create: `tests/plan/test_classify.py`

**Interfaces:**
- Consumes: Task 6 的 `PlanItemStatus`、`SourceCitation`；Plan 1 的 `Manifest`（`.local_sources[].relative_path`、`.url_sources[].url`）。
- Produces：
  - `match_manifest_source(locator: str | None, manifest: Manifest) -> str | None`：`locator` 為空回 `None`；否則做大小寫不敏感子字串比對——任一 `local_source` 的 `relative_path` 或其 basename 出現在 locator 中則回該 `relative_path`；任一 `url_source.url` 出現在 locator 中則回該 url；無命中回 `None`。
  - `classify_item(locator: str | None, *, query_id: str, answer_path: str, manifest: Manifest) -> tuple[PlanItemStatus, SourceCitation]`：`manifest_source = match_manifest_source(locator, manifest)`；`locator` 有值且命中 → `SUPPORTED`；其餘（locator 缺、或具名但未命中 manifest）→ `UNVERIFIED`（§6.3）。一律回傳含 `query_id`、`answer_path`、`manifest_source`、`locator` 的 `SourceCitation`。

- [ ] **Step 1：寫失敗測試 `tests/plan/test_classify.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.classify import classify_item, match_manifest_source
from loop_apidoc.plan.models import PlanItemStatus


def _manifest() -> Manifest:
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return Manifest(
        sources_root="/src",
        generated_at=now,
        local_sources=[
            LocalSource(relative_path="docs/api.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
                        scanned_at=now, supported=True, status=ProcessingStatus.PENDING),
        ],
    )


def test_match_by_basename():
    assert match_manifest_source("see api.pdf page 4", _manifest()) == "docs/api.pdf"


def test_match_none_when_absent():
    assert match_manifest_source("from the spec", _manifest()) is None
    assert match_manifest_source(None, _manifest()) is None


def test_classify_supported_when_matched():
    status, cite = classify_item(
        "api.pdf §2", query_id="05-initial", answer_path="answers/05-initial.txt",
        manifest=_manifest(),
    )
    assert status is PlanItemStatus.SUPPORTED
    assert cite.manifest_source == "docs/api.pdf"
    assert cite.locator == "api.pdf §2"
    assert cite.query_id == "05-initial"


def test_classify_unverified_when_unmatched_or_missing():
    status, cite = classify_item(
        "internal wiki", query_id="05-initial", answer_path="answers/05-initial.txt",
        manifest=_manifest(),
    )
    assert status is PlanItemStatus.UNVERIFIED
    assert cite.manifest_source is None

    status2, cite2 = classify_item(
        None, query_id="05-initial", answer_path="answers/05-initial.txt",
        manifest=_manifest(),
    )
    assert status2 is PlanItemStatus.UNVERIFIED
    assert cite2.locator is None
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/plan/test_classify.py -v`
Expected: FAIL（`ModuleNotFoundError: ... classify`）。

- [ ] **Step 3：實作 `loop_apidoc/plan/classify.py`**

```python
from __future__ import annotations

from pathlib import Path

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import PlanItemStatus, SourceCitation


def match_manifest_source(locator: str | None, manifest: Manifest) -> str | None:
    if not locator:
        return None
    low = locator.lower()
    for source in manifest.local_sources:
        rel = source.relative_path.lower()
        if rel in low or Path(source.relative_path).name.lower() in low:
            return source.relative_path
    for url_source in manifest.url_sources:
        if url_source.url.lower() in low:
            return url_source.url
    return None


def classify_item(
    locator: str | None,
    *,
    query_id: str,
    answer_path: str,
    manifest: Manifest,
) -> tuple[PlanItemStatus, SourceCitation]:
    manifest_source = match_manifest_source(locator, manifest)
    status = (
        PlanItemStatus.SUPPORTED
        if locator and manifest_source
        else PlanItemStatus.UNVERIFIED
    )
    citation = SourceCitation(
        query_id=query_id,
        answer_path=answer_path,
        manifest_source=manifest_source,
        locator=locator,
    )
    return status, citation
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/plan/test_classify.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/plan/classify.py tests/plan/test_classify.py
git commit -m "feat: add manifest source matching and item classification"
```

---

### Task 8：規格化計畫 builder（plan/builder）

把 `ExtractionResult` 的最新結構區塊組裝成 `NormalizationPlan`：敘事階段答案存入 note 欄位；每個結構化階段以 generic helper 把條目映射成對應 entry，套用 Task 7 的狀態分類與 citation，並把結構化 `missing` 與未命中 manifest 的條目彙整成 `missing_items`／`unverified_items`。

**Files:**
- Create: `loop_apidoc/plan/builder.py`
- Create: `tests/plan/test_builder.py`

**Interfaces:**
- Consumes: Task 2 `extract_json_block`、Task 4 `ExtractionResult`/`AnswerArtifact`、Task 6 全部 plan 模型、Task 7 `classify_item`；Plan 1 `Manifest`。
- Produces：
  - `build_normalization_plan(extraction: ExtractionResult, manifest: Manifest) -> NormalizationPlan`：
    - notes：`source_inventory_note`←stage 01 initial 答案、`overview_note`←stage 02、`conflicts_note`←stage 10（缺則空字串）。
    - 對 inventory stage 03/04/05/07/08/09（**不含 06**）：取 `extraction.latest_structured(stage_id)`；無 artifact 或 `extract_json_block` 回 `None` → 加一筆 `MissingItem(area=stage_id, detail="no structured answer", query_id=...)`，該 inventory 留空。
    - 對區塊中 `json_key` 陣列的每個 item：用對應 factory 建 entry，`status`／`citations` 來自 `classify_item(item.get("source"), query_id=art.query_id, answer_path=art.answer_path, manifest=manifest)`；`status is UNVERIFIED` 時另加一筆 `UnverifiedItem`。
    - 區塊頂層 `missing` 陣列每項 → 一筆 `MissingItem(area=stage_id, detail=str(item), query_id=art.query_id)`；`conflicts` 陣列（選用）每項 → 一筆 `SourceConflict`。
    - **stage 06（逐 endpoint 細節）獨立合併**：把 `endpoint_details` 的每項依 `(method, path)` 併入既有 `plan.endpoints` 條目（填 `parameters`／`request`／`responses`／`examples`），避免與 stage 05 重複；無對應條目則新增一筆 `EndpointEntry` 並做狀態分類。stage 06 缺 artifact／區塊 → `MissingItem(area="06", ...)`。（這些是本函式本地建構的物件，原地填欄不違反「不可變更輸入」原則。）

- [ ] **Step 1：寫失敗測試 `tests/plan/test_builder.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.extraction.stages import QueryKind
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.plan.models import PlanItemStatus


def _manifest() -> Manifest:
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return Manifest(
        sources_root="/src", generated_at=now,
        local_sources=[
            LocalSource(relative_path="api.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
                        scanned_at=now, supported=True, status=ProcessingStatus.PENDING),
        ],
    )


def _art(stage_id: str, kind: QueryKind, answer: str) -> AnswerArtifact:
    qid = f"{stage_id}-{kind.value}"
    return AnswerArtifact(query_id=qid, stage_id=stage_id, kind=kind, answer=answer,
                          answer_path=f"answers/{qid}.txt", returncode=0)


def _extraction() -> ExtractionResult:
    return ExtractionResult(
        notebook_url="https://nb/x",
        artifacts=[
            _art("01", QueryKind.INITIAL, "Two sources: api.pdf and a URL."),
            _art("02", QueryKind.INITIAL, "It is a payments API."),
            _art("05", QueryKind.INITIAL,
                 '```json\n{"endpoints": ['
                 '{"method": "GET", "path": "/u", "summary": "list", "source": "api.pdf"},'
                 '{"method": "POST", "path": "/u", "summary": "create", "source": null}],'
                 ' "missing": ["pagination"]}\n```'),
            _art("10", QueryKind.INITIAL, "No conflicts found."),
        ],
    )


def test_builds_notes():
    plan = build_normalization_plan(_extraction(), _manifest())
    assert plan.source_inventory_note.startswith("Two sources")
    assert plan.overview_note == "It is a payments API."
    assert plan.conflicts_note == "No conflicts found."
    assert plan.notebook_url == "https://nb/x"


def test_endpoints_classified():
    plan = build_normalization_plan(_extraction(), _manifest())
    assert len(plan.endpoints) == 2
    supported = [e for e in plan.endpoints if e.status is PlanItemStatus.SUPPORTED]
    unverified = [e for e in plan.endpoints if e.status is PlanItemStatus.UNVERIFIED]
    assert supported[0].path == "/u" and supported[0].method == "GET"
    assert supported[0].citations[0].manifest_source == "api.pdf"
    assert len(unverified) == 1


def test_missing_and_unverified_aggregated():
    plan = build_normalization_plan(_extraction(), _manifest())
    assert any(m.detail == "pagination" and m.area == "05" for m in plan.missing_items)
    assert any(u.area == "05" for u in plan.unverified_items)


def test_absent_structured_stage_records_missing():
    plan = build_normalization_plan(_extraction(), _manifest())
    # stages 03,04,06,07,08,09 had no artifacts -> each contributes a missing item
    areas = {m.area for m in plan.missing_items}
    assert {"03", "04", "06", "07", "08", "09"}.issubset(areas)
    assert plan.environments == []
```

- [ ] **Step 2：執行測試確認失敗**

Run: `uv run pytest tests/plan/test_builder.py -v`
Expected: FAIL（`ModuleNotFoundError: ... builder`）。

- [ ] **Step 3：實作 `loop_apidoc/plan/builder.py`**

```python
from __future__ import annotations

from typing import Callable

from loop_apidoc.extraction.jsonblock import extract_json_block
from loop_apidoc.extraction.models import AnswerArtifact, ExtractionResult
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.classify import classify_item
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    ErrorEntry,
    MissingItem,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SchemaEntry,
    SecuritySchemeEntry,
    SourceConflict,
    UnverifiedItem,
)

# inventory stage_id -> (json_key, plan_field, entry_class, field factory). Stage 06
# is handled separately (merged into endpoints), so it is intentionally absent here.
_INVENTORY: dict[str, tuple[str, str, type, Callable[[dict], dict]]] = {
    "03": ("environments", "environments", EnvironmentEntry,
           lambda i: {"name": i.get("name"), "base_url": i.get("base_url"),
                      "version": i.get("version")}),
    "04": ("security_schemes", "security_schemes", SecuritySchemeEntry,
           lambda i: {"name": i.get("name"), "type": i.get("type"),
                      "location": i.get("location"), "details": i.get("details")}),
    "05": ("endpoints", "endpoints", EndpointEntry,
           lambda i: {"method": i.get("method"), "path": i.get("path"),
                      "summary": i.get("summary")}),
    "07": ("schemas", "schemas", SchemaEntry,
           lambda i: {"name": i.get("name"), "fields": i.get("fields") or [],
                      "enums": i.get("enums") or [], "constraints": i.get("constraints")}),
    "08": ("errors", "errors", ErrorEntry,
           lambda i: {"code": i.get("code"), "meaning": i.get("meaning"),
                      "http_status": i.get("http_status")}),
    "09": ("operational", "operational", OperationalEntry,
           lambda i: {"topic": i.get("topic"), "detail": i.get("detail")}),
}


def _note(extraction: ExtractionResult, stage_id: str) -> str:
    art = extraction.initial(stage_id)
    return art.answer if art else ""


def _structured_block(
    extraction: ExtractionResult, stage_id: str
) -> tuple[AnswerArtifact | None, dict | None]:
    art = extraction.latest_structured(stage_id)
    block = extract_json_block(art.answer) if art is not None else None
    return art, block


def _add_missing_and_conflicts(plan: NormalizationPlan, stage_id: str,
                               art: AnswerArtifact, block: dict) -> None:
    for miss in block.get("missing") or []:
        plan.missing_items.append(
            MissingItem(area=stage_id, detail=str(miss), query_id=art.query_id)
        )
    for conflict in block.get("conflicts") or []:
        plan.source_conflicts.append(
            SourceConflict(area=stage_id, detail=str(conflict), query_id=art.query_id)
        )


def build_normalization_plan(
    extraction: ExtractionResult, manifest: Manifest
) -> NormalizationPlan:
    plan = NormalizationPlan(
        notebook_url=extraction.notebook_url,
        source_inventory_note=_note(extraction, "01"),
        overview_note=_note(extraction, "02"),
        conflicts_note=_note(extraction, "10"),
    )

    for stage_id, (json_key, plan_field, entry_class, factory) in _INVENTORY.items():
        art, block = _structured_block(extraction, stage_id)
        if block is None:
            plan.missing_items.append(
                MissingItem(area=stage_id, detail="no structured answer",
                            query_id=art.query_id if art else None)
            )
            continue

        target = getattr(plan, plan_field)
        for item in block.get(json_key) or []:
            status, citation = classify_item(
                item.get("source"), query_id=art.query_id,
                answer_path=art.answer_path, manifest=manifest,
            )
            target.append(entry_class(status=status, citations=[citation], **factory(item)))
            if status is PlanItemStatus.UNVERIFIED:
                label = item.get("path") or item.get("name") or item.get("code") or json_key
                plan.unverified_items.append(
                    UnverifiedItem(area=stage_id, detail=str(label), query_id=art.query_id)
                )
        _add_missing_and_conflicts(plan, stage_id, art, block)

    _merge_endpoint_details(plan, extraction, manifest)
    return plan


def _merge_endpoint_details(
    plan: NormalizationPlan, extraction: ExtractionResult, manifest: Manifest
) -> None:
    art, block = _structured_block(extraction, "06")
    if block is None:
        plan.missing_items.append(
            MissingItem(area="06", detail="no structured answer",
                        query_id=art.query_id if art else None)
        )
        return

    for item in block.get("endpoint_details") or []:
        detail = {
            "parameters": item.get("parameters") or [],
            "request": item.get("request"),
            "responses": item.get("responses") or [],
            "examples": item.get("examples") or [],
        }
        match = next(
            (e for e in plan.endpoints
             if e.method == item.get("method") and e.path == item.get("path")),
            None,
        )
        if match is not None:
            match.parameters = detail["parameters"]
            match.request = detail["request"]
            match.responses = detail["responses"]
            match.examples = detail["examples"]
            continue
        status, citation = classify_item(
            item.get("source"), query_id=art.query_id,
            answer_path=art.answer_path, manifest=manifest,
        )
        plan.endpoints.append(
            EndpointEntry(method=item.get("method"), path=item.get("path"), summary=None,
                          status=status, citations=[citation], **detail)
        )
        if status is PlanItemStatus.UNVERIFIED:
            plan.unverified_items.append(
                UnverifiedItem(area="06", detail=str(item.get("path") or "endpoint"),
                               query_id=art.query_id)
            )
    _add_missing_and_conflicts(plan, "06", art, block)
```

- [ ] **Step 4：執行測試確認通過**

Run: `uv run pytest tests/plan/test_builder.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5：Commit**

```bash
git add loop_apidoc/plan/builder.py tests/plan/test_builder.py
git commit -m "feat: add normalization plan builder with provenance"
```

---

### Task 9：端對端整合測試（extraction → plan → 寫檔）

以 fake adapter＋fixture 回答串接 `run_extraction` 與 `build_normalization_plan`，驗證 run directory 的 `extraction/`＋`plan/` 產物（spec §8、§12.2），不消耗真實額度。

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_extraction_to_plan.py`

**Interfaces:**
- Consumes: Task 4 `ExtractionStore`、Task 5 `run_extraction`、Task 8 `build_normalization_plan`；Plan 1 `Manifest`。
- Produces：無（純測試）。

- [ ] **Step 1：建立 `tests/integration/__init__.py`（空檔）**

```python
```

- [ ] **Step 2：寫整合測試 `tests/integration/test_extraction_to_plan.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.extraction.orchestrator import run_extraction
from loop_apidoc.extraction.store import ExtractionStore
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.builder import build_normalization_plan
from loop_apidoc.plan.models import NormalizationPlan, PlanItemStatus

NB = "https://notebooklm.google.com/notebook/abc"

# stage_id -> answer text; structured stages return a complete json block.
_ANSWERS = {
    "03": '```json\n{"environments": [{"name": "prod", "base_url": "https://api", '
          '"version": "v1", "source": "api.pdf"}], "missing": []}\n```',
    "04": '```json\n{"security_schemes": [{"name": "ApiKey", "type": "apiKey", '
          '"location": "header", "details": "X-Key", "source": "api.pdf"}], '
          '"missing": []}\n```',
    "05": '```json\n{"endpoints": [{"method": "GET", "path": "/u", "summary": "list", '
          '"source": "api.pdf"}], "missing": []}\n```',
    "06": '```json\n{"endpoint_details": [{"method": "GET", "path": "/u", '
          '"parameters": [{"name": "page"}], "request": null, "responses": '
          '[{"status": "200"}], "examples": [], "source": "api.pdf"}], "missing": []}\n```',
    "07": '```json\n{"schemas": [{"name": "User", "fields": [{"name": "id"}], '
          '"enums": [], "constraints": null, "source": "api.pdf"}], "missing": []}\n```',
    "08": '```json\n{"errors": [{"code": "E1", "meaning": "bad", "http_status": "400", '
          '"source": "api.pdf"}], "missing": []}\n```',
    "09": '```json\n{"operational": [{"topic": "rate limit", "detail": "100/m", '
          '"source": "api.pdf"}], "missing": []}\n```',
}


class _Result:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.returncode = 0


# Quoted JSON keys appear only in structured INITIAL questions (via json_hint);
# REVERSE questions carry no json_hint, so they fall through to prose. All blocks are
# complete (missing: []), so no follow-ups occur.
_KEY_TO_STAGE = {
    '"environments"': "03", '"security_schemes"': "04", '"endpoints"': "05",
    '"endpoint_details"': "06", '"schemas"': "07", '"errors"': "08", '"operational"': "09",
}


class _Adapter:
    def ask(self, question: str, notebook_url: str) -> _Result:
        for token, stage_id in _KEY_TO_STAGE.items():
            if token in question:
                return _Result(_ANSWERS[stage_id])
        return _Result("Prose answer; the sources cover the basics.")


def _manifest() -> Manifest:
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return Manifest(
        sources_root="/src", generated_at=now,
        local_sources=[
            LocalSource(relative_path="api.pdf", mime_type="application/pdf",
                        source_format=SourceFormat.PDF, size_bytes=1, sha256="x",
                        scanned_at=now, supported=True, status=ProcessingStatus.PENDING),
        ],
    )


def test_end_to_end_extraction_and_plan(tmp_path: Path):
    run_dir = tmp_path / "run-1"
    extraction_dir = run_dir / "extraction"
    plan_dir = run_dir / "plan"
    plan_dir.mkdir(parents=True)

    store = ExtractionStore(extraction_dir)
    extraction = run_extraction(_Adapter(), NB, store)

    # extraction artifacts on disk
    assert (extraction_dir / "queries.jsonl").exists()
    assert (extraction_dir / "answers" / "05-initial.txt").exists()
    jsonl = (extraction_dir / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(jsonl) == len(extraction.artifacts)
    assert all(json.loads(line)["answer_path"].startswith("answers/") for line in jsonl)

    plan = build_normalization_plan(extraction, _manifest())
    plan_path = plan_dir / "normalization-plan.json"
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    # reload and assert source-grounded structure
    restored = NormalizationPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    # stage 05 endpoint and stage 06 details merge into ONE endpoint, not two
    assert len(restored.endpoints) == 1
    assert restored.endpoints[0].path == "/u"
    assert restored.endpoints[0].status is PlanItemStatus.SUPPORTED
    assert restored.endpoints[0].parameters == [{"name": "page"}]
    assert restored.endpoints[0].responses == [{"status": "200"}]
    assert restored.security_schemes[0].name == "ApiKey"
    assert restored.errors[0].code == "E1"
    assert restored.environments[0].base_url == "https://api"
    # narrative notes preserved
    assert restored.overview_note
    # everything is source-grounded -> no unverified items
    assert restored.unverified_items == []


def test_no_credentials_in_artifacts(tmp_path: Path):
    store = ExtractionStore(tmp_path / "extraction")
    run_extraction(_Adapter(), NB, store)
    blob = (tmp_path / "extraction" / "queries.jsonl").read_text(encoding="utf-8")
    for secret in ("cookie", "browser state", "credential"):
        assert secret.lower() not in blob.lower()
```

- [ ] **Step 3：執行整合測試確認通過**

Run: `uv run pytest tests/integration/test_extraction_to_plan.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 4：執行整個測試套件確認無回歸**

Run: `uv run pytest -q`
Expected: PASS（Plan 1/2 既有測試 ＋ 本計畫新增測試全綠）。

- [ ] **Step 5：Commit**

```bash
git add tests/integration/__init__.py tests/integration/test_extraction_to_plan.py
git commit -m "test: add extraction-to-plan integration coverage"
```

---

## Carry-forward（交付 Plan 4–6）

- **Plan 4 消費點**：`build_normalization_plan(extraction, manifest) -> NormalizationPlan`。OpenAPI／Markdown／provenance 從 `NormalizationPlan` 生成；`SourceCitation`＋`PlanItemStatus` 直接餵 §8.3 provenance；`x-loop-status: missing-source`（§8.1）對應 `MissingItem`／`status is MISSING`。
- **Plan 6 串接**：`run` 命令把 `manifest`（Plan 1）→ `run_extraction`（本計畫，寫 `extraction/`）→ `build_normalization_plan` → 寫 `plan/normalization-plan.json` 串起；run-id 目錄與時間戳由 Plan 6 注入。
- **逐 endpoint fan-out（延後）**：stage 06 目前單一合併查詢；若 Plan 5 完整性驗證顯示 per-endpoint 細節不足，於 Plan 6 把 stage 06 改為依 stage 05 結果動態展開（query_id `06-detail-{index}`），缺漏仍經 `missing` 機制記錄。
- **自動衝突偵測（延後）**：`source_conflicts` 目前僅在結構區塊含 `conflicts` 陣列時填入；跨來源一致性衝突由 Plan 5 §9.3 驗證 surfacing 後回填。
- **系統與 API 分組（延後）**：`NormalizationPlan.system_groups` schema 欄位已備妥（供 Plan 4 消費），但本計畫無專屬分組擷取階段（stage 02 概覽為敘事文字），故保持空列表，不從敘事推測分組。若 Plan 4/5 需要結構化分組，再新增一個結構化階段填入。
- **真實 smoke test（Plan 6 之外手動）**：以小型測試 Notebook 驗證 NotebookLM 是否確實依 `json_hint` 回傳乾淨 ```json 區塊；若實際輸出常夾雜散文，於 `extract_json_block` 增補容錯或於提示加強格式約束。
