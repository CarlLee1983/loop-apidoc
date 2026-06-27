# SKILL 主導 subagent fan-out 擷取(退役 run-agent)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `loop-apidoc` 擷取從 `run-agent`(subprocess `claude -p`)改為由互動 agent 透過唯讀 subagent fan-out 完成,並退役 run-agent。

**Architecture:** 驅動 agent 當純編排器:混合前處理(複雜 PDF 才轉 md)→ 派唯讀 subagent 取 inventory 與逐端點細節(subagent 只回 JSON、主 agent 寫檔)→ `assemble` → 修正迴圈。後半段 plan→generate→validate 不動。新增 `preprocess` CLI;刪除 run-agent CLI 與其 subprocess 模組鏈。

**Tech Stack:** Python ≥3.11、uv、typer、pydantic v2、pymupdf4llm、pytest、ruff。SKILL.md(英文)為 prompt 編排。

## Global Constraints

- 來源是唯一事實依據:來源沒寫 → `null` 並記入 `missing`;禁臆測、禁套 REST/OAuth 慣例;驗證 fail-closed(逐字來自 spec)。
- 套件管理用 `uv`,**不可用 pip**;測試 `uv run pytest`、lint `uv run ruff check .`。
- 只有 `generate/` 與 `run/` 寫檔;其餘為純函式(single file-I/O exit)。subagent 不寫檔,主 agent 寫擷取 JSON。
- SKILL.md 用英文(token 經濟);產物保持 zh-TW。
- 提交格式:`<type>: [ <scope> ] <subject>`;全域已停用 attribution,commit 訊息不加署名行。
- 分支:`refactor/skill-subagent-fanout`(spec 已提交於此)。

---

### Task 1: 新增 `loop-apidoc preprocess` CLI

暴露既有 `prepare_markdown`(pymupdf4llm),供混合前處理把複雜 PDF 轉成高保真 markdown。additive、獨立。

**Files:**
- Modify: `loop_apidoc/cli.py`(在 `assemble` 指令後新增 `preprocess` 指令)
- Test: `tests/test_cli_preprocess.py`(新建)

**Interfaces:**
- Consumes: `loop_apidoc.agentcli.preprocess.prepare_markdown(sources_dir: Path, dest_dir: Path) -> Path`(現有)
- Produces: CLI 指令 `preprocess --sources <dir> --out <dir>`,exit 0,把每個 PDF 轉成 `<out>/<stem>.md`、文字檔原樣複製。

- [ ] **Step 1: 寫失敗測試**

`tests/test_cli_preprocess.py`:

```python
from __future__ import annotations

from pathlib import Path

import pymupdf
from typer.testing import CliRunner

from loop_apidoc.cli import app

runner = CliRunner()


def test_preprocess_copies_text_sources(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "notes.md").write_text("# Hello\nGET /ping", encoding="utf-8")
    out = tmp_path / "md"
    res = runner.invoke(app, ["preprocess", "--sources", str(sources), "--out", str(out)])
    assert res.exit_code == 0
    assert (out / "notes.md").read_text(encoding="utf-8") == "# Hello\nGET /ping"


def test_preprocess_converts_pdf_to_markdown(tmp_path: Path):
    sources = tmp_path / "sources"
    sources.mkdir()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Payment API")
    doc.save(str(sources / "manual.pdf"))
    doc.close()
    out = tmp_path / "md"
    res = runner.invoke(app, ["preprocess", "--sources", str(sources), "--out", str(out)])
    assert res.exit_code == 0
    md = (out / "manual.md").read_text(encoding="utf-8")
    assert "Payment API" in md
    assert "<!-- page 1 -->" in md
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run pytest tests/test_cli_preprocess.py -v`
Expected: FAIL（`No such command 'preprocess'` → exit_code != 0）

- [ ] **Step 3: 加入 `preprocess` 指令**

在 `loop_apidoc/cli.py` 的 `assemble` 指令(結尾 `raise typer.Exit(...)`)之後、`def main()` 之前插入:

