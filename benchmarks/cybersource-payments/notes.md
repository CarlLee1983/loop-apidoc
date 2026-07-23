# cybersource-payments

第二輪 — 大型企業 API（複雜巢狀 schema + 範例產出壓力測試）。

## Source

- Official URL:
  - SDK 文件（欄位真相，swagger-codegen 產生的忠實 model docs）：
    `https://github.com/CyberSource/cybersource-rest-client-python`（`README.md` + `docs/*.md`）
  - 官方請求範例（接地 integration test_case）：
    `https://github.com/CyberSource/cybersource-rest-samples-python`
    （`samples/Payments/Payments/simple-authorizationinternet.py`，本 case 以 `.md` 包存）
- Downloaded at: 2026-06-28
- Document version: client repo `master`（無語意版號 → inventory.version=null）
- Source format: Markdown（SDK docs）+ 官方 Python sample（包成 markdown code fence）
- Source restoration (2026-07-23): restored the 24 cited SDK Markdown files from
  client commit `a9dde2993c9c7ccb5ad0267822a9dd475823b19d` (2026-05-16) and the
  official authorization sample from sample-repo commit
  `629d93fc009126b88648d1e5bde2a4052be7046a` (2026-05-27), both preceding the
  recorded download. The ignored `sources/` set has 25 files; its file digests
  are in `url_sources/source-manifest.json`. The sample retains its official
  Python bytes under the benchmark's established `.md` citation filename, with
  no content substitution.

> Cybersource 開發者入口（`developer.cybersource.com/api-reference-assets`）為 JS SPA,
> curl/defuddle 取不到（試過 2 個 auth 頁皆 0 bytes）。改用官方 SDK repo 的 codegen `docs/*.md`
> 作欄位真相 —— 它們是 machine-readable 衍生、可重抓、無版權疑慮。
> `CyberSource/cybersource-rest-api-specs` repo 為空,不可用。

## Scope

- Included：核心付款生命週期 5 操作
  - `POST /pts/v2/payments`（create_payment / 授權）
  - `POST /pts/v2/payments/{id}/captures`（capture）
  - `POST /pts/v2/payments/{id}/refunds`（refund）
  - `POST /pts/v2/payments/{id}/voids`（void）
  - `POST /pts/v2/payments/{id}/reversals`（auth reversal）
- Included schemas（18）：5 個 request root + 7 個 request 巢狀（ClientReferenceInformation、
  ProcessingInformation〔40+ 欄位〕、OrderInformation、OrderInformationAmountDetails、
  OrderInformationBillTo〔20+ 欄位〕、PaymentInformation、PaymentInformationCard〔80+ 卡別列舉〕）+
  5 個 201 response root + 1 個 400 error。
- Excluded：TMS/token、payouts、flex、其餘數百個巢狀 model（捕捉到 root 層級,更深層列為 missing）。

## Expected Coverage

- Base URLs：2（apitest / api .cybersource.com）
- Critical endpoints：上述 5 操作
- Auth/signing：JWT with Shared Secret（建議）/ HTTP Signature（棄用）+ MLE 訊息層加密
  —— on-the-wire header/簽章演算法**未在來源**,fail-closed 入 missing;
  securityScheme 以 missing-source placeholder 呈現。
- Callback/webhook：無
- Error codes：create_payment 的 400（status=INVALID_REQUEST,reason 列舉 11 值）

## Run Log

- preprocess：不需要（來源已是 markdown）
- 擷取：唯讀 subagent fan-out × 3（inventory meta / request schemas / response schemas）→ 主 agent 組裝
- assemble：0 error / 5 warning → PASS
- run_dir：`benchmarks/cybersource-payments/output/<ts>`（gitignore）

## Result

- Status: **PASS**
- Issues：5 × `REQUIRED_INFO_MISSING.warning`（endpoints 無 source 範例,忠實缺漏）
- Missing source info：auth wire 格式、MLE 演算法、逐欄位真實必填（SDK docs 一律標 [optional]）、
  capture/refund/void/reversal 的錯誤回應、HATEOAS `_links` 結構、rate limit / idempotency。
- False positives：無
- False negatives：無

## Pipeline 缺陷

**本 case 未揭新 pipeline 缺陷**（第一輪每個 case 都揭 1+ 缺陷;pipeline 已成熟）。

唯一一次 error 是**驗證器正確 fail-closed**:初版 integration `test_case` 範例值為臆造 →
`SOURCE_UNVERIFIED`(error)。改以官方 sample(`samples/simple-authorizationinternet.md`,
值完全相符)接地 → SUPPORTED。這是驗證器**正確擋下未接地內容**,非 bug。
（過程中也確認:`.py` 非支援來源格式,需以 `.md` 收納。）

## Follow-up（非本輪 fail,列入 generator 改進候選）

- requestBody 巢狀物件(order_information 等)以 `type:object` 平鋪,未 `$ref` 對應的
  component schema(`Ptsv2paymentsOrderInformationAmountDetails` 等存在於 components.schemas
  但未被 body 連結)。與 `stripe-basic-rest` 同屬既有設計 —— codegen 無法自動連結巢狀型別。
  大型 schema case 把此限制放大(28-40 欄位的 root 仍是平鋪 object)。
