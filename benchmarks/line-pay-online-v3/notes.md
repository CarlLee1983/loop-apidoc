# line-pay-online-v3

## Source

- Official URL: https://developers-pay.line.me/online-api-v3
- Downloaded at: 2026-06-28
- Document version: Online API v3
- Source format: HTML(JS SPA)→ defuddle-cli 轉 markdown(online-api-v3-overview.md,221 行)

## Scope

- Included: online-api-v3 **總覽頁**(共用 request/response 慣例、HMAC 簽章 header、base URLs、~50 個 result code、Request body 範例、回應 envelope、Transaction ID 處理)
- Excluded(重要限制): 各 endpoint(Confirm/Capture/Void/Refund/Payment Details/Check)的**逐項 request/response 欄位表**位於 **JS 渲染的子頁**,curl/defuddle 無法取得(子頁 URL 403/SPA 路由);僅取得 endpoint 路徑。

## Run Log

- 來源取得: `npx defuddle-cli parse https://developers-pay.line.me/online-api-v3 --md`;子頁無法 curl(JS SPA)。
- 擷取: orchestrator 直接依已讀來源撰寫(來源小,已全讀)。inventory + integration(HMAC)+ 7 endpoints。
- assemble: **PASS**(6 warning,無 error)
- validate: OpenAPI 3.1 **VALID**
- run_dir: `20260628T143249Z`(PASS;gitignore)

## Result

- Status: **PASS**(初跑即 PASS,無新 pipeline finding)
- 產物達成度:7 paths(path 參數 transactionId 正確)、2 securitySchemes(HMAC-SHA256 + ChannelId)、2 schemas(Response Envelope / Payment Request Body)、31 error codes、integration-contract(1 crypto / 1 field_condition / 2 test_case)、OpenAPI 3.1 valid。
- **驗證重點達成**:HMAC-SHA256 簽章機制正確抽取;因非 CBC,簽章範例正確走 **fail-closed gap**(`# gap: 簽章 X-LINE-Authorization 來源未提供 mode, payload_assembly` → NotImplementedError),未捏造 HMAC 公式。這是 NewebPay AES 沒測到的第 2 種簽章機制路徑。
- Issues(6 warning):6 個 endpoint 缺 examples(其 body 不在所取來源 → faithful)。
- Missing source info(faithful):各 endpoint 逐項 body 欄位、完整 v3 Request schema(packages/redirectUrls)、HMAC payload 組裝公式(在 Prerequisites 頁)、GET 端點 query 參數 — 皆正確進 missing,未硬補。
- False positives/negatives:無。

## Findings

- 無新 pipeline finding(HMAC 非 CBC → 正確 fail-closed gap)。
- **來源取得限制(非 pipeline bug)**:LINE Pay v3 文件為 JS SPA,逐 endpoint 子頁無法以 curl/defuddle 取得;本 case 以總覽頁為據,屬「文件不完整」型樣本(endpoint body 多進 missing)。若要完整逐欄,需 Playwright 渲染子頁(未做)。

## Follow-up

- 若要強化此 case:用 Playwright 抓各 endpoint 子頁補齊 request/response 欄位表。
- 觀察:大型 error-code 表(31)正確產出;HMAC 走 gap path 正確。
