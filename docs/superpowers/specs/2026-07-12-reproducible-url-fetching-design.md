# 設計文件：可重現、可退回的 URL 內容擷取

## 1. 背景與目標

目前公開 URL 的正文擷取由 agent 依 SOP 使用 defuddle 或 Playwright 完成；Python
pipeline 只探測 URL、記錄 HTTP status 與 response hash，再信任 agent 撰寫的
`coverage.json`。這使抓取、品質判斷與完成宣告集中於同一個 agent，無法可靠區分：

- 原始來源本來就沒有需要的內容；
- 靜態 HTTP 只抓到 SPA 空殼；
- 正文抽取器遺失 table、tab、code block 等結構；
- 來源需要登入或瀏覽器互動；
- agent 漏抓頁面或過早認定內容完整。

本設計新增可復用的 CLI 與 Python library。工具負責受限下載、保存原始證據、雙層
正文抽取、客觀品質量測與 deterministic 裁決；agent 負責建立預期頁面清單、提出
語意需求，以及在工具要求時升級到 Playwright 或請使用者處理缺口。

第一版採 **HTTP 雙層擷取**，不內建 browser runtime。明確技術異常由工具自動
fallback；分析階段發現語意缺口時，可要求針對相同 URL 建立新的 HTTP attempt。
必要 URL 未獲接受時，pipeline 預設 fail-closed。

## 2. 設計原則

1. **證據優先**：任何完成結論都能回溯到 raw response、抽取結果、metrics 與 hash。
2. **Attempt 不可變**：重抓建立新 attempt，不覆蓋既有證據。
3. **抓取與裁決分離**：transport 不判斷品質，extractor 不碰網路，evaluator 不修改 artifact。
4. **混合升級**：技術空殼自動 fallback；語意缺口由分析階段提出結構化 retry request。
5. **Fail-closed**：未解決的必要來源不得由 agent 自行降級成成功。
6. **安全預設**：只允許公開 HTTP(S)，每次 redirect 都重新驗證目的地。
7. **有限重試**：相同證據與相同策略不得無限重跑。

## 3. 公開介面

Python API：

```python
fetch_url(request: FetchRequest) -> FetchRun
evaluate_fetch(run: FetchRun, requirements: ContentRequirements) -> FetchVerdict
```

CLI：

```bash
# 首次抓取；明確空殼會自動執行 conservative fallback
loop-apidoc fetch-url --url URL --work WORK [--json]

# 分析發現語意缺口後，重新抓取並建立新 attempt
loop-apidoc fetch-url --url URL --work WORK \
  --retry-from FETCH_JSON \
  --requirements REQUIREMENTS_JSON [--json]

# 不發網路請求，只重新評估現有 artifact
loop-apidoc evaluate-url \
  --fetch-run FETCH_JSON \
  --requirements REQUIREMENTS_JSON [--json]

# 檢查 expected、artifact、coverage 與接受狀態
loop-apidoc verify-url-sources \
  --expected EXPECTED_JSON \
  --work WORK [--json]

# 匯入由 agent／MCP 取得的瀏覽器渲染 HTML
loop-apidoc import-rendered-url \
  --fetch-run FETCH_JSON \
  --url URL \
  --html RENDERED_HTML [--json]
```

CLI 的人類輸出保持簡短；`--json` 是具 schema version 的穩定 agent 介面。程式或
輸入錯誤、擷取未通過裁決、成功三者必須使用可區分的 exit code。

## 4. 資料流與升級狀態機

```text
安全檢查
  -> HTTP fetch + 保存 raw response
  -> primary main-content extraction
       | 技術正常 -> semantic evaluation
       | 明確異常 -> conservative DOM-to-Markdown
                          -> semantic evaluation
                               | 足夠 -> accepted
                               | 暫態網路結果 -> retry_http
                               | SPA／互動內容 -> requires_rendering
                               | 登入限制 -> auth_required
                               | 原始來源確實缺少 -> source_incomplete
```

第二層抽取使用同一份 raw HTML，不重新發 HTTP，避免把來源變動誤判為 extractor
差異。只有明確 retry 或可重試網路失敗才建立新的 HTTP attempt。

