# adyen-payments-multimethod — 多產品共用 endpoint

第二輪覆蓋表最後一類「多產品共用 endpoint」(同一路徑不同交易類型 → endpoint
merge、operationId、文件可讀性)。與 `github-webhooks`(多 callback 同源碰撞)互為
對偶:此處測「**單一進入點承載多產品**」。

## 來源

| 項目 | 內容 |
| --- | --- |
| 來源 | Adyen Checkout API v71 官方 OpenAPI 規格(machine-readable JSON) |
| 取得 | `curl` 下載 `https://raw.githubusercontent.com/Adyen/adyen-openapi/main/json/CheckoutService-v71.json`(下載日 2026-06-28) |
| 檔案 | `sources/CheckoutService-v71.json`(~890 KB,gitignore) |
| 授權 | Adyen 官方公開規格;原文 gitignore,只入庫 `extraction/`、`expected/`、`notes.md` |

Source restoration (2026-07-23): restored the v71 source from immutable commit
`74fabab0628019206b77c4823776b726345a035d` (2026-05-28), preceding the recorded
download. The ignored `sources/CheckoutService-v71.json` has SHA-256
`9e426ae2bf007b148c393c5f163bbb0abe54959172b4d85676aedbd178b2b0b0`; its direct
URL acquisition is recorded in `url_sources/coverage.json`.

## 為何選 Adyen `/payments`

`POST /payments` 是**單一多方法進入點**:`PaymentRequest.paymentMethod` 是橫跨
40+ 種付款方式 detail 物件的 `oneOf` union,以 `type` discriminator 分流
(scheme→CardDetails、ideal→IdealDetails、applepay→ApplePayDetails、ach、klarna、
googlepay…)。「同一路徑、不同交易類型」在國際金流即以此 polymorphic body 表達,
正是本類要壓測的可讀性與結構保真風險點。

## 取材範圍(忠實子集)

- **端點(3)**:`POST /payments`(起單)、`POST /payments/details`(redirect/3DS
  續流)、`POST /paymentMethods`(列出可用方法)。三者共同說明「多產品共用入口 +
  續流」的故事。
- **schemas(10)**:`PaymentRequest`(多型 body)、`PaymentResponse`、`Amount`、
  三個代表性成員 `CardDetails`/`IdealDetails`/`ApplePayDetails`、
  `PaymentDetailsRequest`、`PaymentMethodsRequest`/`PaymentMethodsResponse`、
  `ServiceError`。欄位、型別、enum、required 全程式化萃取自 spec → 可追溯。
- **securitySchemes(2)**:`ApiKeyAuth`(`X-API-Key` header)、`BasicAuth`(http
  basic),來源 `components.securitySchemes` 完整文件化。
- **integration**:`field_conditions` 以 discriminator 表達各產品差異化必填;
  `test_cases` 接地兩個官方 sample(`components.examples.post-payments-card-direct`、
  `post-payments-ideal`)。

## 結果:首跑即 PASS(0 error)

`assemble --json` → `ok:true`、exit 0。pipeline 自第一輪已成熟,本 case 未揭新缺陷。

- **3 個 `REQUIRED_INFO_MISSING.warning`**:`/payments`、`/payments/details`、
  `/paymentMethods` 各一筆「endpoint 缺少 request/response 範例」。extraction 的
  endpoint 物件未帶 inline 範例;接地官方 sample 改放 `integration.test_cases`
  (與 `cybersource-payments` 同慣例),故降為 WARNING 而非 error。
- OpenAPI 3.1 valid;`info.title`=「Adyen Checkout API」、`version`=「71」;
  servers=test;3 paths、10 schemas、2 securitySchemes;response 以
  `$ref` 連結 `PaymentResponse`/`ServiceError`;`tags: [Payments]` 宣告於 root;
  operationId `post_payments` / `post_payments_details` / `post_paymentMethods` 穩定。
- provenance 35 筆覆蓋核心;三端點 py/ts/sh 範例齊備;integration-contract 含
  4 field_conditions + 2 test_cases。

## Exact-evidence parity（2026-10-08）

本 case 已列入 `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`。重播結果:legacy `passed` /
Core `accept`,23/23 Core claim supported,243 筆 relationship 全為 support(212 筆
`derived_support`、31 筆 `explicit_support`),
`test_case_obeys_declared_core_parity_contract[adyen-payments-multimethod]` 通過。

