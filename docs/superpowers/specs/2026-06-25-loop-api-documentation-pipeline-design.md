# Loop API 文件標準化 Pipeline 設計

## 1. 目標

Loop Engineering 需要一套可重複執行的 CLI pipeline，將不同格式與完整度的 API 串接文件整理成一致產物：

- OpenAPI 3.1 YAML
- 繁體中文 Markdown 串接文件
- 來源追溯資料
- 驗證與缺漏報告

系統必須以來源文件為唯一事實依據。來源未提供的資訊不得推測；必要資訊缺漏時，驗證必須失敗並明確列出缺項。

## 2. 範圍

### 2.1 第一版支援來源

- PDF
- Markdown
- Microsoft Word
- OpenAPI JSON 或 YAML
- 公開 URL

### 2.2 不在第一版範圍

- 自動登入私有網站
- 自動建立 NotebookLM Notebook
- 自動上傳來源至 NotebookLM
- 從程式碼反向推導 API
- 根據慣例補寫來源不存在的欄位
- 自動發布文件或部署 API portal

## 3. 使用者流程

### 3.1 人工前置作業

人工前置作業不屬於 CLI pipeline：

1. 使用者建立 NotebookLM Notebook。
2. 使用者將所有來源文件與公開 URL 手動加入 Notebook。
3. 使用者取得該 Notebook 的分享連結。
4. 使用者保留一份與 Notebook 內容對應的本機來源目錄。

Notebook 必須可由本機瀏覽器登入的 Google 帳號存取。若分享設定或帳號權限不足，CLI 應在 NotebookLM 預檢階段失敗。

### 3.2 CLI 自動流程

1. 接收 NotebookLM 分享連結與本機來源目錄。
2. 掃描本機來源，建立來源 manifest。
3. 檢查 NotebookLM skill、瀏覽器驗證狀態與 Notebook 可存取性。
4. 使用 NotebookLM skill 執行多輪、彼此獨立且帶完整上下文的查詢。
5. 產生來源擷取結果與規格化計畫。
6. 根據計畫產生 OpenAPI 3.1 YAML 與繁體中文 Markdown。
7. 執行結構、完整性、交叉一致性與來源追溯驗證。
8. 驗證失敗時，根據驗證報告修正並重新驗證，最多三輪。
9. 驗證通過時輸出成功報告；三輪後仍失敗時輸出缺漏／衝突報告並以非零狀態結束。

## 4. 技術方案

### 4.1 主程式

採用 Python 建立 CLI。核心流程不得直接耦合瀏覽器自動化細節，而是透過 NotebookLM adapter 呼叫指定 skill：

`https://github.com/PleasePrompto/notebooklm-skill`

該 skill 的執行契約如下：

```bash
python scripts/run.py auth_manager.py status
python scripts/run.py notebook_manager.py add ...
python scripts/run.py ask_question.py --question "..." --notebook-url "..."
```

所有 skill script 必須透過 `scripts/run.py` wrapper 執行。不可直接執行 `auth_manager.py`、`notebook_manager.py` 或 `ask_question.py`。

### 4.2 整合限制

指定的 NotebookLM skill：

- 透過本機瀏覽器自動化查詢 NotebookLM。
- 每次問題建立獨立 session，沒有對話上下文。
- 不負責建立 Notebook 或上傳來源。
- 可能受 Google 帳號、瀏覽器狀態及 NotebookLM 查詢額度影響。

因此每個 follow-up 問題必須包含 Notebook 身分、目前已知摘要、尚待確認項目與預期輸出格式，不能依賴「上一個回答」。

## 5. CLI 介面

預期主要命令：

```bash
loop-apidoc run \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --sources ./sources \
  --output ./output
```

預設值：

- 輸出語言：`zh-TW`
- 規格版本：OpenAPI 3.1
- 最大修正輪數：3
- 禁止推測：啟用

第一版可提供以下輔助命令：

```bash
loop-apidoc doctor
loop-apidoc manifest --sources ./sources
loop-apidoc validate --output ./output
```

`doctor` 檢查 Python、NotebookLM skill、skill 依賴、Chrome、驗證狀態及必要驗證工具，不修改 Notebook 或輸出文件。

## 6. 來源 Manifest

manifest 在人工上傳完成後建立，用於定義本次執行的來源基準線。它不是上傳前置程序，也不負責上傳。

每個本機來源至少記錄：

- 相對路徑
- MIME type 或文件格式
- 檔案大小
- SHA-256
- 掃描時間
- 是否受支援
- 重複檔案判定
- 處理狀態

公開 URL 由 CLI 參數或來源設定檔提供，至少記錄：

