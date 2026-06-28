# github-webhooks

第二輪 — webhook / callback 專屬(async flow、驗簽、重送規則)。

## Source

- Official URLs（fetched 2026-06-28）：
  - https://docs.github.com/en/webhooks/webhook-events-and-payloads （交付 header + 共用 payload 屬性 + ping/star/push 事件）
  - https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries （簽章驗證）
  - https://docs.github.com/en/webhooks/using-webhooks/handling-failed-webhook-deliveries （失敗交付 / 重送）
- Document version：docs.github.com（無語意版號 → inventory.version=null）
- Source format：HTML → 以 WebFetch 取得逐字內容,操作者整理成兩份 markdown 存入 `sources/`
  （`webhook-delivery-and-signing.md`、`webhook-events-and-payloads.md`）

> defuddle 對 docs.github.com 回 0 bytes（JS 渲染）;WebFetch 可取。內容為官方文件逐字引用。

## Scope

- Included webhooks（3,皆 method=POST / path=None）：`ping`、`star`、`push`
- Schemas（4）：CommonWebhookProperties、PingEvent、StarEvent、PushEvent
- 簽章：`X-Hub-Signature-256`（HMAC-SHA256,sha256= 前綴,簽 raw body）+ 舊版 `X-Hub-Signature`（HMAC-SHA1）
- 重送：GitHub **不自動重送**;接收端須 10 秒內回 HTTP 200,失敗只能手動 / REST API redeliver
- Excluded：repository/sender/hook/commit 物件完整 schema(僅 object 層級);其餘數十種事件型別

## Expected Coverage

- Base URLs：0（webhook 交付到整合者設定的 URL,無固定 API server）
- Critical webhooks：ping / star / push
- Auth/signing：HMAC 簽章（見上）—— 非 OpenAPI securityScheme,放 integration.crypto + operational
- Callback/webhook：3 個 callback,含 trigger / transport / payload_ref / verification / expected_response（含重送規則）
- Error codes：無（webhook 無錯誤碼表）

## Run Log

- preprocess：不需要
- 擷取：直接手寫（來源小;3 webhook + 4 schema + integration）
- assemble：初跑 0 error / 5 warning（其中 2 筆為 star/push「無 response」假象 → pipeline bug)
  → 修 builder 後 0 error / 3 warning → PASS
- run_dir：`benchmarks/github-webhooks/output/<ts>`（gitignore）

## Result

- Status: **PASS**
- Issues：3 × `REQUIRED_INFO_MISSING.warning`（webhook 無 source 範例,忠實缺漏)
- Missing source info：webhook secret 長度/格式、repository/sender 完整 schema、其餘事件型別、
  REST API redelivery endpoint 路徑
- False positives：無（修 bug 後）
- False negatives：無

## Pipeline 缺陷（本 case 揭 1 項真 bug,已 TDD 修)

**多 webhook 同源碰撞**（`plan/builder.py`）：一頁文件列多個 webhook 事件時（GitHub/Stripe 常態),
所有 path-less detail 會 reduce 到同一個 `manifest_source`,原本只靠 manifest_source 配對 →
全部 detail 堆到第一個 webhook(ping 吞下 star/push 共 18 欄位,star/push 變空 default response)。

- 修法：`_match_index` 對 path-less webhook **優先以 distinct locator 配對**、manifest_source 後備,
  且每個 webhook endpoint 至多被取用一次（`consumed` set）。
- 連帶強化 `webhook_name`:在首個 **句子(`. `/`。`)或冒號(`: `/`：`) 邊界** 切,
  避免整段 summary 變成巨長的 webhook key（先前 key = 整句 summary）。
- TDD：`tests/plan/test_builder.py::test_webhooks_sharing_one_source_file_pair_by_locator_not_collapsed`、
  `tests/generate/test_naming.py::test_webhook_name_cuts_at_first_sentence_or_colon_boundary`（先紅後綠）。
  既有 `test_webhook_details_merge_by_source_not_collapsed`(不同源)仍綠。

## Follow-up

- 無新增 follow-up;repository/sender 等物件 schema 未展開為已知忠實缺漏(來源未逐欄列出)。
