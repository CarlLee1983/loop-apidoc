# loop-apidoc agent-native plugin 設計

> 日期:2026-06-27
> 狀態:設計已核可,待寫 implementation plan

## 目標

把 `loop-apidoc` 的能力包成一個 **Claude Code plugin**。使用者在 Claude session 裡呼叫 skill、給一或多個文檔來源,由 **agent 本身**驅動整個流程(擷取 → 組裝 → 驗證 → 修正)自動跑完,輸出標準化的 OpenAPI / Markdown / provenance / 驗證報告。

## 核心決策(已確認)

1. **完全 agent-native**:由當前的 Claude agent 直接做擷取,**不再 spawn `claude -p`**(無巢狀、無雙重計費)。
2. **agent 主導修正**:驗證失敗時,CLI 回報結構化缺漏清單,agent 回頭重讀來源補齊,重跑驗證,最多 N 輪。
3. **來源型態**:本機檔案(PDF/MD/HTML,agent 直接 Read)+ 公開 URL(agent 自己 WebFetch/defuddle)。不碰 NotebookLM,不需要 PDF→markdown 前處理。
4. **plugin 內含 CLI**:plugin 倉庫自帶 `loop_apidoc` 套件,skill 用 `uv run --project <plugin-dir> loop-apidoc ...` 呼叫。使用者只要裝 plugin + 有 `uv`。

## 架構:反轉控制權

現況是 **Python pipeline 呼叫 claude**(`run-agent` 內部 spawn `claude -p`)。新設計是 **agent 呼叫 Python**,把 CLI 切成兩半:

- **擷取(extraction)** — 由 agent 用自己的工具完成,產出固定 schema 的 JSON 檔。
- **組裝(assemble)** — `manifest → plan → generate → validate` 維持確定性 Python,由 agent 透過新 CLI 子命令呼叫。

agent 在中間扮演 orchestrator,並負責失敗時的修正迴圈。

現有的 `run` (NotebookLM) 與 `run-agent` (`claude -p` 後端) **保留不動**,新流程獨立、向後相容。

## 元件

### (a) plugin 倉庫骨架

- `loop_apidoc` 套件本身(plugin 自帶 CLI)。
- skill:`skills/loop-apidoc/SKILL.md` — 教 agent 整個流程的指令。擷取 schema **直接沿用現成常數**:
  - inventory schema = `loop_apidoc/agentcli/extraction.py` 的 `INVENTORY_PROMPT`
  - per-endpoint detail schema = `loop_apidoc/extraction/questions.py` 的 `_ENDPOINT_DETAIL_SHAPE`
- `plugin.json` / marketplace 設定。

### (b) 新 CLI 子命令 `assemble`(關鍵新程式碼,薄)

```
loop-apidoc assemble --sources <dir> --extraction <dir> --output <dir> [--url ...] [--json]
```

行為:
- 讀 agent 寫好的 `extraction/inventory.json` 與 `extraction/endpoints/*.json`。
- 用既有純函式(`inventory_to_stage_answers` 及 per-endpoint 邏輯)組出 `ExtractionResult` —— 這些邏輯現成,只是改成吃**檔案**而非 `adapter.ask`。
- 跑 `build_manifest → build_normalization_plan → generate_outputs → validate_outputs → write_reports`。
- `--json` 時把驗證結果(PASS/FAIL + 結構化缺漏清單)印到 stdout,供 agent 解析驅動修正。
- 壞掉/缺漏的 JSON → 直接報錯退出(fail loudly),非零狀態碼。

> 設計重點:`assemble` 本質上是 `run_agent_pipeline` 去掉「擷取」那段,改成從磁碟讀 agent 產物。盡量複用,不重寫 plan/generate/validate。

## 資料契約(agent 產物 → assemble 輸入)

`extraction/inventory.json` —— 單一 JSON 物件,schema 同 `INVENTORY_PROMPT`:

```
{"overview": str,
 "environments": [{"name", "base_url", "version"|null, "source"}],
 "security_schemes": [{"name", "type"|null, "location"|null, "details"|null, "source"}],
 "endpoints": [{"method", "path", "summary", "source"}],
 "schemas": [{"name", "fields": [obj], "enums": [str], "constraints"|null, "source"}],
 "errors": [{"code", "meaning", "http_status"|null, "source"}],
 "operational": [{"topic", "detail", "source"}],
 "missing": [str]}
```

`extraction/endpoints/<id>.json` —— 每個 endpoint 一檔,schema 同 `_ENDPOINT_DETAIL_SHAPE`:

```
{"method", "path",
 "parameters": [{"name", "in": "query"|"header"|"path"|"body"|null, "type"|null, "required"|null, "description"|null}],
 "request": {"content_type"|null, "schema"|null, "required"|null, "description"|null}|null,
 "responses": [{"status", "description"|null, "schema"|null}],
 "examples": [obj], "missing": [str]}
```

所有 `source` 必須引用來源的章節/頁碼;來源未述明者一律 null 並加進 `missing`,不得臆測或套 REST/OAuth 慣例(沿用現有的來源依據原則)。

## 資料流與修正迴圈(skill 內腳本)

```
1. agent 蒐集來源:本機 Read / 公開 URL WebFetch
2. agent 依 inventory schema 輸出 → 寫 extraction/inventory.json
3. agent 對每個 endpoint 依 detail schema 輸出 → 寫 extraction/endpoints/<id>.json
4. agent 執行: uv run --project <plugin> loop-apidoc assemble --json ...
5. 讀驗證結果:
     PASS → 回報輸出路徑與摘要,結束
     FAIL → 取得結構化缺漏清單 → 回頭重讀對應來源、只補那些欄位、覆寫對應 JSON → 回到 4
   最多 N 輪(預設 3);N 輪仍 FAIL → 呈現缺漏/衝突報告給使用者,不硬編補寫
```

## 錯誤處理

- 來源讀不到 / URL 抓失敗 → agent 在擷取階段就明確列出無法取得的來源,不硬編內容。
- `assemble` 對壞掉或缺欄的 JSON → fail loudly,非零退出,訊息指出哪個檔/哪個欄位。
- 驗證的缺漏分類沿用既有 `validate` 報告結構,`--json` 輸出讓 agent 可程式化讀取。

## 測試

- `assemble` 命令:給定固定 extraction 樣本(inventory + endpoints JSON)→ 斷言輸出檔案與驗證報告;確定性、好測,走既有 pytest 風格。
- 壞 JSON / 缺欄 → 斷言 fail loudly 與非零碼。
- skill 文字:一個小型端到端範例做 smoke test(用既有 PDF 樣本)。

## 不做(YAGNI)

- 不重寫 plan/generate/validate。
- 不移除既有 `run` / `run-agent` 後端。
- 不在 skill 內重實作 OpenAPI 生成(C 選項已排除)。
- 不支援 NotebookLM / 私有網站登入(本 skill 範圍外)。