分析階段不得只回報「內容很少」，而要提供結構化需求：

```json
{
  "schema_version": 1,
  "url": "https://docs.example.com/api/payment",
  "required_evidence": [
    "request parameters",
    "response fields",
    "error codes"
  ],
  "observed_gap": [
    "頁面提到 request parameters，但目前快照沒有參數表"
  ],
  "retry_reason": "possible_extraction_loss"
}
```

裁決值為：

- `accepted`
- `retry_http`
- `requires_rendering`
- `source_incomplete`
- `auth_required`

除 `accepted` 或具有效使用者缺口接受紀錄外，其餘狀態都阻擋 pipeline。

## 5. Artifact 模型

每個 normalized URL 使用穩定 ID 建立目錄：

```text
<WORK>/url_sources/<url-id>/
├── fetch.json
├── attempts/
│   ├── 001/
│   │   ├── request.json
│   │   ├── response.json
│   │   ├── raw.html
│   │   ├── extracted.md
│   │   ├── conservative.md        # 有 fallback 才存在
│   │   ├── metrics.json
│   │   └── verdict.json
│   └── 002/
│       └── ...
└── accepted.json                  # 有被接受的 extraction 才存在
```

`fetch.json` 是索引，不複製正文：

```json
{
  "schema_version": 1,
  "requested_url": "https://docs.example.com/api",
  "attempts": ["attempts/001", "attempts/002"],
  "current_attempt": "attempts/002",
  "status": "requires_rendering"
}
```

### 5.1 不可變與完整性規則

- 已完成 attempt 不得覆寫。
- 每次重新發 HTTP 才建立新 attempt。
- 相同 raw HTML 的兩種 extractor 結果存於同一 attempt。
- raw response 與衍生檔案都記錄 SHA-256。
- `accepted.json` 只引用選定的 attempt 與 extraction，不複製或修改檔案。
- artifact 寫入採暫存後 atomic rename；部分寫入不得形成有效 attempt。
- schema、hash 或引用驗證失敗時 fail loudly。

### 5.2 Request／response metadata

允許保存：requested URL、final URL、redirect chain、method、status、content type、
安全 response headers 白名單、byte count、時間、hash、timeout、截斷與網路錯誤。

禁止保存：Authorization、cookies、proxy credentials、URL userinfo 與敏感 request
headers。query 在 log 與 artifact 中依 key policy 遮蔽 token、key、signature 等值；
另存完整請求 URL 的不可逆 hash 供同一性比對。

## 6. URL 與網路安全

預設只允許公開網路：

- scheme 僅限 HTTP／HTTPS；
- 拒絕 URL userinfo；
- DNS 的所有解析結果都必須通過檢查；
- 拒絕 loopback、private、link-local、multicast、reserved、unspecified IP；
- 明確拒絕常見 cloud metadata endpoint；
- 每一次 redirect 都重新解析並驗證目的 host/IP；
- 限制 redirect 次數、response bytes、連線及總 timeout；
- DNS resolve 與實際 connection 必須避免 TOCTOU／DNS rebinding；具體 transport 實作
  必須將通過驗證的位址綁定到該次連線，或採等價的安全機制。

第一版不允許內網。未來若要支援企業內網，必須另行設計明確 allowlist，不能以關閉
全域安全檢查達成。

## 7. 雙層正文抽取

抽取器採 adapter 介面並回傳統一 `ExtractionResult`。

### 7.1 Primary

使用成熟的 Python main-content extractor，目的為移除 nav/footer/廣告並保留主要正文。
具體套件在實作計畫前依官方／上游文件評估，不在設計階段鎖定。

### 7.2 Conservative fallback

從相同 DOM 保守轉換 Markdown，至少保留：

- heading、paragraph；
- ordered/unordered list；
- table；
- pre/code；
- definition list；
- link 與可見 anchor text。

它不追求只留下主文，而是降低 API 文件結構被 main-content heuristic 刪除的風險。

## 8. 技術品質量測

不以單一模糊總分裁決，而輸出具 evidence 的 signals：

