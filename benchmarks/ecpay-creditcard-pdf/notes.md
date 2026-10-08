# ecpay-creditcard-pdf

第二輪 — 表格密集 PDF(PDF preprocess、欄位表、錯誤碼表)。

## Source

- Official URL（fetched 2026-06-28）：
  https://www.ecpay.com.tw/Content/files/gw_p110.pdf
  （綠界科技全方位金流 信用卡介接技術文件 V5.6.1,61 頁 PDF,2.8MB）
- Document version：V5.6.1（inventory.version=5.6.1）
- Source format：PDF → `loop-apidoc preprocess`(pymupdf4llm)→ markdown(`work/sources_md/gw_p110.md`,2190 行,540 表格列)
- Source restoration (2026-07-23): re-downloaded from the same official URL into the
  ignored `sources/gw_p110.pdf`; SHA-256
  `fd12a38c37df000e0927d39fdc32448c304b10e8aa6056d4419c63c42b7f53e9`.
  The PDF metadata (title, 2022-06-15 creation/modification date, 61 pages) and the
  cited endpoint/callback/signature sections match this case's recorded V5.6.1
  source identity. This is a restored copy of that published edition, not a newer
  API-document substitution.

## Scope

- Included(4 path + 1 webhook,皆 form-POST application/x-www-form-urlencoded)：
  - `POST /Cashier/AioCheckOut/V5`（產生訂單,36 參數表）
  - 付款結果通知（**webhook**,POST/ReturnURL,回 1|OK,17 回傳欄位）
  - `POST /Cashier/QueryTradeInfo/V5`（查詢訂單）
  - `POST /CreditDetail/QueryTrade/V2`（查詢信用卡單筆明細,JSON 回應）
  - `POST /CreditDetail/DoAction`（關帳/退刷/取消/放棄）
- 簽章：CheckMacValue（SHA256,EncryptType=1;參數排序→HashKey 前綴+HashIV 後綴→URL encode→小寫→SHA256→大寫）
- 錯誤碼：RtnCode=1 成功、10200095 訂單未成立(文件僅列部分,完整表需後台查)
- Excluded：定期定額(QueryCreditCardPeriodInfo / CreditCardPeriodAction)、對帳媒體檔下載

## Expected Coverage

- Base URLs：2（payment / payment-stage .ecpay.com.tw）
- Critical endpoints：AioCheckOut、QueryTradeInfo、DoAction
- Auth/signing：CheckMacValue SHA256（integration.crypto;非 OpenAPI securityScheme）
- Callback/webhook：付款結果通知(回 1|OK;未回應則 5~15 分鐘重送、當天 4 次)
- Error codes：RtnCode 等

## Run Log

- preprocess：`preprocess --sources ... --out work/sources_md`(pymupdf4llm)→ gw_p110.md
- 擷取：唯讀 subagent 讀 md → 結構化 JSON;主 agent 組裝(html.unescape `&gt;`/`&amp;`)
- assemble：初跑 1 error(no-auth 誤判)/ 5 warning → 修 completeness 後 0 error / 5 warning → PASS
- run_dir：`benchmarks/ecpay-creditcard-pdf/output/<ts>`（gitignore）

## Result

- Status: **PASS**
- Issues：5 × `REQUIRED_INFO_MISSING.warning`（5 endpoint 各無逐端點範例,忠實缺漏）
- PDF 表格保真(人眼+數字驗證)：
  - AioCheckOut 36 參數(11 必填)完整保留;付款結果通知 17 欄位;查詢/退款參數表保留。
  - api-guide / OpenAPI 正確帶出 base URL、CheckMacValue 機制、錯誤碼。
- Missing source info：完整交易狀態代碼表(需後台查)、定期定額/對帳媒體檔(範圍外)
- False positives：1(no-auth 誤判,已修)。False negatives：無。

### 第三輪 re-extraction（2026-07-03,commit `2dfbeb7`）

全新 agent-native 重擷取並更新 committed `extraction/`(端點檔改零填補 `ep00..`)。

- Status 不變:**PASS**、5 × `REQUIRED_INFO_MISSING.warning`(逐端點無範例,忠實),品質分 **82/100**(completeness 40 因無逐端點範例被拉低;不影響 validation)。
- 產物:4 paths + 1 webhook、**10 具名 `components.schemas`(改為 `$ref` 連結,舊版全內嵌在 endpoint parameters)**、2 base URLs、securitySchemes 0(CheckMacValue 屬 integration.crypto)、integration-contract(1 crypto / 1 callback / 4 field_condition / 1 test_case)、provenance 50、examples 齊、OpenAPI 3.1 valid。
- title=`綠界科技全方位金流 信用卡介接技術文件`、version=`V5.6.1`。AioCheckOut requestBody 仍 36 屬性 / 11 必填。
- assemble 帶 `--url` 首跑揭 review.html 崩潰(見下方 Pipeline 缺陷 §2),修後 PASS。

### Source-derivation lane（2026-08-17,issue #111）

原始 PDF 已還原到本機 gitignored `raw/gw_p110.pdf`(SHA-256 與上述
`fd12a38c…` 記載逐位元組相同,今天由官方 URL 重新下載驗證)。新增 committed
`source-derivation.json` 綁定原始 PDF、本機 `sources/gw_p110.pdf.md`(注意:
兩者都是 gitignored,不入庫;入庫的只有描述檔記錄的 SHA-256)與轉檔工具
(pymupdf4llm,版本交給 `uv.lock` 決定,不在描述檔內釘死)。以現行
`uv run loop-apidoc preprocess`(pymupdf4llm)重跑該 PDF,產出與本機
`sources/gw_p110.pdf.md` 逐位元組相同 —— `preprocess` 這一步
正式納入 `tests/test_benchmarks.py` 與 `scripts/quality_gate.py
--strict-local` 迴圈(ADR 0013)。`jili-legacy-gaming-pdf` 因無公開
URL、未取得供應商原始檔,本次不列入此 lane。