- 原始 URL
- 擷取時間
- HTTP 狀態
- 可用時的內容雜湊

Manifest 用於：

- 確認本次規格化涵蓋哪些來源。
- 發現本機漏檔、重複檔與不支援格式。
- 將輸出規格追溯至穩定來源識別碼。
- 比較後續重新執行時來源是否改變。

由於指定 skill 無法列出 Notebook 中所有來源，第一版無法自動證明 Notebook 與本機目錄逐檔完全相同。CLI 必須：

1. 要求 NotebookLM 描述它可見的來源與內容範圍。
2. 將回答與 manifest 做名稱及內容主題比對。
3. 對無法確認的來源標記 `unverified`。
4. 只要存在應納入但未確認的來源，完整性驗證不得通過。

## 7. NotebookLM 擷取與規劃

### 7.1 查詢階段

查詢採分段策略，避免要求單一回答承載全部內容：

1. Notebook 與來源盤點。
2. API 系統概覽與術語。
3. 環境、base URL 與版本。
4. 驗證、授權與簽章。
5. Endpoint 清單。
6. 逐 endpoint 的 method、path、參數、request、response 與範例。
7. 共用 schema、enum 與資料限制。
8. 錯誤碼與失敗行為。
9. rate limit、timeout、retry、idempotency 與 webhook。
10. 來源衝突、缺漏與無法確認事項。

每輪回答保存為原始擷取 artifact，不直接覆蓋或丟棄。

### 7.2 完整性追問

每個主題至少執行：

- 初始完整擷取問題。
- 針對缺欄或模糊處的 follow-up。
- 反向檢查問題，要求列出前述回答可能遺漏、衝突或沒有來源支持的內容。

若 NotebookLM 明確表示來源沒有資訊，系統必須保存為缺漏，不得繼續用引導式問題誘導其推測。

### 7.3 規格化計畫

擷取完成後先產生機器可讀計畫，再產生最終文件。計畫至少包含：

- 系統與 API 分組
- endpoint inventory
- schema inventory
- security scheme
- 錯誤模型
- 每個輸出項目的來源引用
- 缺漏項目
- 來源衝突
- 無法確認項目

只存在於計畫且具來源依據的內容，才可進入 OpenAPI 與 Markdown。

## 8. 標準化輸出

每次執行使用獨立 run directory：

```text
output/
└── <run-id>/
    ├── manifest.json
    ├── extraction/
    │   ├── queries.jsonl
    │   └── answers/
    ├── plan/
    │   └── normalization-plan.json
    ├── openapi.yaml
    ├── api-guide.zh-TW.md
    ├── provenance.json
    └── validation/
        ├── report.json
        └── report.md
```

### 8.1 OpenAPI 3.1

`openapi.yaml` 至少遵守：

- `openapi: 3.1.x`
- API 資訊與 server 只在來源存在時填入
- endpoint operation 與 parameter 使用原始 API 名稱
- request／response schema 使用明確型別與 required 規則
- security scheme 只根據來源建立
- 未知值不得以常見慣例補全

OpenAPI 必填但來源缺失的欄位，應使用最小合法占位描述，並透過明確的 `x-loop-status: missing-source` 及 provenance 記錄缺漏。若該缺漏影響可串接性，完整性驗證仍須失敗。

### 8.2 繁體中文 Markdown

`api-guide.zh-TW.md` 至少包含：

- 文件範圍與來源
- 串接前置條件
- 環境與 base URL
- 驗證／授權
- 共用規則
- Endpoint 章節
- Request／response 範例
- 錯誤碼
- 限制與注意事項
- 已知缺漏與來源衝突

敘述採繁體中文；API path、欄位、enum、header、query parameter 與程式碼範例保留原始名稱。

### 8.3 來源追溯

`provenance.json` 將標準化項目映射至：

- manifest source ID
- NotebookLM 查詢 ID
- NotebookLM 回答 artifact
- 來源提供的章節、頁碼、URL 或可辨識定位資訊
- 狀態：`supported`、`conflicting`、`missing` 或 `unverified`

NotebookLM 回答本身不是獨立事實來源；它是對已上傳來源的整理層。最終狀態仍需連回 manifest 中的來源。

## 9. 驗證

### 9.1 結構驗證

- OpenAPI 3.1 schema 合法。
- YAML 可解析。
- `$ref` 均可解析。
- Markdown 必要章節存在。
- JSON artifacts 符合各自 schema。

### 9.2 完整性驗證

每個 endpoint 至少檢查：

- HTTP method
- path
- operation 說明
- authentication 要求或明確標示來源未提供
- request parameter／body
- response status 與 schema
- 錯誤行為
- 來源追溯

