# Benchmarks — `loop-apidoc` 文件樣本驗證集

依 [`docs/BENCHMARK_VALIDATION_PLAN.md`](../docs/BENCHMARK_VALIDATION_PLAN.md) 建立。
目的:用可重跑的公開文件樣本,檢查整條 `preprocess → 擷取 → assemble → validate`
流程是否能穩定產出足以支援後續開發的 OpenAPI、整合契約、範例與來源追溯。

## 目錄結構(每個 case)

```text
<case-id>/
├── sources/                 # 官方原始來源(gitignore — 操作者本機提供,不入庫)
├── work/                    # preprocess 產出的 markdown 等衍生檔(gitignore)
├── extraction/              # agent 擷取產物(入庫 — 可追溯、可重跑基準)
│   ├── inventory.json
│   ├── endpoints/ep0.json …
│   └── integration.json     # 選填:來源有簽章/加密/callback/欄位條件時才有
├── expected/                # 人工驗收基準(入庫)
│   ├── minimum.json         # 此 case 至少必須抽到的重點
│   └── validation.expect.json  # 預期 PASS/FAIL 與必要 issue 類型
├── output/                  # assemble 實際輸出 run-dir(gitignore)
└── notes.md                 # 來源網址、下載日、觀察、缺漏、決策(入庫)
```

**入庫策略**:`sources/`、`work/`、`output/` 一律 gitignore(原文可能有版權、輸出可重生)。
只 commit `extraction/`、`expected/`、`notes.md` — 這些可重跑、可追溯,但不散布原文。

## 命名規約

`<case-id>` 用穩定、可預測的 kebab-case,例如:
`newebpay-mpg` · `line-pay-online-v3` · `tappay-backend` · `stripe-basic-rest` · `apis-guru-baseline`

## 如何(重)跑一個 case

```bash
RUN=(loop-apidoc); [ -n "$CLAUDE_PLUGIN_ROOT" ] && RUN=(uv run --project "$CLAUDE_PLUGIN_ROOT" loop-apidoc)
# 開發 repo 內直接用 uv run loop-apidoc 亦可

# 1. (PDF/表格密集才需要)前處理成高保真 markdown
uv run loop-apidoc preprocess \
  --sources benchmarks/<case-id>/sources \
  --out     benchmarks/<case-id>/work/sources_md

# 2. Agent 擷取 — 依 skills/loop-apidoc/SKILL.md,讓 coding agent 用唯讀 subagent
#    fan-out 讀來源,寫出 extraction/{inventory.json,endpoints/*.json,integration.json}
#    (這步不是 CLI,是 agent 驅動)

# 3. 組裝 + 驗證
uv run loop-apidoc assemble \
  --sources    benchmarks/<case-id>/sources \
  --extraction benchmarks/<case-id>/extraction \
  --output     benchmarks/<case-id>/output \
  --json
# 取回傳 run_dir 後可再單獨驗證:
uv run loop-apidoc validate --output <run_dir>
```

## 驗收

PASS / FAIL 條件與「產物是否足夠支援後續開發」評分表見
[`docs/BENCHMARK_VALIDATION_PLAN.md`](../docs/BENCHMARK_VALIDATION_PLAN.md)。

### 自動回歸 harness

```bash
uv run pytest tests/test_benchmarks.py -v
```

對每個 case 用**已 commit 的 `extraction/`** 重跑確定性的 assemble→validate,
並比對 `expected/{validation.expect.json,minimum.json}`:斷言 PASS/FAIL、error 數、
OpenAPI 3.1 valid、paths/webhooks/schemas/securitySchemes 數量下限、critical_operations
存在、provenance/examples/integration-contract 齊備。

> **需本機 `sources/`**:驗證器需 manifest 含被引用來源才會把項目標為 verified;
> `sources/` 為操作者提供且 gitignore(部分有版權),故缺 `sources/` 的 case 會自動 **skip**。

## 進度

| case-id | 來源型態 | 狀態 |
| --- | --- | --- |
| `newebpay-mpg` | 台灣金流簽章 PDF | ✅ **PASS**(Phase 1);初跑揭 6 項 pipeline 缺陷 → 全修復後重跑 PASS;OpenAPI 3.1 valid、整合契約+範例齊全(見 notes.md) |
| `apis-guru-baseline` | machine-readable OpenAPI | ✅ **PASS**(Phase 2);揭 1 項 gap(公開 API no-auth 誤判)→ 修 `_has_auth_marker` 後 PASS;7 GET、4 schemas、OpenAPI 3.1 valid |
| `line-pay-online-v3` | REST payment HTML | ✅ **PASS**(Phase 3);HMAC-SHA256 簽章 case(非 CBC→正確 fail-closed gap);總覽頁來源(JS 子頁無法 curl,endpoint body 多 faithful missing);7 paths、31 error codes |
| `tappay-backend` | backend payment HTML | ✅ **PASS**(Phase 3);defuddle 取源;揭 1 項 gap(payload_ref 未 sanitize)→ 修 `_refs` 後 PASS;4 paths+2 webhooks、x-api-key、整合契約齊全 |
| `stripe-basic-rest` | 高品質 REST(官方 OpenAPI 子集) | ✅ **PASS**(Phase 3);Bearer/Basic auth case;揭 1 項 gap(http scheme 缺失)→ 修 `_build_security_scheme` 後 PASS;PaymentIntents 6 op、form body、$ref 連結 |
| `cybersource-payments` | 大型企業 REST(SDK codegen docs) | ✅ **PASS**(第二輪);複雜巢狀 schema 壓測;首跑即 0 error(pipeline 已成熟,未揭新缺陷);5 op、18 schema(40+ 欄位 ProcessingInformation)、JWT/HTTP Signature wire 格式 fail-closed placeholder |
| `github-webhooks` | webhook/callback 專屬 | ✅ **PASS**(第二輪);揭 1 項真 bug(多 webhook 同源碰撞)→ 修 `_merge_one_detail`/`_match_index` + `webhook_name` 後 PASS;3 webhook、HMAC-SHA256 驗簽、無自動重送 |
| `paypal-webhooks-incomplete` | 文件不完整 | 🟥 **EXPECTED_FAIL**(第二輪);真實不完整官方頁(無 base URL/簽章延後/payload 未文件化);越界 payload schema 被 `SOURCE_UNVERIFIED` 擋下(2 error);證明不臆造,缺漏入 missing |
| `ecpay-creditcard-pdf` | 表格密集 PDF | ✅ **PASS**(第二輪);pymupdf4llm preprocess;AioCheckOut 36 參數表完整保真;揭 1 項真 bug(純簽章 auth 誤觸 no-auth gap)→ 修 `_has_auth_marker` 後 PASS;4 path+1 webhook、CheckMacValue SHA256 |
| `adyen-payments-multimethod` | 多產品共用 endpoint | ✅ **PASS**(第二輪完結);Adyen Checkout v71 官方 OpenAPI;單一 `POST /payments` 以 `paymentMethod.type` discriminator(oneOf union)服務 40+ 付款方式;首跑即 0 error(pipeline 已成熟);3 path、10 schema、雙 auth 完整文件化;oneOf 不產生原生 discriminator 為忠實限制(入 missing);與 github-webhooks 互為對偶 |
