---
name: loop-apidoc
description: 從一或多個 API 文檔來源(本機 PDF/MD/HTML 或公開 URL)產出標準化的 OpenAPI 3.1 + 繁中 Markdown 串接文件。由 agent 擷取、呼叫確定性 CLI 組裝與驗證,驗證失敗時自動回頭補齊缺漏。當使用者要把雜亂的 API 串接文件整理成一致、可追溯的規格時使用。
---

# loop-apidoc:來源依據式 API 文件產生

你要把使用者提供的 API 文檔來源,整理成標準化、可追溯的產物。**唯一事實依據是來源**:來源沒寫的一律 `null` 並記入 `missing`,**絕不臆測、絕不套用 REST/OAuth 慣例**。

CLI 以本 plugin 內含的套件執行,一律用:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc <command> ...
```

## 流程

### 1. 蒐集來源
- 本機檔案(PDF/MD/HTML):用 Read 直接讀。
- 公開 URL:用 WebFetch 或 defuddle 抓成文字。
- 把本機來源目錄記為 `<SOURCES>`(供 manifest/provenance 用);URL 用 `--url` 傳入。

### 2. 擷取 inventory → 寫 `<WORK>/inventory.json`
讀完所有來源後,輸出**一個** JSON 物件(嚴格依來源填寫),schema:

```json
{"overview": "str",
 "environments": [{"name":"str","base_url":"str","version":"str|null","source":"str"}],
 "security_schemes": [{"name":"str","type":"str|null","location":"str|null","details":"str|null","source":"str"}],
 "endpoints": [{"method":"str","path":"str","summary":"str","source":"str"}],
 "schemas": [{"name":"str","fields":[{}],"enums":["str"],"constraints":"str|null","source":"str"}],
 "errors": [{"code":"str","meaning":"str","http_status":"str|null","source":"str"}],
 "operational": [{"topic":"str","detail":"str","source":"str"}],
 "missing": ["str"]}
```
包含**每一個** endpoint 與**每一個** error code。每個 `source` 引用來源章節/頁碼。

### 3. 擷取每個 endpoint 細節 → 寫 `<WORK>/endpoints/<NN>.json`
對 inventory.endpoints 的**每一個** endpoint,各輸出一個 JSON 檔(`ep0.json`, `ep1.json`, …),schema:

```json
{"method":"str","path":"str","source":"str",
 "parameters":[{"name":"str","in":"query|header|path|body|null","type":"str|null","required":"bool|null","description":"str|null"}],
 "request":{"content_type":"str|null","schema":"str|null","required":"bool|null","description":"str|null"} ,
 "responses":[{"status":"str","description":"str|null","schema":"str|null"}],
 "examples":[{}],"missing":["str"]}
```
`request` 無內容時為 `null`。來源沒寫的填 null/空陣列並加進 `missing`。
頂層 `source` 必填,引用此 endpoint 細節所在的來源章節/頁碼/URL(與 inventory.endpoints 的對應 `source` 一致)。**多來源時這是把細節歸屬到正確來源的唯一依據**:漏填會被判 `SOURCE_UNVERIFIED`。

### 4. 組裝 + 驗證
```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc assemble \
  --sources "<SOURCES>" --extraction "<WORK>" --output "<OUT>" --json
```
解析 stdout 的 JSON:`ok`、`run_dir`、`report.issues`。

### 5. 修正迴圈(最多 3 輪)
- `ok == true` → 回報 `run_dir` 內的 `openapi.yaml` / `api-guide.zh-TW.md` / `provenance.json` / `validation/report.md`,結束。
- `ok == false` → 看 `report.issues`(每筆有 `code`/`severity`/`location`/`evidence`/`suggested_fix`),依 `location` 與 `evidence` 判斷哪個欄位缺漏或有問題,**只針對那些欄位回頭重讀對應來源**,覆寫 `inventory.json` 或對應的 `endpoints/<NN>.json`,然後回到步驟 4。
- 連續 3 輪仍 FAIL → 把剩餘的缺漏/衝突清單呈現給使用者,**不要硬編補寫**。

## 重要
- `<WORK>` 用一個工作目錄(可放在 `<OUT>` 之外的暫存區)。
- 每輪覆寫同一份 `inventory.json` / `endpoints/*.json` 再重跑 assemble。
- 退出碼:0=PASS、1=驗證 FAIL、2=擷取輸入檔錯誤(修正你寫出的 JSON)。