```python
@app.command()
def preprocess(
    sources: Path = typer.Option(
        ..., "--sources", help="本機來源目錄",
        exists=True, file_okay=False, dir_okay=True, readable=True,
    ),
    out: Path = typer.Option(
        ..., "--out", help="markdown 輸出目錄（衍生位置，勿放 sources/ 內）"
    ),
) -> None:
    """把 sources 下每個 PDF 轉成 markdown（pymupdf4llm，保留表格／標題結構），
    非 PDF 文字檔原樣複製。供 agent-native 擷取時 subagent 讀取高保真 markdown。"""
    from loop_apidoc.agentcli.preprocess import prepare_markdown

    dest = prepare_markdown(sources, out)
    count = sum(1 for p in dest.glob("*") if p.is_file())
    typer.echo(f"已前處理 {count} 個檔案於 {dest}")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run pytest tests/test_cli_preprocess.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: lint + commit**

```bash
uv run ruff check loop_apidoc/cli.py tests/test_cli_preprocess.py
git add loop_apidoc/cli.py tests/test_cli_preprocess.py
git commit -m "feat: [cli] 新增 preprocess 指令暴露 PDF→markdown(pymupdf4llm)"
```

---

### Task 2: 退役 run-agent(刪 CLI 指令、subprocess 模組鏈,瘦身 extraction.py)

一次性、有序移除,期間不讓 import 懸空。注意:本次稍早為證明 #3 而在 `pipeline.py`/`cli.py` 加的 `--timeout`(及 `tests/test_cli_run_agent.py`)隨此一併移除——那些改動**尚未提交**。

**Files:**
- Modify: `loop_apidoc/cli.py`（刪 `run-agent` 指令，含未提交的 `--timeout`）
- Delete: `loop_apidoc/agentcli/pipeline.py`、`adapter.py`、`runner.py`、`commands.py`、`parsing.py`、`answer_quality.py`、`config.py`、`errors.py`、`models.py`
- Modify: `loop_apidoc/agentcli/extraction.py`（只留 `inventory_to_stage_answers`/`_block`/`_stage00`）
- Modify: `loop_apidoc/agentcli/__init__.py`（更新 docstring，移除 claude -p 描述）
- Modify: `tests/agentcli/test_collapsed_extraction.py`（移除測 `run_agent_extraction`/`INVENTORY_PROMPT` 部分）
- Delete: `tests/agentcli/test_agentcli.py`、`tests/test_cli_run_agent.py`

**Interfaces:**
- Produces（保留供 assemble）：`loop_apidoc.agentcli.extraction.inventory_to_stage_answers(inventory: dict) -> dict[str, str]`，行為不變。
- Removed：`run_agent_extraction`、`INVENTORY_PROMPT`、`run_agent_pipeline`、`ClaudeCodeAdapter`、`AgentConfig`、`subprocess_runner` 等及 `run-agent` CLI。

- [ ] **Step 1: 從 cli.py 移除 `run-agent` 指令**

刪除 `loop_apidoc/cli.py` 中整個 `@app.command(name="run-agent")` 函式(`def run_agent(...)` 連同其 docstring、`--timeout` option、函式本體到 `raise typer.Exit(...)`)。保留 `manifest`/`validate`/`assemble`/`preprocess` 與頂層 import。

- [ ] **Step 2: 刪除 pipeline.py**

```bash
git rm loop_apidoc/agentcli/pipeline.py
```

- [ ] **Step 3: 瘦身 extraction.py**

把 `loop_apidoc/agentcli/extraction.py` 整檔替換為(只留 assemble 仍需的轉換,移除所有 claude -p 擷取與其 import):

```python
from __future__ import annotations

import json

# Which inventory key feeds which plan stage; each becomes that stage's INITIAL
# structured answer so build_normalization_plan consumes it unchanged.
_INVENTORY_STAGES: tuple[tuple[str, str], ...] = (
    ("03", "environments"),
    ("04", "security_schemes"),
    ("05", "endpoints"),
    ("07", "schemas"),
    ("08", "errors"),
    ("09", "operational"),
)


def _block(key: str, inventory: dict) -> str:
    # The global `missing` list is surfaced once via stage 10; copying it into
    # every inventory stage block here would make the plan record each gap once
    # per stage and the guide repeat it N times.
    value = inventory.get(key)
    payload = {key: value if isinstance(value, list) else []}
    return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def _stage00(inventory: dict) -> str:
    """Encode the source title (and optional document version) for stage 00.

    Title-only stays plain text (the long-standing contract); when a source
    version is present we emit a small JSON object so the version survives the
    text-artifact seam into the plan and OpenAPI `info.version`."""
    title = str(inventory.get("title") or "").strip()
    version = str(inventory.get("version") or "").strip()
    if version:
        payload = {"title": title or None, "version": version}
        return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    return title


