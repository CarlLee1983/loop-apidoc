# Benchmark Validation Plan

本計劃用來建立 `loop-apidoc` 的文件樣本驗證集。目標不是「訓練模型」,而是用可重跑的公開文件樣本檢查整條流程是否能穩定產出足夠後續開發使用的 OpenAPI、整合契約、範例程式與來源追溯。

## 目標

- 建立 5-8 組官方或可公開取得的 API 文件樣本。
- 每組樣本都能重跑 `preprocess`(需要時)、agent 擷取、`assemble`、`validate`。
- 用固定驗收標準判斷產物是否足以支援後續生成 SDK、client package、server stub、integration module 或測試骨架。
- 找出流程盲點:擷取 prompt、`integration.json` schema、OpenAPI 生成、範例程式、驗證規則或文件說明。

## 樣本來源優先順序

### 第一輪:最小有效樣本集

先收 5 份,每份代表一種風險面。

| 順序 | 文件類型 | 建議來源 | 驗證目的 |
| --- | --- | --- | --- |
| 1 | 台灣金流簽章文件 | NewebPay API 文件下載: `https://www.newebpay.com/website/Page/content/download_api` | AES / SHA / HashKey / HashIV / callback / 交易查詢 |
| 2 | 標準支付 REST 文件 | LINE Pay Online API: `https://developers-pay.line.me/online-api-v3` | REST payment flow、confirm、refund、callback |
| 3 | Backend payment API | TapPay Backend API: `https://docs.tappaysdk.com/tutorial/en/back.html` | backend payment request/response、付款方式差異 |
| 4 | 高品質國際 REST 文件 | Stripe API Reference: `https://docs.stripe.com/api` | 標準 REST、auth、request/response、error handling |
| 5 | Machine-readable baseline | APIs.guru OpenAPI Directory: `https://github.com/APIs-guru/openapi-directory` | 對照既有 OpenAPI 規格,檢查 schema/operation 基準 |

### 第二輪:擴充覆蓋 — ✅ 完成(5/5 類,2026-06-29)

第一輪穩定後再補 3-5 份。五類覆蓋全數完成。

| 類型 | 對應 case | 驗證目的 | 狀態 |
| --- | --- | --- | --- |
| 表格密集 PDF | `ecpay-creditcard-pdf` | PDF `preprocess`、欄位表、錯誤碼表 | ✅ PASS(修純簽章 auth 誤判) |
| callback / webhook 文件 | `github-webhooks` | async flow、驗簽、重送規則 | ✅ PASS(修多 webhook 同源碰撞) |
| 多產品共用 endpoint | `adyen-payments-multimethod` | endpoint merge、operationId、文件可讀性 | ✅ PASS(`POST /payments` oneOf discriminator,首跑 0 error) |
| 文件不完整案例 | `paypal-webhooks-incomplete` | fail-closed、missing、conflict、provenance | 🟥 EXPECTED_FAIL(SOURCE_UNVERIFIED 正確擋下越界 schema) |
| 大型企業 API | `cybersource-payments` | 大型文件、複雜 schema、範例產出壓力測試 | ✅ PASS(18 schema/40+ 欄位,首跑 0 error) |

> 來源型態:PDF(綠界 V5.6.1)/ WebFetch HTML(GitHub webhooks)/ 官方 OpenAPI curl(Adyen Checkout v71)/ 官方頁(PayPal,刻意不完整)/ SDK codegen md(CyberSource)。原始 `sources/` gitignore,只入庫 `extraction/` + `expected/` + `notes.md`。

## 目錄結構

每份樣本建立一個獨立 case。來源文件可以是 PDF、markdown、HTML 擷取後保存的文字,或官方 OpenAPI 檔。

```text
benchmarks/
└── <case-id>/
    ├── sources/
    │   └── <official-source-files>
    ├── extraction/
    │   ├── inventory.json
    │   ├── endpoints/
    │   │   ├── ep000.json
    │   │   └── ep001.json
    │   └── integration.json        # 選填:來源有簽章、加密、callback、條件規則時必須有
    ├── expected/
    │   ├── minimum.json            # 此 case 至少必須抽到的重點
    │   └── validation.expect.json  # 預期 PASS/FAIL 與必要 issue 類型
    ├── output/                     # 實際跑 assemble 後產生,可 gitignore
    └── notes.md                    # 來源網址、下載日期、觀察、缺漏、決策
```

建議 `case-id` 用穩定命名,例如:

- `newebpay-mpg`
- `line-pay-online-v3`
- `tappay-backend`
- `stripe-basic-rest`
- `apis-guru-baseline`

## 每個 Case 的 `minimum.json`