- 證據:全部是指向 `CheckoutService-v71.json`(SHA-256 `9e426ae2…`)的 v1
  `json_pointer`。Core 會比對 pointer 所指的值,或以允許的 Structural Derivation 重算;
  不採用不比對內容的 claim-bound 參照。
- 前置的 Core 推導:
  - #189:error `/code` 由 `/paths/<p>/<m>/responses/<status>` 的 4xx/5xx key 推導。
  - #190:test case 的 operation 參照由 operation `requestBody` 下的
    `examples/<key>` 位置推導。
- 改成原文:
  - 18 個 operation response 的 `description`。
  - 5 個 `errors.meaning`,改為所引 `/payments` response 的 `description`。
  - 2 個 `test_cases.name`,改為所引 `components.examples` 的 `summary`。
- 移除:
  - environment 名稱 `test`(來源沒有命名 environment)。
  - 2 個 `operational`(multi-method entry point、redirect / 3DS continuation):內容是
    extraction 自己的說明,不是來源文字。
  - 4 個 `field_conditions`,不移入 `missing`,因為來源有寫,只是以結構表達。它們原本寫的是:
    - `paymentMethod.type = scheme (card)` → `CardDetails`;
    - `paymentMethod.type = applepay` → `ApplePayDetails`(required `applePayToken`);
    - `paymentMethod.type = ideal` → `IdealDetails`(只固定 `type`);
    - redirect / 3DS 付款方式 → `PaymentRequest.required`(含 `returnUrl`)。
    
    這些都由 `paymentMethod` 的 `oneOf` 與各 detail schema 的 `required` 表達,schema
    claim 已涵蓋。`minimum.json` 的 `counts.field_conditions` 4→0。
- 推導所需的修正:
  - 每個 endpoint 的 `request` 加上 `schema_ref`(等於原有的 `request.schema`)。
    claim projection 讀的是 `request.schema_ref`,FunkyGames 也同時帶兩個 key。
  - 4 個陣列欄位加 `[]`:`allowedPaymentMethods`、`blockedPaymentMethods`、
    `paymentMethods`、`storedPaymentMethods`。
  - 5 個欄位移除推論出的 `object` 型別,因為來源 property 只有 `$ref` 或 `oneOf`:
    三個 `amount`、`PaymentDetailsRequest.details`、`PaymentRequest.paymentMethod`。
  - `POST /payments/details` 的 `200` `schema_ref` 改為 `null`:來源指向未擷取的
    `PaymentDetailsResponse`,不是原本寫的 `PaymentResponse`。
- `validation.expect.json`:`REQUIRED_INFO_MISSING.warning` 由 4 筆增為 6 筆。新增的
  兩筆是「operational 缺少資訊」,以及「`/payments/details` 成功 response 沒有 schema」。
- 已過時的說明:`validation.expect.json` 的 `observations` 裡,描述 field_conditions 的
  那一句已不符現況。AC8 只允許修改計數與其說明,所以這次沒有改那一句。

## 忠實限制 / 缺漏(入 `missing`,不臆造)

1. **oneOf/discriminator 現原生產生**:pipeline 已支援 `one_of` + `discriminator`
   欄位宣告,generator 直接輸出原生 OpenAPI `oneOf`/`discriminator`。`paymentMethod`
   以 `oneOf` 指向三個具名成員 schema(CardDetails/IdealDetails/ApplePayDetails),
   `discriminator.propertyName=type`,`mapping` 對應 scheme/ideal/applepay。此為
   正面證明(機器可用的多型),非忠實限制。
2. **CSE 客戶端加密演算法**:`CardDetails.encrypted*` 欄位的加密演算法不在 Checkout
   spec(card-direct 範例用原始卡號)→ 忠實入 missing。
3. **Webhook / HMAC 驗簽**:Adyen 通知 payload 與 HMAC 屬另一支 Notification API,
   不在 Checkout spec → 無 callbacks,入 missing。

## 重跑

```bash
C=benchmarks/adyen-payments-multimethod
# (sources/ 需操作者本機提供:curl 上述 URL 存成 sources/CheckoutService-v71.json)
# source-quality/ 需先由 manifest → inspect-source-risk → assess-sources 產出(見 benchmarks/README.md)
uv run loop-apidoc assemble --sources "$C/sources" --extraction "$C/extraction" --output "$C/output" \
  --source-quality "$C/source-quality" --json
uv run pytest tests/test_benchmarks.py -k adyen -q
```
