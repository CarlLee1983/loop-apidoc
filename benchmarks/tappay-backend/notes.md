# tappay-backend

## Source

- Official URL: https://docs.tappaysdk.com/tutorial/en/back.html
- Downloaded at: 2026-06-28
- Document version: 無(來源未標 API 版本)
- Source format: HTML → defuddle-cli 轉 markdown(468 行;參數表為原始 HTML <table>,含巢狀子表)

## Scope

- Included: Server APIs — Pay by Prime、Pay by Card Token、Refund、Record + Backend Notify(callback)、Frontend Redirect(callback)
- Excluded: reference.html / home.html 等外部頁(supported acquirers、currency limits、e-payment support list、完整 status/msg 錯誤碼表)

## Expected Coverage

- Base URLs: Sandbox https://sandbox.tappaysdk.com、Production https://prod.tappaysdk.com
- Critical endpoints: POST /tpc/payment/pay-by-prime、/tpc/payment/pay-by-token、/tpc/transaction/refund、/tpc/transaction/query
- Auth: x-api-key header(= partner_key);無簽章/加密
- Callback/webhook: Backend Notify(POST,HTTP 200+retry 1/2/4/8/16 分×5)、Frontend Redirect(GET query string)
- Error codes: body 內 status(0=成功,2=Record 列表結束)、error 421 gateway timeout(HTTP status 未文件化)

## Run Log

- preprocess: 不需要(defuddle 已轉 markdown);來源即 sources/tappay-backend-api.md
- 擷取: 1×inventory + 1×integration + 4×endpoint group(prime / token / refund+record / 2 callbacks)= 6 subagent
- assemble: 初跑 FAIL(2 OUTPUT_MISMATCH + 1 warning,揭 payload_ref 誤判)→ **修 _refs sanitize 後重跑 PASS**(1 warning)
- validate: OpenAPI 3.1 **VALID**
- run_dir: `output/20260628T142332Z`(PASS;gitignore)

## Result

- Status: **PASS**(初跑 FAIL 揭 1 項 pipeline gap → 修復後重跑 PASS)
- 產物達成度:4 paths + 2 webhooks、components.schemas(巢狀 cardholder.*/result_url.*/filters.* 正確重建)、x-api-key securityScheme、integration-contract、多語 examples、OpenAPI 3.1 valid。（**數字以「第三輪 re-extraction」為準**）
- Issues:初跑 3 → 修後 **1 warning**:Frontend Redirect GET 無 responses(來源未定義接收端回應 → 降 WARNING)。

### 第三輪 re-extraction（2026-07-03,commit `2dfbeb7`）

全新 agent-native 重擷取並更新 committed `extraction/`(端點檔改零填補 `ep00..`;URL 沿用既有 md 源)。

- Status 不變:**PASS**、**1 × `REQUIRED_INFO_MISSING.warning`**(`endpoints[4]` Frontend Redirect GET 無 response 定義=expected 認可),品質分 **96/100**(補逐端點範例後 completeness 88;初擷取未補範例時為 75)。
- 產物:4 paths + 2 webhooks、**17 `components.schemas`(舊版 10;本輪 inventory 收全欄)**、x-api-key、2 base URLs、integration-contract(**0 crypto / 2 callback / 5 field_condition / 1 test_case**)、6×逐端點範例(取自來源 Format code block)、provenance、OpenAPI 3.1 valid。
- title=`Server APIs`、version 缺漏→`0.0.0` + `x-loop-status:missing-source`(忠實)。
- assemble 帶 `--url` 首跑揭 review.html 崩潰(`UrlSource` 無 status,commit `cf0d868` 修),與 ecpay 共通;修後 PASS。
- 註:舊版 inventory 只取代表性欄位子集(下方 Follow-up 提及的限制),本輪已讓 inventory schema 收全欄,components.schemas 與 request 欄位對齊。
- Missing source info(faithful):無 API 版本(info.version=0.0.0 + x-loop-status:missing-source)、無 HTTP status code、Record trade_records 元素結構截斷、additional_data 宣稱加密但無演算法、callback 無簽章驗證(僅靠 Record API 重查)。皆正確進 missing,未硬補。
- False positives:初跑 2× payload_ref OUTPUT_MISMATCH(已修)。
- False negatives:無。

## Findings(本 case 揭出的 pipeline gap)

1. ✅ **[bug] integration payload_ref 解析未 sanitize**:SKILL 定 `payload_ref = schemas.{inventory schema name}`,但含空白的名稱(如「Backend Notify Body」)在 OpenAPI 被 sanitize 成 key「Backend_Notify_Body」;`validate/integration.py` `_refs` 用**裸名**比對 OpenAPI keys → false OUTPUT_MISMATCH。endpoint 的 `schema_ref` 走 `component_key`/`schema_key_map` 能正確解析,但 integration `_refs` 沒有 → 兩者不一致。
   - **修**:`_refs` 也用 `component_key(name)` sanitize 後比對(裸名與 sanitized 任一命中即有效)。含 RED→GREEN 測試;tappay 重跑 PASS。

## Follow-up

- Generator/validator changes:已修 #1(payload_ref sanitize)。
- 觀察(非 bug):version 缺漏 → info.version=0.0.0 + x-loop-status:missing-source 為合理 fail-closed 標記。
- inventory.schemas 本次取代表性欄位子集(完整逐欄在 endpoints/*.json);若要 components.schemas 與 request 欄位完全對齊,未來可讓 inventory schema 收錄全欄。