`minimum.json` 不需要比對完整輸出,只記錄「這份文件至少應該支援開發的資訊」。

```json
{
  "must_have": {
    "base_urls": 1,
    "endpoints_min": 3,
    "schemas_min": 1,
    "error_codes_min": 1,
    "examples": true,
    "provenance": true
  },
  "integration": {
    "required": true,
    "crypto_required": true,
    "callbacks_required": true,
    "field_conditions_min": 1,
    "test_cases_min": 1
  },
  "critical_operations": [
    "paths./pay.post",
    "paths./pay/notify.post"
  ]
}
```

## 執行流程

### 1. 收集來源

- 優先使用官方文件、官方 PDF、官方 API reference。
- 記錄來源 URL、下載日期、文件版本。
- 若文件是 HTML,保存原始 URL 與當次擷取內容。
- 避免用部落格或非官方教學當主 benchmark;它們可作為輔助參考,但不能作為來源真相。

### 2. 前處理

PDF 或表格密集文件先轉 markdown。

```bash
uv run loop-apidoc preprocess \
  --sources benchmarks/<case-id>/sources \
  --out benchmarks/<case-id>/work/sources_md
```

文字或 markdown 來源可直接進入擷取流程。

### 3. Agent 擷取

依 `skills/loop-apidoc/SKILL.md` 讓 Claude Code 或 Codex 讀來源,產出:

- `benchmarks/<case-id>/extraction/inventory.json`
- `benchmarks/<case-id>/extraction/endpoints/*.json`
- `benchmarks/<case-id>/extraction/integration.json`(來源有簽章/加密/callback/欄位條件時)

擷取原則:

- 不從常識補欄位。
- 每個重要項目都要有 `source`。
- 無法確認的資訊放進 `missing`。
- 來源互相矛盾時標 conflict,不要自行裁決。

### 4. 組裝與驗證

```bash
uv run loop-apidoc assemble \
  --sources benchmarks/<case-id>/sources \
  --extraction benchmarks/<case-id>/extraction \
  --output benchmarks/<case-id>/output \
  --json
```

取得 `run_dir` 後再跑一次 validate:

```bash
uv run loop-apidoc validate --output <run_dir>
```

### 5. 產物檢查

每個 case 至少檢查這些檔案:

- `openapi.yaml`
- `api-guide.zh-TW.md`
- `provenance.json`
- `plan/normalization-plan.json`
- `validation/report.json`
- `integration-contract.json`(來源有整合機制時)
- `examples/`(有 endpoint 可產生範例時)

## 驗收標準

### PASS 條件

一個 case 可視為通過,需同時滿足:

- `assemble --json` 回傳 `ok: true`,或在預期缺漏 case 中回傳預期 issue。
- `openapi.yaml` 可被驗證器接受。
- endpoint、schema、security、server 至少符合 `expected/minimum.json`。
- `provenance.json` 能追到核心 endpoint、schema、security、integration contract 的來源。
- 若來源有簽章/加密/callback,必須有 `integration-contract.json`。
- `examples/` 有足夠資訊讓工程師或 agent 改成可執行 request。
- 缺漏資訊被標成 missing/issue,沒有被硬補成看似確定的內容。

### FAIL 條件

任一情況需要記錄為 fail 或需要修正:

- `assemble` crash 或輸出非預期格式。
- OpenAPI invalid。
- 明確存在於來源的 endpoint/schema/error code 未被抽到。
- 簽章/加密訊號存在,但沒有產出 `integration.json` 或 validation 沒有報缺漏。
- 範例程式宣稱可跑,但缺少來源必要資訊。
- provenance 缺核心項目來源。
- validation 沒有抓出明顯 unverified/conflict/missing。

## 產物是否足夠支援後續開發

每個 case 跑完後,用以下問題評分:

| 問題 | 標準 |
| --- | --- |
| OpenAPI 是否能生成 client/server stub? | endpoint、method、path、requestBody、responses、schemas 足夠 |
| 型別是否足夠? | request/response 欄位、required、enum、巢狀結構可用 |
| 整合機制是否足夠? | `integration-contract.json` 說清楚簽章/加密/callback/條件欄位 |
| 範例是否有幫助? | curl / TypeScript / Python 能作為可修改起點 |
| 來源是否可追? | `provenance.json` 能定位核心輸出來源 |
| 缺漏是否透明? | 不確定資訊進 missing/issue,沒有被猜測 |

若大多數答案為「是」,該 case 代表產物足以支援快速生成 SDK、套件或應用整合層。若目標是 production-ready app,仍需再補商業流程、金鑰管理、部署、真實 sandbox 測試與監控。

## 紀錄模板

