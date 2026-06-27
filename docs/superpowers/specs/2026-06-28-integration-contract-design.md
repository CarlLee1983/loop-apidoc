# Design: `integration-contract.json` — 機器可讀整合契約

- **Date**: 2026-06-28
- **Status**: Approved design — pending implementation plan
- **Scope**: 為 `loop-apidoc` 新增一份來源接地、可驗證、機器可讀的整合契約產物,補齊 OpenAPI/Markdown 之外的「整合機制層」(加解密、簽章鏈、callback、跨欄位條件、測試案例)。

## 1. 動機

現行產物(`openapi.yaml` + `api-guide.zh-TW.md`)能撐起 60–70% 的 API 接口骨架(client、DTO、request builder、端點導覽),但讓付款類功能真正跑起來的關鍵——AES 加解密、HashKey/HashIV 組字串順序、TradeInfo/TradeSha 包裝、callback 解密與 CheckValue 驗證——目前多半以**自由文字**落在 `OperationalEntry.detail` 與 `SecuritySchemeEntry.details` 裡:對人有幫助,對 codegen 不夠。

本設計新增 `integration-contract.json`:把這些「機制層」資訊變成有 citation、可被 no-speculation 交叉驗證的結構化欄位。

**核心不變量(沿用,非協商):** 來源文件是唯一真相。契約任一欄位來源沒講就留 `null` 並記入 `missing`,絕不臆測、絕不用 REST/付款慣例補。

## 2. 範圍決策

- **通用整合契約(非付款專用)**:schema 對「加解密/簽章機制」給足表達力,但不寫死 `HashKey`/`TradeSha` 之類 domain 專名——專名落在通用欄位的 `name`/`description`/`key_source`。對純 REST 來源,crypto/callback 區段為空,不影響其他產物。
- **資料來源採混合策略**:
  - 結構化機制資訊走**新抽取階段**(subagent 直接從原文抽,帶 citation),不由程式事後從文字推導。
  - 已在 plan 結構化的部分(env、operationId、endpoints、errors)**複用 plan**,契約只引用不重抽。
- **驗證原則**:有講必抽全、抽必有據、沒講不假裝。

## 3. 架構與資料流

```
sources ──(subagent fan-out 唯讀)──▶ agent 寫 JSON
                                       ├─ inventory.json        (現有)
                                       ├─ endpoints/*.json      (現有)
                                       └─ integration.json      (新:契約原始抽取,帶 citation)
                                                   │
                                          loop-apidoc assemble
                                                   │
              manifest ─▶ plan(新增 integration 區塊)─▶ generate ─▶ validate
                                                   │
        ┌──────────────────────────────┼─────────────────────────────────┐
   openapi.yaml (現有)        integration-contract.json (新產物)       api-guide.zh-TW.md(加「整合機制」章節)
                                  provenance.json (含契約 target)        validation/report(含契約檢查)
```

- **新抽取階段**:fan-out 多一類唯讀 subagent,專讀整合機制段落,回傳 `integration.json`。沿用既有「subagent 只讀/搜尋、回傳 JSON、主 agent 寫檔」原則。
- **單一 I/O 出口不變**:僅 `generate/`(`generate_outputs`)與 `run/` 寫檔;契約組裝/驗證皆純函式。
- **`assemble` 流程不變**:`manifest → plan → generate → validate`,只是各階段多認得契約;`assemble` 仍只組裝、不抽取,透過 `--json` 回報供 agent 自驅修正迴圈。

## 4. `integration-contract.json` Schema

每個葉節點帶 `citations`(沿用 `plan.models.SourceCitation`);來源沒講就 `null` 並進 `missing`。

```jsonc
{
  "version": "1.0",
  "api_title": "...",                    // 複用 plan.resolved_title
  "base_urls": [ /* 複用 plan.environments */ ],

  "crypto": [                            // 0..n 套加解密/簽章機制
    {
      "name": "TradeInfo 加密",          // 來源用詞,不寫死
      "purpose": "request",              // request | response | callback | signature
      "algorithm": "AES",                // 來源明述,否則 null
      "mode": "CBC",
      "padding": "PKCS7",
      "key_source": { "key": "HashKey", "iv": "HashIV", "note": "..." },
      "payload_assembly": [              // 組字串/欄位順序(簽章鏈關鍵)
        { "step": 1, "desc": "...", "fields": ["..."] }
      ],
      "encoding": "hex-lower",
      "verify": { "field": "TradeSha", "method": "SHA256", "desc": "..." },
      "citations": [ /* SourceCitation */ ]
    }
  ],

  "callbacks": [                         // 0..n 回呼/webhook
    {
      "name": "NotifyURL 付款通知",
      "trigger": "...",
      "transport": "HTTP POST form",
      "payload_ref": "schemas.TradeInfo",  // 指向已抽 schema,不重描述
      "verification": "用 crypto[TradeInfo] 解密 + 比對 TradeSha",
      "expected_response": "1|OK",
      "citations": [ ... ]
    }
  ],

  "field_conditions": [                  // 跨欄位條件(單欄 required/format/enum 已在 schema)
    {
      "scope": "endpoints.{path}.{method} | schemas.{name}",
      "rule": "當 ItemType=2 時 ProdDesc 必填",
      "when": "ItemType == 2",
      "then_required": ["ProdDesc"],
      "citations": [ ... ]
    }
  ],

  "error_codes": [ /* 複用 plan.errors,以 contract 視角輸出 */ ],

  "test_cases": [                        // 僅收錄來源實際列出的 sample
    {
      "name": "MPG 建立交易範例",
      "operation_ref": "paths./MPG/mpg_gateway.post",
      "request": { /* 來源列出的範例 */ },
      "response": { ... },
      "citations": [ ... ]
    }
  ],

  "missing": [ { "area": "crypto.padding", "detail": "來源未述 padding" } ]
}
```