def inventory_to_stage_answers(inventory: dict) -> dict[str, str]:
    """Split one inventory JSON into per-stage answer texts (pure).

    The agent-native `assemble` path writes inventory.json directly; this maps it
    into the per-stage INITIAL answers build_normalization_plan consumes."""
    answers: dict[str, str] = {
        "00": _stage00(inventory),
        "01": "Source inventory: a single source manual was provided and read.",
        "02": str(inventory.get("overview") or "").strip()
        or "(no overview stated)",
        "10": "Gaps/conflicts: " + "; ".join(
            str(m) for m in (inventory.get("missing") or [])
        ) if inventory.get("missing") else "(none reported)",
    }
    for stage_id, key in _INVENTORY_STAGES:
        answers[stage_id] = _block(key, inventory)
    return answers
```

- [ ] **Step 4: 刪除 subprocess 模組鏈**

```bash
git rm loop_apidoc/agentcli/adapter.py loop_apidoc/agentcli/runner.py \
       loop_apidoc/agentcli/commands.py loop_apidoc/agentcli/parsing.py \
       loop_apidoc/agentcli/answer_quality.py loop_apidoc/agentcli/config.py \
       loop_apidoc/agentcli/errors.py loop_apidoc/agentcli/models.py
```

- [ ] **Step 5: 更新 `agentcli/__init__.py` docstring**

把 `loop_apidoc/agentcli/__init__.py` 整檔替換為:

```python
"""Agent-native extraction support.

The interactive agent (driven by skills/loop-apidoc/SKILL.md) extracts sources
itself and writes inventory.json + endpoints/*.json; this package only assembles
that agent-written JSON (assemble.py), converts inventory.json into plan stage
answers (extraction.py), and preprocesses PDFs to markdown (preprocess.py).
"""
```

- [ ] **Step 6: 修剪 test_collapsed_extraction.py**

把 `tests/agentcli/test_collapsed_extraction.py` 整檔替換為(只留 `inventory_to_stage_answers` 測試,移除 `_FakeAdapter`/`run_agent_extraction`/`INVENTORY_PROMPT` 相關):

```python
from __future__ import annotations

from loop_apidoc.agentcli.extraction import inventory_to_stage_answers
from loop_apidoc.extraction.jsonblock import extract_json_block

_INVENTORY = {
    "overview": "A payments API.",
    "environments": [{"name": "prod", "base_url": "https://api", "version": "v1",
                      "source": "p.1"}],
    "security_schemes": [{"name": "AES", "type": None, "location": None,
                          "details": None, "source": "p.2"}],
    "endpoints": [{"method": "POST", "path": "/pay", "summary": "pay",
                   "source": "p.3"}],
    "schemas": [],
    "errors": [{"code": "E1", "meaning": "bad", "http_status": "400", "source": "p.9"}],
    "operational": [{"topic": "rate", "detail": "100/m", "source": "p.10"}],
    "missing": ["webhooks"],
}


def test_inventory_split_maps_each_stage():
    answers = inventory_to_stage_answers(_INVENTORY)
    assert "A payments API." in answers["02"]
    assert extract_json_block(answers["03"])["environments"][0]["base_url"] == "https://api"
    assert extract_json_block(answers["04"])["security_schemes"][0]["name"] == "AES"
    assert extract_json_block(answers["05"])["endpoints"][0]["path"] == "/pay"
    assert extract_json_block(answers["08"])["errors"][0]["code"] == "E1"
    assert extract_json_block(answers["09"])["operational"][0]["topic"] == "rate"
    assert "webhooks" in answers["10"]


def test_title_surfaced_in_stage_00():
    answers = inventory_to_stage_answers({**_INVENTORY, "title": "Acme Pay API"})
    assert answers["00"] == "Acme Pay API"


def test_missing_title_yields_blank_stage_00():
    answers = inventory_to_stage_answers(_INVENTORY)
    assert answers["00"] == ""