若來源本來未提供其中一項，必須記錄為缺漏；會影響串接的缺漏使驗證失敗。

### 9.3 一致性驗證

- Markdown 與 OpenAPI endpoint inventory 一致。
- method、path、欄位名稱、型別、required、enum 和狀態碼一致。
- 共用 schema 引用一致。
- 同一資訊在來源間衝突時不得任選其一而不揭露。

### 9.4 禁止推測驗證

任何規格欄位都必須存在 `supported` provenance。以下狀況視為失敗：

- 無來源映射。
- 來源只表達不確定資訊，但輸出寫成確定事實。
- 根據 REST、OAuth 或產業慣例自行補值。
- 將範例值誤寫為完整 enum 或固定限制。

### 9.5 執行結果

驗證報告採穩定 issue code，例如：

- `SOURCE_UNVERIFIED`
- `REQUIRED_INFO_MISSING`
- `SOURCE_CONFLICT`
- `OPENAPI_INVALID`
- `OUTPUT_MISMATCH`
- `UNSUPPORTED_ASSERTION`

所有 issue 包含嚴重度、位置、證據、建議修正及是否可由 pipeline 自動修正。

## 10. 修正循環

最大修正輪數為三輪。每輪流程：

1. 讀取上一輪驗證報告。
2. 將問題分成：
   - 轉換或格式錯誤：可自動修正。
   - 擷取不足：可追加 NotebookLM 查詢。
   - 來源缺漏或衝突：不可推測修正。
3. 僅處理可修正問題。
4. 重新生成受影響產物。
5. 執行完整驗證，不只執行失敗項目。

輪數定義為首次生成後最多三次修正嘗試。若任一輪驗證通過，立即停止。若第三次修正後仍失敗：

- 保留所有中間 artifact。
- 輸出最終缺漏／衝突報告。
- CLI 以非零 exit code 結束。
- 不得將文件標記為完成。

若剩餘問題全部屬於來源缺漏或衝突，系統可提前停止，不浪費 NotebookLM 額度。

## 11. 錯誤處理與安全

- NotebookLM 未驗證：停止並提供登入指示。
- Notebook 無法存取：停止，不進入規格化。
- 查詢額度或暫時錯誤：有限次技術重試，與三輪內容修正分開計數。
- skill 輸出格式異常：保存 stdout／stderr，停止該次執行。
- 不支援檔案：加入 manifest issue，不靜默略過。
- 機密資料：輸出及 log 不應保存 Google cookie、browser state 或憑證。
- skill 的 `data/`、`.venv/` 與瀏覽器狀態不得複製至專案或提交 Git。

## 12. 測試策略

### 12.1 單元測試

- manifest 建立與雜湊
- 支援格式辨識
- NotebookLM adapter command 建構與輸出解析
- normalization plan schema
- provenance 規則
- validator issue code
- retry 與停止條件

### 12.2 整合測試

- 使用 fixture 模擬 NotebookLM 回答，不消耗真實額度。
- 從 manifest、擷取結果到 OpenAPI／Markdown 的完整生成。
- 故意缺漏、衝突與不一致案例。
- 三輪修正成功、提前停止及最終失敗。

### 12.3 真實 smoke test

使用不含機密資訊的小型測試 Notebook：

- 驗證 skill 認證與查詢。
- 驗證獨立 session 問題包含足夠上下文。
- 驗證產物可通過 OpenAPI 與內部完整性檢查。

真實 smoke test 需由明確命令觸發，不納入一般單元測試。

## 13. 完成條件

第一版完成須同時符合：

- 可由單一 CLI 命令執行完整自動流程。
- 支援指定的五類來源基準。
- 使用指定 `PleasePrompto/notebooklm-skill` 查詢 Notebook。
- 產生 OpenAPI 3.1、繁中 Markdown、manifest、plan、provenance 與驗證報告。
- 任何無來源支持的內容都無法通過驗證。
- 修正循環最多三次且停止行為可測試。
- 成功執行 exit code 為 0；未解決缺漏、衝突或無來源內容時為非零。

## 14. 已知限制

- 人工上傳是否完整無法由指定 skill 直接逐檔驗證，只能透過 manifest 與 NotebookLM 回答交叉確認。
- NotebookLM skill 透過非官方瀏覽器自動化，可能因 NotebookLM UI 變更失效。
- NotebookLM 回答可能缺少精確頁碼或來源定位，必須保留 `unverified` 狀態而非假造引用。
- Google 登入與 NotebookLM 額度使真實端對端測試無法完全在無人值守 CI 中執行。
