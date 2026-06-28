# paypal-webhooks-incomplete

第二輪 — 文件不完整案例(fail-closed、missing、不臆造、provenance)。**EXPECTED_FAIL**。

## Source

- Official URLs（fetched 2026-06-28）：
  - https://developer.paypal.com/api/rest/webhooks/ （overview:交付、簽章「延後到 Integration guide」、2xx + 重送 25 次/3 天）
  - https://developer.paypal.com/api/rest/webhooks/event-names/ （事件型別清單;明言不含 payload schema）
- Source format：HTML → WebFetch 逐字 → 操作者整理成兩份 markdown 存 `sources/`
- 取材原則:依計畫「官方文件中刻意挑缺 base URL / 缺 response / 簽章描述不完整者」。
  PayPal 這兩頁**本身就真實不完整**:base URL 未提供、簽章 header/演算法延後到他頁、
  payload 欄位明言需查其他文件。無需人工裁切即具備 fail-closed 所需的缺口。

## Scope

- Included webhooks（3,皆 method=POST / path=None）：
  `PAYMENT.SALE.COMPLETED`、`PAYMENT.CAPTURE.COMPLETED`、`CHECKOUT.ORDER.APPROVED`
- 1 schema `WebhookEvent`(envelope 欄位)—— **故意讓其 source 指向未提供的 REST API reference**,
  模擬 extraction 越界納入無法接地的 payload schema。
- 簽章:機制有提(CRC32+signature 或 verify-signature endpoint),但 header/演算法/步驟延後 → 入 missing。
- 重送:2xx;否則 25 次/3 天。

## Expected Coverage

- Base URLs：0（webhook 交付到訂閱者 URL;且管理 API 的 host 未提供）
- Auth/signing：機制有提、細節缺 → integration.crypto.algorithm=null + missing
- Callback/webhook：3 callback,含重送規則
- Error codes：無

## Run Log

- assemble：**2 error / 3 warning → FAIL（如預期)**
  - SOURCE_UNVERIFIED × 2(同根因:WebhookEvent schema source 未在 manifest)
  - REQUIRED_INFO_MISSING.warning × 3(webhook 無範例)
- run_dir：`benchmarks/paypal-webhooks-incomplete/output/<ts>`（gitignore）
- OpenAPI 3.1 valid（失敗 run 仍產出合法 OpenAPI:3 webhooks、1 schema、無 servers）

## Result

- Status: **EXPECTED_FAIL**（正確 fail-closed,非 bug)
- 證明不臆造:
  - base URL 缺 → environments 空 + missing,未補 host。
  - 簽章細節延後 → algorithm=null + missing,未發明 PAYPAL-TRANSMISSION-* / 演算法。
  - payload 欄位未文件化 → webhook body 空、callbacks.payload_ref=null。
  - 管理 API → 僅 missing,未發明 path/method/schema。
  - 越界的 WebhookEvent schema(source 不在 manifest)→ 被 SOURCE_UNVERIFIED 擋下,不放行。
- False positives：無。False negatives：無。

## Pipeline 缺陷

無。本 case 驗證的是**既有 fail-closed 行為正確**:多源情境下,引用未提供來源的斷言被
classify 標 UNVERIFIED,並由 completeness(unverified_items)與 no-speculation(schema target)
雙重報為 error;缺漏資訊一律進 missing,未被硬補。

## Follow-up

- 無。此 case 作為 harness 內唯一的 EXPECTED_FAIL 樣本,守住「驗證器會把缺漏/未接地報成
  error 而非吞掉」這條不變量。