- HTTP status、content type、response bytes；
- app root、loading、skeleton、noscript 等空殼特徵；
- raw HTML 與抽取文字比例；
- title、heading、paragraph、table、list、code block 數量；
- 導覽連結規模與正文規模的不合理差距；
- HTML 存在大量 table/code，但 Markdown 完全遺失；
- response 是否被截斷；
- login、WAF、CAPTCHA、consent 或錯誤頁特徵；
- primary 與 conservative 的文字及結構差異。

範例：

```json
{
  "schema_version": 1,
  "technical_status": "suspect",
  "signals": [
    {
      "code": "EXTRACTION_LOST_TABLES",
      "severity": "error",
      "evidence": {
        "html_tables": 8,
        "markdown_tables": 0
      }
    }
  ]
}
```

品質門檻集中於具版本的 policy，不散落在 agent prompt。policy 版本寫入每個 attempt，
確保相同證據可重現相同裁決。

## 9. 語意完整性與「來源真的缺少」判斷

evaluator 結合結構化 `ContentRequirements`、raw HTML metrics 與兩種 extraction：

- raw HTML 有對應文字、table、code 或 tab 結構但 Markdown 遺失：要求 extraction retry／fallback；
- raw response 為 SPA shell：`requires_rendering`；
- raw response 為登入或防護頁：`auth_required`；
- 不同 HTTP attempts 顯著不同：保留差異並要求重新裁決；
- raw HTML 與兩種 extraction 都沒有所需證據，且不存在空殼、截斷、登入或互動訊號：
  才能裁決 `source_incomplete`；
- 機械證據無法分辨時，不得宣稱來源缺少，改為 `requires_rendering` 或人工確認。

這項制度只能證明「在已取得的 representation 中找不到」，不能對未執行的瀏覽器互動
做無證據推論。因此任何 SPA／tab／lazy-load 疑慮必須先走 rendered attempt。

## 10. 重試限制

- 自動 HTTP retry 只處理 timeout、連線中斷、429 與明確可重試的部分 5xx，採有限 backoff。
- 分析退回預設最多新增一次 HTTP attempt。
- 相同 raw SHA-256、extractor 版本及 policy version 不得重複處理。
- 第二次仍不足時必須升級 Playwright、人工確認或由使用者接受缺口。
- retry budget 與停止原因寫入 verdict，不由 agent 自由延長。

## 11. Coverage 與使用者缺口接受

agent 仍建立 `expected` URL 清單；`results` 改由工具根據 artifact 產生，不能手寫成功：

```json
{
  "url": "https://docs.example.com/api",
  "status": "requires_rendering",
  "artifact": "url_sources/<url-id>/fetch.json",
  "accepted_file": null,
  "attempt_count": 2,
  "user_override": null
}
```

若來源確實不完整，使用者可明確接受特定缺口。這是 elevated action，agent 不得自行
執行；CLI 必須要求可稽核的 reason，並記錄時間、artifact hash 與當時 verdict。
接受缺口只解除 pipeline 阻擋，不會把狀態改寫成內容完整；preparation、provenance 與
validation report 仍須揭露。

## 12. Pipeline 整合

1. `manifest --url` 引用已存在的 fetch artifact，不再為 hash 重複下載整份 response。
2. skill 先建立 expected URL 清單，再逐頁呼叫 `fetch-url`。
3. extraction 只讀 `accepted.json` 指向的 Markdown。
4. `verify-extraction` 驗證 URL source 引用對應有效 accepted artifact。
5. `assemble` 執行 `verify-url-sources`；缺頁、未接受或 artifact 損壞直接 exit 2。
6. 使用者接受的缺口可繼續，但必須進入 preparation、provenance 與 validation report。
7. 現有 `coverage.json` 提供明確、有限的相容期：舊格式可讀並產生 deprecated
   warning，但不能被視為新制已驗證 artifact。

既有 `fetch_failed`、`empty_suspect` 與 missing coverage 在新制改為阻擋條件。頁面
是否不重要，必須在 expected URL 確認階段排除，不能由 agent 在抓取失敗後自行降級。

## 13. Playwright 交接