### Exact-evidence parity（2026-10-08）

本 case 已列入 `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`。重播結果:legacy `passed` /
Core `accept`,38/38 Core claim supported、0 unverified,
`test_case_obeys_declared_core_parity_contract[ecpay-creditcard-pdf]` 通過。

- 證據:extraction 內 495 筆 v1 `evidence`,全是指向 `gw_p110.pdf.md`(SHA-256
  `d42d3337…`)的 `line_range`。
- 範圍規則:Core 對 `line_range` 只核對來源、位置、digest 與 claim path,不比對文字
  (`CLAIM_BOUND_EXACT_REFERENCE`),所以每筆證據另以腳本檢查,0 違規。規則如下(全文見
  `specs/stories/ecpay-exact-evidence-parity.md`):
  - `flat(s)` = 移除 `*`、`|`、`<br>`,再把連續空白縮成一格。
  - 每段範圍至多 40 行。
  - 字串值經 `flat` 後須出現在範圍內。
  - 非字串值(如 `required`)的範圍須含該欄位名稱。
  - 來源沒寫出名稱的識別字(schema 名、`schema_ref`、environment 名、field-condition
    scope、integration `kind`、`operation_refs`,以及來源寫明「並無參數名稱」的
    `PaymentResultResponse.response`)須沿用同一項目已被文字檢查的範圍。
- 改成原文的轉述(只改值、不重新命名識別字):
  - 4 個 operation 與 path-less webhook 的 `summary` 及 `200` 回應 `description`。
  - webhook 的 `CheckMacValue` 參數 `description`。
  - 7 個 `errors.meaning`。
  - 7 個 `operational` 的 `topic`(改成來源章節標題)與 `detail`。
  - `callbacks[0]` 的 `name`/`verification`/`expected_response`。
  - CheckMacValue 的 6 個步驟。
  - 4 個 `field_conditions.when`。
  - `test_cases[0].name`。
  - 7 個來源寫作 `String (9)`/`String (20)`/`String (1)` 的欄位 `type`。
- 前置 Core 修正:
  - 同一 scope 的多個 field condition 各有 claim identity(#186)。
  - test case 的 `paths.{path}.{method}` 參照可解析到對應 operation(#187);test case 的
    `operation_refs` 證據綁在 `/operation_refs/operation:POST:~1Cashier~1AioCheckOut~1V5`。
- `validation.expect.json` 不變(5 × `REQUIRED_INFO_MISSING.warning` 照舊)。

### `request.schema_ref`(2026-10-08)

5 個端點的 `request` 補上 `schema_ref`,值與既有的 `request.schema` 相同。
`schema_ref` 才是指向 inventory schema 的 key:claim projection 只讀它來產生
operation 的 `request_schema_ref`,cross-file gate 也只檢查它;只寫在 `schema` 的名稱,
Core 看不到、gate 也不檢查。`schema` 保持不變,因為 generator 仍讀它,產出的 OpenAPI
不變。4 個有 path 的 operation 各多一筆 `/request_schema_ref` 證據,沿用同一端點
`/method` 的範圍(範圍規則第 4 條的識別字,加上 `/request_schema_ref`);path-less
webhook 投影成 webhook claim,不帶 request schema。

## Pipeline 缺陷（本 case 揭 2 項真 bug,皆 TDD 修)

### 1. 純簽章 auth 誤觸 no-auth gap

**純簽章 auth 誤觸 no-auth gap**(`validate/completeness.py _has_auth_marker`)：
金流 API 僅以請求簽章(CheckMacValue,記在 `integration.crypto`)做驗證、無 OpenAPI
securityScheme 時,completeness 誤報『無 security scheme 且來源未標示未提供 authentication』
→ ERROR(false positive)。

- 修法:`_has_auth_marker` 在 `plan.integration.crypto` 非空時回 True —— 已記錄的
  簽章/加密機制即 API 的驗證機制,來源已處理 auth。
- TDD：`tests/validate/test_completeness.py::test_no_security_scheme_but_integration_crypto_is_ok`
  (先紅後綠);既有 no-auth / public / missing-marker 測試仍綠。

### 2. `assemble --url` → review.html 崩潰（第三輪揭,commit `cf0d868`）

`generate/review.py` `_source_rows` 對 URL 來源取 `source.status.value`,但 `UrlSource`
無 `status` 欄(只有 `http_status`)→ 只要 manifest 含 URL 來源、產生 review.html 就
`AttributeError: 'UrlSource' object has no attribute 'status'`。**SKILL.md 明令 assemble
帶 `--url`,但先前所有 benchmark/harness 都只 `--sources`,從未踩過此路徑。**

- 修法:`_source_rows` 由 `http_status` 導狀態(200→ok / None→未取得 / else→http N)。
- TDD：`tests/generate/test_review_html.py::test_review_html_renders_url_sources_without_crashing`。

## Follow-up

- 與其他 case 共通的既有 follow-up:form/body 參數平鋪、巢狀物件未 $ref(generator 設計)。
  ECPay 為扁平 form 參數,影響不大。
