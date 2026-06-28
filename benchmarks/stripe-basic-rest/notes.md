# stripe-basic-rest

## Source

- Official URL: https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.sdk.json(官方 OpenAPI spec)
- Downloaded at: 2026-06-28
- Document version: Stripe API 2026-06-24.dahlia
- Source format: OpenAPI(spec3.sdk.json,10MB)→ 取 Payment Intents 子集存於 sources/stripe-payment-intents-subset.json
- 取源說明: docs.stripe.com/api 為 JS-heavy SPA(1.2MB,難淨取);改用官方 machine-readable OpenAPI spec 的 Payment Intents 子集(高品質 REST 對照,符合 doc「挑 3-5 基本 endpoint」)。

## Scope

- Included: Payment Intents 生命週期 6 個 operation(5 paths):create / retrieve / update / confirm / cancel / capture
- Excluded: 其餘 PI endpoint(search、apply_customer_balance、increment_authorization…)、完整 PaymentIntent schema(45 欄取代表性 20)、巢狀 request 子物件全展開、全域 error 物件

## Run Log

- 來源取得: curl 官方 spec → Python 取 6 op + PaymentIntent schema 子集存 sources/。
- 擷取: orchestrator 直接由 machine-readable spec 程式化撰寫(faithful,真實 description/type)。inventory + 6 endpoints,無 integration.json(無 crypto/callback)。
- assemble: 初跑 FAIL(1 OPENAPI_INVALID + 6 no-response error + warnings)→ 修 2 項後 **PASS**(6 warning)
- validate: OpenAPI 3.1 **VALID**;provenance 26
- run_dir: `20260628T143815Z`(PASS;gitignore)

## Result

- Status: **PASS**(初跑 FAIL 揭 1 項 pipeline gap + 1 項擷取 casing 失誤 → 修復後 PASS)
- 產物達成度:5 paths / 6 operations(get+post 同路徑正確合併)、PaymentIntent schema、bearerAuth+basicAuth(http scheme 正確)、create 37 form 欄位、 response 連結、OpenAPI 3.1 valid、provenance 26。
- **驗證重點達成**:HTTP Bearer/Basic 認證(第 4 種 auth 型態,前面 case 未涵蓋)、form-urlencoded request body、同路徑多 method 合併、 回應連結。
- Issues(6 warning):各 endpoint 缺 request example(子集未取 example → faithful)。
- Missing source info(faithful):per-op error responses、完整 PaymentIntent 45 欄、巢狀子 schema — 皆進 missing。
- False positives:初跑 6× no-response(實為擷取 casing 失誤造成端點重複,非 pipeline bug;已修)。

## Findings

1. ✅ **[bug] http 型 securityScheme 缺 `scheme` → OPENAPI_INVALID**:`generate/openapi.py` `_build_security_scheme` 對 `type:http` 只輸出 `{"type":"http"}`,但 OpenAPI 規定 http 必須有 `scheme`(bearer/basic)→ spec 驗證失敗。任何 Bearer/Basic 認證來源都會中招。
   - **修**:http 型由 details/name 推導 scheme(含 bearer→bearer、basic→basic);無法推導則退回 missing-source apiKey placeholder(不輸出非法 http)。含 RED→GREEN 測試;stripe 重跑 PASS。
2. ⚠️ **[擷取教訓 / 輕量 pipeline 觀察]**:inventory.endpoints 用小寫 method(取自 spec path key),endpoint detail 用大寫 → endpoint 比對**區分大小寫**,產生重複端點(半數無 response)。本次修擷取(統一大寫)解決;另記:pipeline endpoint 比對/dedup 對 method 大小寫敏感,未來可考慮正規化。

## Follow-up

- Generator: 已修 #1(http scheme)。可考慮 endpoint method 比對正規化(#2 觀察)。
- 若要強化:補全 PaymentIntent 45 欄與巢狀子 schema、加 request examples。