每個 `notes.md` 建議使用以下格式:

```markdown
# <case-id>

## Source

- Official URL:
- Downloaded at:
- Document version:
- Source format: PDF / HTML / Markdown / OpenAPI

## Scope

- Included:
- Excluded:

## Expected Coverage

- Base URLs:
- Critical endpoints:
- Auth/signing:
- Callback/webhook:
- Error codes:

## Run Log

- preprocess:
- assemble:
- validate:
- run_dir:

## Result

- Status: PASS / EXPECTED_FAIL / FAIL
- Issues:
- Missing source info:
- False positives:
- False negatives:

## Follow-up

- Extraction prompt changes:
- Schema/contract changes:
- Generator changes:
- Validator changes:
- Documentation changes:
```

## 第一輪執行清單

1. 建立 `benchmarks/newebpay-mpg/`,下載 NewebPay MPG 或交易相關官方文件。
2. 建立 `benchmarks/line-pay-online-v3/`,保存 LINE Pay Online API v3 來源。
3. 建立 `benchmarks/tappay-backend/`,保存 TapPay Backend API 來源。
4. 建立 `benchmarks/stripe-basic-rest/`,挑 3-5 個 Stripe 基本 endpoint 當高品質 REST 對照。
5. 建立 `benchmarks/apis-guru-baseline/`,挑一份小型 OpenAPI 當 machine-readable baseline。
6. 逐一跑 preprocess(必要時)、agent 擷取、assemble、validate。
7. 每跑完一份,更新 `notes.md`,不要等全部跑完才回顧。
8. 三份以上完成後,整理共通問題,再決定要優先修擷取 prompt、contract schema、examples generator 或 validator。

## 停止條件

第一輪完成後,若以下條件成立,即可進入下一階段功能補強:

- 至少 3 份 case 可穩定 PASS。
- 至少 1 份金流簽章 case 產出 `integration-contract.json` 與 request examples。
- 至少 1 份缺漏/不完整 case 能正確 fail-closed。
- 已整理出前 3 個最影響「生成可開發套件/應用」的缺口。

## 執行結果(兩輪完結)

### 第一輪 — ✅ 完成(5/5 PASS)

`newebpay-mpg`(台灣金流簽章 PDF)、`line-pay-online-v3`(HMAC REST)、`tappay-backend`
(backend payment)、`stripe-basic-rest`(高品質 REST)、`apis-guru-baseline`
(machine-readable)全數 PASS。初跑揭出並修復 **9 項 pipeline 缺陷**(簽章接回
false-positive、AES 模板硬接 SHA256、簽章 payload 選錯欄位、webhook 強制 responses、
schemas.fields 中文 key 遺失 type、公開 API no-auth 誤判、payload_ref 未 sanitize、
http securityScheme 缺 scheme 等),全數 TDD。

### 第二輪 — ✅ 完成(5/5 類)

見上方「第二輪:擴充覆蓋」表。4 PASS + 1 EXPECTED_FAIL,新增修復 **3 項 pipeline 缺陷**
(多 webhook 同源碰撞、webhook_name 切分、純簽章 auth 誤判),`adyen` 與 `cybersource`
首跑即 0 error(pipeline 已成熟,未揭新缺陷)。

### 自動回歸 harness

`tests/test_benchmarks.py`:對每個 case 用**已 commit 的 `extraction/`** 重跑確定性的
assemble→validate,比對 `expected/{validation.expect.json,minimum.json}` —
斷言 PASS/FAIL、**完整 issue-class map 全等**(error 與 warning 漂移皆為回歸訊號)、
OpenAPI 3.1 valid、paths/webhooks/schemas/securitySchemes/**base_urls** 下限、
**error_codes** 下限、critical_operations、provenance/examples/integration-contract
存在,以及 integration 子欄位(`crypto_required`/`callbacks_required` 正向、
`field_conditions_min`/`test_cases_min` floor)。**需本機 `sources/`**(gitignore)才
標 verified,故缺來源的 case 自動 skip。現況:**10 case + 守門 = 11 passed,全套 348 passed**。

### 已知忠實限制(後續 generator 改進候選)

- **oneOf / discriminator 原生支援**:`adyen-payments-multimethod` 的單一 `/payments`
  以 `paymentMethod.type` 分流 40+ 付款方式;pipeline 目前不產生原生 OpenAPI
  `oneOf`/`discriminator`,改以 object + 具名成員 schema + 描述標 discriminator 對應
  呈現(忠實入 `missing`,非 fail)。為兩輪後最主要的單一改進方向。
- pipeline endpoint method 比對大小寫敏感(inventory 小寫 vs endpoint 大寫 → 重複端點;
  觀察未修)。
