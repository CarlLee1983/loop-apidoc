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
第一輪先手動跑通 1–2 個 case(人眼驗收),再決定是否建自動評分 harness。

## 進度

| case-id | 來源型態 | 狀態 |
| --- | --- | --- |
| `newebpay-mpg` | 台灣金流簽章 PDF | ✅ **PASS**(Phase 1);初跑揭 6 項 pipeline 缺陷 → 全修復後重跑 PASS;OpenAPI 3.1 valid、整合契約+範例齊全(見 notes.md) |
| `apis-guru-baseline` | machine-readable OpenAPI | ✅ **PASS**(Phase 2);揭 1 項 gap(公開 API no-auth 誤判)→ 修 `_has_auth_marker` 後 PASS;7 GET、4 schemas、OpenAPI 3.1 valid |
| `line-pay-online-v3` | REST payment HTML | ✅ **PASS**(Phase 3);HMAC-SHA256 簽章 case(非 CBC→正確 fail-closed gap);總覽頁來源(JS 子頁無法 curl,endpoint body 多 faithful missing);7 paths、31 error codes |
| `tappay-backend` | backend payment HTML | ✅ **PASS**(Phase 3);defuddle 取源;揭 1 項 gap(payload_ref 未 sanitize)→ 修 `_refs` 後 PASS;4 paths+2 webhooks、x-api-key、整合契約齊全 |
| `stripe-basic-rest` | 高品質 REST(官方 OpenAPI 子集) | ✅ **PASS**(Phase 3);Bearer/Basic auth case;揭 1 項 gap(http scheme 缺失)→ 修 `_build_security_scheme` 後 PASS;PaymentIntents 6 op、form body、$ref 連結 |