第一版不內建 Playwright。當 verdict 是 `requires_rendering` 時，agent/MCP 抓取 rendered
HTML，再透過 `import-rendered-url` 匯入為新 attempt。匯入內容接受相同 schema、hash、
extractor 與 evaluator 檢查，不能直接標記 accepted。

登入流程仍遵守現有紅線：工具與 agent 不接收或保存 credentials；需要登入時由使用者
在瀏覽器親自操作，或另存 HTML/PDF 作為本地來源。

## 14. 元件切分

```text
loop_apidoc/urlfetch/
├── models.py       # request、attempt、metrics、verdict schema
├── policy.py       # timeout、大小、安全與品質門檻
├── safety.py       # URL、DNS、redirect、IP 範圍檢查
├── transport.py    # 受限制的 httpx streaming fetch
├── artifacts.py    # 不可變 attempt 與 hash 寫入／驗證
├── extract.py      # primary、conservative adapters
├── inspect.py      # HTML／Markdown 客觀結構量測
├── evaluate.py     # signals 與狀態機裁決
└── coverage.py     # 從 artifact 產生 coverage results
```

每個模組只暴露小型具型別介面。第三方 extractor 被 adapter 隔離，未來替換實作不應
改變 artifact 或 CLI contract。

## 15. 錯誤處理

- 不合法 URL、安全拒絕、artifact schema/hash 錯誤：fail loudly，不建立有效 attempt。
- HTTP/network failure：寫入完整但失敗的 attempt，依 policy 決定有限 retry。
- extractor exception：保存 raw evidence 與錯誤類型，不保存 stack trace 中可能的敏感內容。
- disk full／partial write：atomic write 回滾，索引不引用不完整 attempt。
- evaluator 無法裁決：使用保守狀態 `requires_rendering`，不預設 accepted。

## 16. 測試策略

### 16.1 單元測試

- Safety：IPv4/IPv6、DNS 多結果、redirect 轉內網、userinfo、非 HTTP scheme、metadata IP。
- Transport：timeout、redirect loop、429/5xx retry、大小上限、截斷與敏感資料遮蔽。
- Extractor fixtures：一般文章、API table、code sample、SPA shell、登入頁、空頁及困難 DOM。
- Evaluator：每個 signal、狀態轉移、相同 hash 防重試與 retry budget。
- Artifacts：不可覆寫、hash tamper、schema version、atomic write failure。

### 16.2 整合測試

- accepted URL 正常進入 extraction/assemble；
- requires-rendering、缺頁、壞 artifact 確實阻擋；
- 分析 requirements 能觸發一次新 attempt；
- rendered HTML 匯入後仍需通過 evaluator；
- 使用者接受缺口後可繼續且報告保留缺口；
- 舊 coverage 相容期行為明確；
- 既有 manifest、preparation、assemble 與 URL snapshot 測試全部維持通過。

所有 CI 網頁案例使用固定 fixtures 與 mock transport，不依賴外網；另提供非 CI 的人工
live smoke command 驗證真實站點。

## 17. 完成標準

第一版必須以自動測試與固定 fixtures 證明：

1. agent 無法只填 JSON 宣稱抓取成功；
2. primary 遺失 table/code 時會自動執行 conservative fallback；
3. 分析階段能提交結構化缺口並觸發一次新 HTTP attempt；
4. evaluator 能區分 extraction loss、SPA shell、auth gate 與來源本身缺少內容；
5. 未解決的必要 URL 確實阻擋 assemble；
6. 公開 URL redirect 到非公開位址會被拒絕；
7. 所有完成結論可回溯到 raw response、抽取產物、metrics、policy version 與 hash；
8. Playwright 匯入結果走相同的證據與裁決流程；
9. 使用者接受缺口不會被呈現成來源完整。

## 18. 不在第一版範圍

- 內建 Playwright/browser runtime；
- 通用全站 crawler 或無界深度連結追蹤；
- 企業內網 allowlist；
- credentials、cookie 或 token 自動化；
- 由 agent 自動接受來源缺口；
- 以 LLM 主觀分數取代 deterministic signals。
