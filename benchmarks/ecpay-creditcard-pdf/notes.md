# ecpay-creditcard-pdf

第二輪 — 表格密集 PDF(PDF preprocess、欄位表、錯誤碼表)。

## Source

- Official URL（fetched 2026-06-28）：
  https://www.ecpay.com.tw/Content/files/gw_p110.pdf
  （綠界科技全方位金流 信用卡介接技術文件 V5.6.1,61 頁 PDF,2.8MB）
- Document version：V5.6.1（inventory.version=5.6.1）
- Source format：PDF → `loop-apidoc preprocess`(pymupdf4llm)→ markdown(`work/sources_md/gw_p110.md`,2190 行,540 表格列)

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
