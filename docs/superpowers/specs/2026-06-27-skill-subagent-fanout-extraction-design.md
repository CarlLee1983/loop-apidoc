# 設計文件:SKILL 主導的 subagent fan-out 擷取(退役 run-agent)

## 1. 目標

把 `loop-apidoc` 的擷取階段從 `run-agent`(subprocess `claude -p`)轉為**在當前互動 session 內,由驅動 agent 透過唯讀 subagent fan-out 完成**,並退役 `run-agent`。

動機:

- **逾時 / 成本**:大型文件(例:藍新 95 頁)單次 inventory `claude -p` 超過預設 300s 逾時(exit 124);per-endpoint 又序列化呼叫,慢且每次另計費的巢狀 session。
- **架構已半成品**:`assemble` 模式本來就把擷取交給當前 agent、CLI 只做 plan→generate→validate。本設計把最慢的 per-endpoint 擷取**平行化**到 subagent,並讓驅動 agent 維持精簡 context、可擴展到大型文件。

核心不變量不變:**來源是唯一事實依據**。來源沒寫 → `null` 並記入 `missing`;不臆測、不套 REST/OAuth 慣例;驗證 fail-closed。

## 2. 範圍

### 2.1 在範圍

- 改寫 `skills/loop-apidoc/SKILL.md`:擷取改為 subagent 派發。
- 新增 `loop-apidoc preprocess` CLI 指令(暴露既有 pymupdf4llm `prepare_markdown`),供 PDF 混合前處理。
- 瘦身 `loop_apidoc/agentcli/extraction.py`:只保留 `assemble` 仍需的 `inventory_to_stage_answers`。
- 刪除 run-agent 的 CLI 指令與其 subprocess 模組鏈及測試。

### 2.2 不在範圍

- 後半段 plan→generate→validate 不動。
- headless / CI(cron、無互動 agent)生成:本設計**放棄**此路徑(見 §7 風險)。
- 既有生成器 / validator 行為不變(沿用已合 main 的修復)。

## 3. 架構與資料流

驅動 agent(執行 SKILL 的互動式 Claude)為**純編排器**,本身幾乎不持有全文:

```
1. 收集來源       認定 <SOURCES>(本機檔);URL 經 --url 傳入
2. 前處理(混合)  逐 PDF 判斷是否表格密集/複雜:
                  是 → loop-apidoc preprocess 生 <WORK>/sources_md/*.md(pymupdf4llm)
                  否 → subagent 直接 Read 原檔(PDF/MD/HTML)
3. inventory      派 1 個唯讀 subagent,回傳 inventory JSON
                  → 主 agent 寫 <WORK>/inventory.json
4. per-endpoint   對 inventory.endpoints 每一筆,平行派唯讀 subagent,回傳該端點 JSON
                  → 主 agent 寫 <WORK>/endpoints/<NN>.json
5. assemble       loop-apidoc assemble --sources <SOURCES> --extraction <WORK> --output <OUT> --json
6. 修正迴圈(≤3)  ok==false 時依 issue.location 對應 inventory 欄位 / 某端點,
                  派「定向」subagent 重讀該來源回傳修正 JSON → 主 agent 覆寫對應檔 → 回 5
```

### 3.1 唯讀 subagent 契約

- **工具**:僅 `Read / Grep / Glob`。**無 Web、無 Write、無 Bash。**
- **輸入**:來源位置(md 或原檔路徑)+ 任務描述(inventory schema,或某端點的 method/path/summary/source)。
- **輸出**:**只回該段 JSON**(符合 SKILL 定義的 schema),不寫檔、不附解釋。
- **grounding**:prompt 重申來源沒寫就 `null`+`missing`,禁臆測 / 禁 REST/OAuth 慣例。能力(無 Web)+ prompt 雙重保證。

### 3.2 唯一寫檔者

主 agent 是唯一寫 `<WORK>/inventory.json` 與 `<WORK>/endpoints/*.json` 的角色。呼應專案「single file-I/O exit」哲學:subagent 純函式式回傳資料、零檔案碰撞、可平行。

### 3.3 混合前處理判斷

由驅動 agent 主觀判斷,SKILL 給準則(非硬規則):**來源為 PDF 且含多表格 / 大頁數 → 先 `preprocess` 成 markdown 再讀**;MD/HTML/小型 PDF → subagent 直接 Read。理由:`prepare_markdown`(pymupdf4llm,commit f65d4f2)較能保留表格 / 巢狀;Read 對 PDF 是頁面渲染、表格易失真。

## 4. 元件變更

### 4.1 改寫 `skills/loop-apidoc/SKILL.md`