def test_version_encoded_with_title_in_stage_00():
    answers = inventory_to_stage_answers(
        {**_INVENTORY, "title": "Acme Pay API", "version": "NDNF-1.2.2"})
    block = extract_json_block(answers["00"])
    assert block == {"title": "Acme Pay API", "version": "NDNF-1.2.2"}


def test_version_without_title_still_carried_in_stage_00():
    answers = inventory_to_stage_answers({**_INVENTORY, "version": "v3"})
    block = extract_json_block(answers["00"])
    assert block == {"title": None, "version": "v3"}


def test_global_missing_not_duplicated_into_every_inventory_stage():
    answers = inventory_to_stage_answers(_INVENTORY)
    for sid in ("03", "04", "05", "07", "08", "09"):
        assert "missing" not in extract_json_block(answers[sid])
    assert "webhooks" in answers["10"]
```

- [ ] **Step 7: 刪除過時測試**

```bash
git rm tests/agentcli/test_agentcli.py tests/test_cli_run_agent.py
```

- [ ] **Step 8: 全套測試 + lint**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 全綠（無 import error、無 run_agent 殘留參照）；ruff All checks passed。
若有殘留參照(例如某 import 仍指向已刪模組)→ 依錯誤訊息修正後重跑。

- [ ] **Step 9: commit**

```bash
git add -A
git commit -m "refactor: [agentcli/cli] 退役 run-agent(claude -p),保留 assemble/preprocess"
```

---

### Task 3: 改寫 SKILL.md 為 subagent fan-out

把擷取改為驅動 agent 編排唯讀 subagent;新增混合前處理、subagent 契約、修正迴圈派發。純 prompt,無單元測試,Task 4 e2e 驗收。

**Files:**
- Modify: `skills/loop-apidoc/SKILL.md`

**Interfaces:**
- Consumes: `loop-apidoc preprocess`(Task 1)、`loop-apidoc assemble`(現有)。
- Produces: 驅動 agent 的擷取編排指令(subagent 派發 + 主 agent 寫 `<WORK>/inventory.json`、`<WORK>/endpoints/<NN>.json`)。

- [ ] **Step 1: §1 收集來源 — 加入混合前處理**

在 SKILL.md「### 1. Collect sources」段落,把「Local files (PDF/MD/HTML): read directly with Read.」改寫為:

```markdown
- Local files: record the source directory as `<SOURCES>`.
  - MD/HTML/small PDF: subagents read the file directly with Read.
  - **Table-heavy or large PDF**: first flatten to high-fidelity markdown —
    `uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc preprocess --sources "<SOURCES>" --out "<WORK>/sources_md"`
    (pymupdf4llm preserves tables/headings; raw PDF reads distort tables).
    Point extraction subagents at `<WORK>/sources_md`.
- Public URLs: fetch as text with WebFetch or defuddle; pass URLs via `--url`.
```

- [ ] **Step 2: 新增「Subagent contract」區塊**

在 §1 之後、§2 之前插入:

```markdown
## Subagent contract (extraction)

