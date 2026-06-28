# newebpay-mpg

## Source

- Official URL: https://www.newebpay.com/website/Page/content/download_api
- Downloaded at: 2026-06-26
- Document version: NDNF-1.2.2(線上交易─幕前支付技術串接手冊)
- Source format: PDF(表格密集 → preprocess 轉 markdown)

## Scope

- Included: 幕前支付(MPG)交易串接、簽章(AES/SHA256/HashKey/HashIV)、付款結果通知 callback
- Excluded: 待跑通後補

## Expected Coverage

- Base URLs: 測試 / 正式 MPG 端點
- Critical endpoints: MPG 交易建立(`/MPG/mpg_gateway` 類)、付款結果通知(callback)
- Auth/signing: AES-256-CBC(TradeInfo)+ SHA256(TradeSha),HashKey/HashIV
- Callback/webhook: 付款完成 NotifyURL / ReturnURL 回傳
- Error codes: 文件狀態碼表

## Run Log

- preprocess: `uv run loop-apidoc preprocess` → `work/sources_md/…NDNF-1.2.2.md`(3128 行高保真 markdown)
- 擷取(agent-native, 唯讀 subagent fan-out): 1×inventory + 1×integration + 5×endpoint(分組:MPG / Query / Cancel+Close / EWallet+BNPL×2 / 3 callbacks)→ inventory.json(10 ep / 20 schema / 127 error / 5 security / 3 env)、integration.json(5 crypto / 3 callback / 7 field_condition / 6 test_case)、endpoints/ep0-9.json
- assemble: round1 → 8 issues(含 integration.crypto.TradeInfo 缺 verify.field ERROR);round2(補 verify.field=TradeInfo)→ 23 issues,揭出 6 項 pipeline 缺陷
- **修 pipeline 6 項後 round3 → PASS**(7 warnings,全非阻斷)
- validate: OpenAPI 3.1 **VALID**;provenance **235 targets**
- run_dir: `output/20260628T135757Z`(PASS;gitignore)

## Result

- Status: **PASS**(初跑 FAIL 揭出 6 項 pipeline 缺陷 → 全數修復後重跑 PASS;見下方 Findings 標註 ✅)
- 產物達成度(全部 ≥ minimum.json):7 paths + 3 webhooks、20 components.schemas、5 securitySchemes、127 error codes、integration-contract(5/3/7/6)、10×三語 examples、provenance 235、api-guide 705 行結構完整、OpenAPI 3.1 valid。
- Issues:初跑 23 → 修復後 **7(全 warning)**:EWallet/BNPL×3 + ReturnURL/CustomerURL 缺 examples、ReturnURL/CustomerURL 無 responses(降為 warning)。皆非阻斷;來源 4.6~4.8 無專屬 PHP 範例(與 AES/SHA 同機制),產出仍含 curl/ts/py 範例,屬來源缺漏。
- Missing source info(來源真缺,faithful):AES/GCM(EncryptType=1)細節、callback 接收端應回應主體、各錯誤碼 HTTP status、BankType 完整清單、rate-limit 數值 — 皆正確進 missing,未硬補。
- False positives:16× OUTPUT_MISMATCH(偵測誤判,非範例真錯);ReturnURL/CustomerURL no-response ERROR(來源確實未定義接收端回應)。
- False negatives:待確認 — 來源 4.6~4.8 是否原本就無 PHP 範例(若有=擷取漏抽)。

## Findings(本 case 揭出的 6 項 pipeline 缺口 — **全數已修復並重跑 PASS**)

1. ✅ **[bug] 簽章接回偵測 false-positive**(16×):`verify.field=TradeInfo` 後,每個 endpoint 範例都會渲染全部 `sign_<scheme>` helper 與註解 `# 簽章 TradeInfo`,字面 'TradeInfo' 洩入 → 偵測器 `target not in content` prefilter 對未攜帶 TradeInfo body 欄位的 endpoint 也觸發。**修**:`validate/integration.py` 改以「範例是否把該欄位宣告為 body key(`"target":`)」為前提,排除註解誤觸。
2. ✅ **[bug] AES 簽章模板硬接 SHA256**:`sign_trade_info` = AES-CBC→hex→SHA256。**修**:`generate/examples.py` `_py_signature`/`_ts_signature` CBC 分支只回 `hex(AES)`,移除 SHA256 與未用 import。
3. ✅ **[bug] 簽章 payload 欄位選錯**:取 `payload_assembly ∩ 外層 body`。**修**:`_payload_field_names` 直接用來源明列欄位(不交集 body);新增 `_payload_pieces`,body 欄位讀實際值、內層欄位用 `<field>` placeholder(不 KeyError)。
4. ✅ **[strictness] webhook 強制要 responses**:**修**:`validate/completeness.py` 對 path-less webhook 缺 responses 降為 WARNING(實 path 仍 ERROR)。
5. ✅ **[contract gap] inventory.schemas[].fields 形狀**:**修**:`SKILL.md` §2 明定 fields 用英文 key `name/type/required/description` + dotted-path 巢狀,並警告勿用中文 key。
6. ✅ **[cosmetic] securityScheme markdown 標籤**:**修**:`generate/markdown.py` `名稱：`→`說明：`(對 apiKey/crypto 皆中性)。

全部修復含 RED→GREEN 單元測試(tests/validate/test_completeness.py、test_validate_integration.py、test_generate_examples.py、generate/test_markdown.py),全測 PASS、ruff clean。

## Follow-up

- Extraction prompt changes:在 SKILL inventory.schemas[].fields 明確要求 name/type/required/description(英文 key);確認 4.6~4.8 是否有 PHP 範例。
- Schema/contract changes:同上(契約 gap #5)。
- Generator changes:修 examples 簽章模板(#2 AES 不應接 SHA256)、簽章 payload 欄位來源(#3 應允許內層明文欄位)。
- Validator changes:修簽章接回偵測 false-positive(#1);webhook 放寬 response 要求(#4)。
- Documentation changes:securityScheme markdown 標籤(#6)。
