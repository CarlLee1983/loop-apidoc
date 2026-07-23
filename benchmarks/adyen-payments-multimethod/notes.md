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
uv run loop-apidoc assemble --sources "$C/sources" --extraction "$C/extraction" --output "$C/output" --json
uv run pytest tests/test_benchmarks.py -k adyen -q
```