You orchestrate; **read-only subagents extract**. For every extraction below,
dispatch a subagent restricted to read-only tools (Read/Grep/Glob — **no web, no
write**). Give it: the source location (`<SOURCES>` or `<WORK>/sources_md`), the
exact JSON schema to fill, and the grounding rule. The subagent **returns the
JSON only** (no prose, no file writes). **You (the orchestrator) are the only
writer** — you write the returned JSON to disk. Grounding rule to include in every
subagent prompt: *"Fill strictly from the sources. Anything the sources do not
state → null and add a short label to `missing`. Never infer; never apply
REST/OAuth conventions. Return only the JSON object."*
```

- [ ] **Step 3: 改寫 §2 inventory 為 subagent 派發**

把「### 2. Extract inventory」開頭改為:

```markdown
### 2. Extract inventory → write `<WORK>/inventory.json`
Dispatch **one** read-only subagent (per the Subagent contract) to read every
source and **return one** JSON object with this schema. Then **you** write the
returned object to `<WORK>/inventory.json`.
```

(下方既有 JSON schema 與欄位說明保留不變。)

- [ ] **Step 4: 改寫 §3 per-endpoint 為平行 fan-out**

把「### 3. Extract each endpoint's detail」開頭改為:

```markdown
### 3. Extract each endpoint's detail → write `<WORK>/endpoints/<NN>.json`
For **every** endpoint in `inventory.endpoints`, dispatch a read-only subagent
**in parallel** (one per endpoint; batch if there are many) that returns one JSON
object with the schema below. Pass each subagent its endpoint identity
(`method`/`path`/`summary`/`source`) and the source location. **You** write each
returned object to `<WORK>/endpoints/ep<N>.json` (`ep0.json`, `ep1.json`, …).
```

(下方既有 endpoint schema、nested/tags/security/schema_ref/webhooks 說明保留不變。)

- [ ] **Step 5: 改寫 §5 修正迴圈為定向 subagent**

把「### 5. Correction loop」的 `ok == false` 項改為:

```markdown
- `ok == false` → read `report.issues` (`code`/`severity`/`location`/`evidence`/
  `suggested_fix`); from `location` identify the inventory field or the endpoint
  at fault, **dispatch a targeted read-only subagent to re-read only the relevant
  source** and return the corrected JSON, then **you** overwrite `inventory.json`
  or the matching `endpoints/<NN>.json` and return to step 4.
```

- [ ] **Step 6: 檢視整份 SKILL.md 一致性**

確認:不再出現 `run-agent`/`claude -p`;§4 assemble 指令不變;`<WORK>` 路徑一致;全文英文。

- [ ] **Step 7: commit**

```bash
git add skills/loop-apidoc/SKILL.md
git commit -m "feat: [skill] 擷取改為唯讀 subagent fan-out,主 agent 寫檔;加混合前處理"
```

---

### Task 4: e2e 驗收(藍新 95 頁)

跑一次完整 SKILL 流程,確認退役後產物正確。手動驗證任務(無新程式碼)。

**Files:**
- 無(執行與人眼驗收)

- [ ] **Step 1: 準備工作目錄**

```bash
mkdir -p /tmp/loop-work /tmp/loop-out
```

- [ ] **Step 2: 依 SKILL 流程跑一次(由執行 agent 進行)**

- 對 `sources/線上交易─幕前支付技術串接手冊_NDNF-1.2.2.pdf`(表格密集、95 頁)→ 先 `loop-apidoc preprocess --sources sources --out /tmp/loop-work/sources_md`。
- 派唯讀 subagent 取 inventory → 寫 `/tmp/loop-work/inventory.json`。
- 對每個 endpoint 平行派唯讀 subagent → 寫 `/tmp/loop-work/endpoints/ep<N>.json`。
- `uv run --project . loop-apidoc assemble --sources sources --extraction /tmp/loop-work --output /tmp/loop-out --json`。

- [ ] **Step 3: 驗收**

Run: 解析 assemble 的 `--json` 輸出。
Expected:
- `ok == true`(或僅剩來源真缺漏的 fail-closed,且非崩潰);
- `/tmp/loop-out/<run-id>/openapi.yaml` 的 `info.title`/`info.version` 來自來源(非 Untitled/0.0.0);
- 人眼看 `api-guide.zh-TW.md`:端點/schema 呈現良好、無 query/body 重複、media-type 乾淨。

- [ ] **Step 4: 收尾**

```bash
rm -rf /tmp/loop-work /tmp/loop-out
```

記錄 e2e 結果(PASS/缺漏)於 PR 描述;不提交臨時產物。

---

## 自我檢查結果

- **Spec 覆蓋**:§3 流程→Task 3;§4.1 SKILL→Task 3;§4.2 preprocess CLI→Task 1;§4.3 瘦身 extraction→Task 2 Step 3;§4.4 刪除(含 --timeout)→Task 2;§4.5 保留→Task 2 不動 assemble/preprocess;§6 測試→各 Task 測試步驟 + Task 4 e2e;§8 驗收→Task 4。
- **Placeholder 掃描**:無 TBD/TODO;每個 code 步驟含完整內容。
- **型別一致**:`prepare_markdown(sources_dir, dest_dir) -> Path`、`inventory_to_stage_answers(inventory) -> dict[str,str]` 跨 Task 一致;移除清單與 §4.4 一致。