設計取捨:

- `payload_assembly` 用「步驟陣列」表達簽章組字串順序——付款 codegen 最缺、且對任何簽章 API 通用。
- `callbacks.payload_ref` / `field_conditions.scope` / `test_cases.operation_ref` 一律用**指標**指回 OpenAPI / schema 既有位置,不重複描述,維持單一真相。
- crypto/callback/test_cases 皆 `0..n`,純 REST 來源得到空陣列。

## 5. Provenance 對齊與驗證

### 5.1 provenance target 新命名空間

與既有 OpenAPI target 並列、一對一可回溯:

```
integration.crypto.{name}
integration.callbacks.{name}
integration.field_conditions.{index}
integration.test_cases.{name}
```

no-speculation 檢查擴充:掃描契約每個葉節點,凡無對應 provenance target / 無 citation → 違規。

`error_codes` 為 `plan.errors` 的複用視角,沿用其既有 citation,**不**另立 `integration.*` target,避免同一事實重複接地。

### 5.2 驗證三道力道

| 情境 | 分類 | 行為 |
|---|---|---|
| 契約欄位填了來源沒講的內容 | `UNSUPPORTED_ASSERTION` | fail-closed(不可修) |
| 來源明述「需加密/簽章」但 crypto 細節沒抽到 | `REQUIRED_INFO_MISSING` | agent 回去補讀 |
| 來源根本沒提 crypto/callback | (不分類) | 留 null,記 `missing`,**不 fail** |
| `payload_ref`/`operation_ref` 指向不存在的 OpenAPI 位置 | `OUTPUT_MISMATCH` | fixable,重組 |

「來源明述需加密卻沒細節」的偵測:掃既有 `plan.operational` / `plan.security_schemes` 文字裡的訊號詞(如「加密」「簽章」「AES」「HashKey」),有訊號卻無對應 `crypto` 條目 → `REQUIRED_INFO_MISSING`。此舉同時實現「阻擋宣稱可直接產碼」的 codegen-readiness 守門。

- completeness 對契約 section 一律視為 optional——缺席不 fail,僅缺「半套」才 fail。

## 6. Package 邊界

維持「many small files、單一 I/O 出口、I/O 外皆純函式」。

| 動作 | 檔案 | 性質 |
|---|---|---|
| 契約 plan 模型 | `loop_apidoc/plan/models.py` 加 `IntegrationContract` 等 model + `NormalizationPlan.integration` 欄位 | 純資料 |
| agent JSON → plan 區塊 | `loop_apidoc/agentcli/extraction.py` 擴充(讀 `integration.json`) | 純函式 |
| 契約組裝 | **新** `loop_apidoc/plan/integration.py`(複用 errors/env、訊號詞掃描) | 純函式 |
| 產出 contract 檔 + provenance target | **新** `loop_apidoc/generate/integration.py`,由 `generate_outputs` 呼叫 | I/O 經 generate |
| api-guide 章節 | `loop_apidoc/generate/markdown.py` 加「整合機制」section | I/O 經 generate |
| 驗證 | `loop_apidoc/validate/` 加 no-speculation 契約掃描 + 訊號詞缺漏檢查 | 純函式 |
| SKILL 契約 | `skills/loop-apidoc/SKILL.md` 加新 subagent 抽取指示 + `integration.json` 格式 | 文件 |

新增檔 2 個(`plan/integration.py`、`generate/integration.py`),其餘為既有檔擴充。`assemble` 的 `manifest→plan→generate→validate` 主流程不變。

## 7. 產物

- **主產物**:`integration-contract.json`(機器可讀,供 codegen / SDK 提示)。
- **人類可讀**:`api-guide.zh-TW.md` 新增「整合機制」章節(資料已在手,邊際成本低)。
- `provenance.json` 多出 `integration.*` target;`validation/report.{json,md}` 含契約檢查結果。

## 8. 測試策略(TDD,≥80% 覆蓋)

- **plan/integration.py**
  - agent `integration.json` → `IntegrationContract` 正常組裝
  - 訊號詞觸發:operational 文字含「AES/HashKey」但無 crypto 條目 → `REQUIRED_INFO_MISSING`
  - 來源無 crypto → 留 null + 進 missing,**不** fail
  - errors/env 複用、不重複
- **generate/integration.py**
  - `integration-contract.json` 結構正確、每葉節點帶 citation
  - provenance 多出 `integration.*` target 且與契約一對一
  - `payload_ref` / `operation_ref` 指向 OpenAPI 既有位置(指標解析)
- **validate**
  - 契約欄位無 citation → no-speculation 違規
  - `operation_ref` 指向不存在位置 → `OUTPUT_MISMATCH`
  - 填了來源沒講的簽章順序 → `UNSUPPORTED_ASSERTION` fail-closed
- **markdown**:api-guide 出現「整合機制」章節且內容對應契約
- **e2e**:用已驗證的 NewebPay PDF(95 頁)來源跑完整 `assemble`,**人眼**確認 `integration-contract.json` 的 TradeInfo 簽章鏈完整(呼應教訓:validation PASS ≠ 產物好)。

## 9. 不在本次範圍(YAGNI / 後續)

- extraction JSON 全面強型別化(Parameter/RequestBody/Response 等)——獨立改善項。
- 其他開發者導向產物:`integration-tasks.md`、`examples/`(curl/TS/Python)、`postman_collection.json`、`sdk-hints.json`。
- 契約以外的 codegen-readiness 驗證(operationId 穩定性等)——本設計僅實作與契約直接相關的訊號詞守門。
