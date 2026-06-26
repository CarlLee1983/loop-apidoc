# loop-apidoc — AUTO_FIX no-op 短路設計

- **日期**：2026-06-26
- **狀態**：設計已批准，待實作
- **範圍**：Plan 6 deferral #1 的收尾。純行為短路，**不**引入任何 OpenAPI/輸出修復 transform。

## 背景與問題

`run_correction_loop`（`loop_apidoc/run/correction.py`）依 spec §10 在生成後跑最多 3 輪修正。
驗證 issue 經 `classify_issue` 分成三類：

- `AUTO_FIX`：`OPENAPI_INVALID` / `OUTPUT_MISMATCH`
- `RE_QUERY`：`REQUIRED_INFO_MISSING`
- `UNFIXABLE`：`SOURCE_UNVERIFIED` / `SOURCE_CONFLICT` / `UNSUPPORTED_ASSERTION`

v1 的 generation 是**從 plan 決定性產生**，且**沒有**任何修復 transform。因此當某一輪的可處理（actionable，ERROR 級且 AUTO_FIX 或 RE_QUERY）issue **全是 AUTO_FIX、不含任何 RE_QUERY** 時：

- `requery` 不會被呼叫（只有 RE_QUERY 才觸發），plan 不變；
- `regenerate(plan)` 決定性地產出**完全相同**的（仍然無效）輸出；
- `validate` 得到**完全相同**的報告。

於是 loop 原地空轉直到 `max_rounds`（3）才 FAIL，白燒 2 輪 compute（不耗 NotebookLM quota，但無意義）。

## 目標

- AUTO_FIX-only 的失敗應**立即短路**，不再空燒剩餘輪次。
- 不改變既有的 PASSED / EARLY_STOPPED / 混合 AUTO_FIX+RE_QUERY / 正常 RE_QUERY 復原行為。
- 不引入修復能力（修復 transform 仍為未來工作）。

## 方案

採**預測式守衛**（評估過的另兩案見「替代方案」）：在執行某一輪之前，若該輪可證明是 no-op，就短路。

判定依據是已記錄的不變式：generation 從 plan 決定性產生，且 `requery` 只在 RE_QUERY 存在時呼叫。因此「actionable 全是 AUTO_FIX」⇒ plan 不變 ⇒ 輸出與報告必然不變 ⇒ 這一輪是 no-op。

### 唯一改動點

`loop_apidoc/run/correction.py` 的 `run_correction_loop`：

```python
while not report.ok and rounds < max_rounds:
    actionable = actionable_codes(report)
    if not actionable:
        return CorrectionOutcome(            # 既有：只剩 UNFIXABLE
            plan=plan, result=result,
            report=annotate_fixability(report),
            rounds=rounds, status=RunStatus.EARLY_STOPPED,
        )

    # 新增守衛：AUTO_FIX-only 的這一輪可證明是 no-op（plan 不變、generation 決定性）。
    # 不耗 quota，但也無法修復 → 立即短路為 FAILED，不空燒剩餘輪次。
    if not any(
        classify_issue(issue) is CorrectionCategory.RE_QUERY for issue in actionable
    ):
        return CorrectionOutcome(
            plan=plan, result=result,
            report=annotate_fixability(report),
            rounds=rounds, status=RunStatus.FAILED,
        )

    rounds += 1
    plan = requery(plan, report)   # 守衛後 RE_QUERY 必存在 → 由條件式簡化為無條件
    result = regenerate(plan)
    report = validate(plan, result)
```

`requery` 的呼叫由原本的 `if any(... RE_QUERY ...): plan = requery(...)` 簡化為無條件呼叫，因為新守衛保證執行到此處時 actionable 內必含 RE_QUERY。

### 狀態語義

短路時複用 `RunStatus.FAILED`（不新增 enum 值）。理由：

- 這本質是失敗——輸出無效且 v1 無法修復。
- `rounds < max_rounds` 搭配 `FAILED` 已能區分「短路」與「撐滿 3 輪後失敗」，observability 不需新狀態。
- `RunResult.ok` 仍 = `status is PASSED`，CLI exit code 與既有一致（FAILED → exit 1）。

## 行為變化對照

| 情境 | 改動前 | 改動後 |
| --- | --- | --- |
| 首次驗證即 AUTO_FIX-only 失敗 | rounds=3、FAILED、requery=0 | **rounds=0**、FAILED、requery=0 |
| RE_QUERY 修好缺漏、generator 仍無效 | 撐到 rounds=3 才 FAILED | 下一輪轉 AUTO_FIX-only → 提前短路 FAILED |
| 只剩 UNFIXABLE（source 衝突/未驗證） | EARLY_STOPPED、rounds=0 | 不變 |
| 正常 RE_QUERY 三輪內復原 | PASSED | 不變 |
| 混合 AUTO_FIX + RE_QUERY | 跑該輪（requery） | 不變（仍跑該輪） |
| 首次驗證即 PASS | PASSED、rounds=0 | 不變 |

## 測試策略

`tests/run/test_correction_loop.py`：

- **修改** `test_auto_fix_only_does_not_requery`：斷言 `rounds == 0`（原 `== 3`）、status 仍 `FAILED`、`requeries["n"] == 0`。
- **新增** scenario：第一輪 RE_QUERY 取得進展但仍無效、第二輪報告轉為 AUTO_FIX-only → 驗證在 `rounds < 3` 時短路為 FAILED、且第二輪不再呼叫 `requery`。
- 既有 `test_recovers_within_three_rounds`、`test_final_failure_after_three_rounds`（皆用 RE_QUERY 類 `_missing_report`）、`test_early_stop_on_unfixable_only`、`test_passes_on_first_validation` 不受影響。

`tests/integration/test_correction_scenarios.py`：若其中有依賴 AUTO_FIX-only 撐滿 3 輪的斷言，一併更新為短路後的 rounds 值。

## 文件與收尾

- 更新 `correction.py` 內 AUTO_FIX 的 `NOTE`：把「a real autofix transform — or an identical-report short-circuit — is a deferred enhancement」改寫為「短路已實作；真正的 autofix transform 仍為未來工作」。
- 更新 plan-sequence memory 的 Plan 6 deferral #1：標註短路已完成，僅剩「真正修復 transform」為未來項。

## 替代方案（已評估、未採用）

- **反應式報告比對**：每輪後比對新舊報告，相同即停。更通用（可擋住 requery 回傳未變 plan 的卡死），但偵測前必先燒掉一輪，且需 `ValidationReport` 相等比較。對本問題非最佳。
- **混合（預測守衛 + 報告比對後盾）**：對 v1 過度設計（YAGNI）。

## 非目標

- 不實作 OpenAPI/輸出修復 transform。
- 不改 `classify_issue` 的分類對應。
- 不動 §6 manifest-coverage（deferral #2）、per-stage requery（deferral #3）、preflight 對稱（deferral #4）。