- §1 收集來源:加入混合前處理判斷與 `preprocess` 指令用法。
- §2 inventory:改為「派 1 個唯讀 subagent,回傳 inventory JSON,你(主 agent)寫 inventory.json」。
- §3 per-endpoint:改為「對每個 endpoint 平行派唯讀 subagent,回傳端點 JSON,你寫 endpoints/NN.json」;提示大型文件可分批。
- 新增「Subagent 契約」區塊(§3.1 內容)。
- §5 修正迴圈:改為派定向 subagent 重讀相關來源、回傳修正 JSON,由主 agent 覆寫。
- inventory / endpoint / 修正三種 subagent prompt 範本內嵌於 SKILL(攜帶 JSON schema + grounding 規則)。

### 4.2 新增 `loop-apidoc preprocess` CLI

```
loop-apidoc preprocess --sources <dir> --out <dir>
```

薄包裝既有 `loop_apidoc/agentcli/preprocess.py:prepare_markdown`(pymupdf4llm)。輸出 markdown 供 subagent 讀。

### 4.3 瘦身 `agentcli/extraction.py`

- **保留**:`inventory_to_stage_answers`(+ `_block`、`_stage00`)——`assemble` 把 agent 寫的 inventory.json 轉成 plan stage answers 仍需。
- **移除**:`run_agent_extraction`、`INVENTORY_PROMPT`、`adapter`/`build_endpoint_detail_question` import。
- 擷取 prompt(inventory / endpoint)改由 SKILL 持有(subagent 範本),Python 端不再保留副本。

### 4.4 刪除(run-agent 退役)

- CLI:`run-agent` 指令。
- 模組:`adapter.py`、`runner.py`、`commands.py`、`parsing.py`、`answer_quality.py`、`config.py`、`errors.py`、`pipeline.py`、`models.py`(`AskResult`,僅 adapter 用)。
- 測試:測 `run_agent_extraction` / adapter / runner / pipeline 者;`tests/test_cli_run_agent.py`(含本次臨時加的 `--timeout`)。
- **附帶**:本次為證明 #3 而加在 `pipeline.py` / `cli.py` 的 `--timeout` 旗標隨此退役一併移除,**不另行 commit**。

### 4.5 保留

`assemble.py`、`preprocess.py`、共用 `loop_apidoc/extraction/`(models/stages/store/jsonblock)、plan/generate/validate/run/manifest 全套。

## 5. 錯誤處理 / grounding

- subagent 無 Web 工具 → 物理上無法上網臆測。
- 修正迴圈 ≤3 輪;`SOURCE_UNVERIFIED` / `SOURCE_CONFLICT` / `UNSUPPORTED_ASSERTION` 維持 fail-closed,呈報使用者而非硬填。
- 後半段 plan→generate→validate 不動 → 既有 257 測試與所有生成器修復照常適用。

## 6. 測試策略

- **保留**:`tests/test_cli_assemble.py`、plan/generate/validate 全部、`test_collapsed_extraction.py` 中測 `inventory_to_stage_answers` 的部分。
- **刪除**:測 `run_agent_extraction` / adapter / runner / pipeline 的測試、`tests/test_cli_run_agent.py`。
- **新增**:`preprocess` CLI 測試(PDF→md 有產出、輸出路徑正確)。
- **e2e**:SKILL 為 prompt 無單元測試;以一次真實 e2e(藍新 95 頁)走完整 SKILL 流程,validation PASS + 人眼看 `api-guide.zh-TW.md` 驗收。

## 7. 風險 / 取捨

- **放棄 headless**:此路徑需互動式 agent;cron / CI 無法跑(已選定退役 run-agent)。
- **「複雜」門檻為 agent 主觀判斷**:SKILL 給準則而非硬規則;若日後判斷不穩,可改為硬規則(如 PDF 且頁數 > N 一律 preprocess)。
- **subagent 數量**:端點多(25+)時派發量大、token 成本高;受平行上限節流,SKILL 提示分批。
- **grounding 退化風險**:從 `claude -p` 的 config 鎖定改為 subagent 工具白名單 + prompt;需確保派發時確實限制工具為 Read/Grep/Glob。

## 8. 驗收標準

1. SKILL 走完整流程(含 fan-out)對藍新 95 頁產出 validation PASS、人眼 api-guide 良好。
2. `loop-apidoc preprocess` 可獨立把 PDF 轉 md。
3. run-agent 指令與其 subprocess 模組鏈、相關測試移除後,`uv run pytest` 全綠、`uv run ruff check .` 乾淨。
4. `assemble` 路徑(含 `inventory_to_stage_answers`)不受影響。
