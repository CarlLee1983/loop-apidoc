# loop-apidoc — per-stage requery 設計

- **日期**：2026-06-26
- **狀態**：設計已批准，待實作
- **範圍**：Plan 6 deferral #3 的收尾。讓修正循環的 requery 只重查與失敗相關的 NotebookLM 擷取 stage，而非每次重跑整個 `run_extraction`，以節省查詢額度。

## 背景與問題

修正循環（`run_correction_loop`）在遇到 `REQUIRED_INFO_MISSING`（分類為 `RE_QUERY`）錯誤時，呼叫 pipeline 注入的 `requery` closure。目前該 closure（`loop_apidoc/run/pipeline.py`）執行：

```python
def requery(p, r):
    fresh = run_extraction(adapter, notebook_url, store)   # 全部 10 個 stage
    ...
```

`run_extraction` 依序跑 `STAGES`（01–10），每個 stage 發 INITIAL +（structured 且有 gap 時）FOLLOWUP + REVERSE 查詢，一次約 20–30 個 NotebookLM 查詢。每一輪修正都重跑全部，即使只有一兩個 endpoint 欄位缺漏，造成額度浪費。

### actionable RE_QUERY 的來源範圍（關鍵觀察）

`check_completeness`（`loop_apidoc/validate/completeness.py`）只在三種情形產生 **ERROR 級** `REQUIRED_INFO_MISSING`（即會成為 actionable RE_QUERY 的 issue）：

| 檢查 | issue location | 來源 stage |
| --- | --- | --- |
| endpoint 缺 method/path | `paths.<path>.<method>` 或 `endpoints[<i>]` | 05（endpoint inventory） |
| endpoint 缺 responses | `paths.<path>.<method>` 或 `endpoints[<i>]` | 06（per-endpoint details） |
| 無 security scheme 且無 auth marker | `components.securitySchemes` | 04（authentication） |

其餘 stage（01/02/03/07/08/09/10）的 completeness 檢查只產 WARNING 或不產 issue，永不成為 actionable RE_QUERY。因此「issue → stage」映射的目標範圍只有 **{04, 05, 06}**。

## 目標

- requery 只重查與當輪 actionable RE_QUERY issue 相關的 stage。
- 保留脈絡鏈正確性：重查 stage 的 `known_summary` 仍反映其前序 stage 的（最新）答案。
- 非重查 stage 的擷取結果原樣保留，與重查結果合併後交給既有 `build_normalization_plan`。
- 無法精準鎖定 stage 時，fail-closed 退回完整 `run_extraction`，絕不略過該補的 requery。

## 決策

| 主題 | 決定 | 理由 |
| --- | --- | --- |
| 映射粒度 | 粗粒度：endpoint 類 issue → `{05, 06}`，security → `{04}` | 依 location 字首判定，不解析中文 evidence（穩定）。05（inventory）變動會影響 06（details），捆綁重查維持資料一致。仍省約 70% 額度。 |
| 未映射 fallback | 退回完整 `run_extraction` | fail-closed：correctness 優先於 quota；未知 location 寧可全查也不略過。 |
| 脈絡鏈 | 重建 `prior_initials`：重查 stage 用新答案、保留 stage 用舊答案 | 與 full run 累積邏輯一致，後查 stage（06）看得到剛重查的前序（05）答案。 |
| store 持久化 | 不改格式 | 重查覆寫 `answers/<query_id>.txt`、`queries.jsonl` 多一筆歷史紀錄；符合 §7.1「不丟棄前輪」。plan builder 讀 in-memory ExtractionResult，不受 jsonl 重複影響。 |

## 方案

### 1. 重構 orchestrator：抽出 per-stage 執行

在 `loop_apidoc/extraction/orchestrator.py` 把 `run_extraction` 迴圈體抽成共用 helper：

```python
def _run_stage(
    adapter: NotebookLMAdapter,
    store: ExtractionStore,
    stage: QueryStage,
    known: str,
    notebook_url: str,
    max_attempts: int,
) -> list[AnswerArtifact]:
    """Run one stage's INITIAL (+ optional FOLLOWUP for structured gaps) + REVERSE."""
    artifacts: list[AnswerArtifact] = []
    initial = _ask_and_store(adapter, store, stage, QueryKind.INITIAL,
                             build_question(stage, QueryKind.INITIAL,
                                            notebook_url=notebook_url, known_summary=known),
                             notebook_url, max_attempts)
    artifacts.append(initial)

    if stage.mode is StageMode.STRUCTURED:
        block = extract_json_block(initial.answer)
        gaps = find_gaps(block) if block is not None else []
        if gaps:
            followup_q = build_question(stage, QueryKind.FOLLOWUP, notebook_url=notebook_url,
                                        known_summary=known, pending_fields=gaps)
            artifacts.append(_ask_and_store(adapter, store, stage, QueryKind.FOLLOWUP,
                                            followup_q, notebook_url, max_attempts))

    reverse_q = build_question(stage, QueryKind.REVERSE, notebook_url=notebook_url,
                               known_summary=known)
    artifacts.append(_ask_and_store(adapter, store, stage, QueryKind.REVERSE,
                                    reverse_q, notebook_url, max_attempts))
    return artifacts
```

`run_extraction` 改為逐 stage 呼叫 `_run_stage`，行為與輸出**完全不變**：

```python
def run_extraction(adapter, notebook_url, store, *, max_attempts=3) -> ExtractionResult:
    artifacts: list[AnswerArtifact] = []
    prior_initials: list[tuple[str, str]] = []
    for stage in STAGES:
        known = build_known_summary(prior_initials)
        stage_artifacts = _run_stage(adapter, store, stage, known, notebook_url, max_attempts)
        artifacts.extend(stage_artifacts)
        initial = stage_artifacts[0]   # INITIAL is always first
        prior_initials.append((stage.title, initial.answer))
    return ExtractionResult(notebook_url=notebook_url, artifacts=artifacts)
```

### 2. 新增 targeted 重查

同檔新增：

```python
def rerun_stages(
    adapter: NotebookLMAdapter,
    notebook_url: str,
    store: ExtractionStore,
    prior: ExtractionResult,
    stage_ids: set[str],
    *,
    max_attempts: int = 3,
) -> ExtractionResult:
    """Re-run only the requested stages; retain prior artifacts for the rest.

    Iterates STAGES in order so a re-run stage's known_summary reflects the
    latest answer of every earlier stage (fresh if re-run this round, else
    retained). Returns a merged ExtractionResult consumable by
    build_normalization_plan unchanged.
    """
    artifacts: list[AnswerArtifact] = []
    prior_initials: list[tuple[str, str]] = []
    for stage in STAGES:
        if stage.stage_id in stage_ids:
            known = build_known_summary(prior_initials)
            stage_artifacts = _run_stage(adapter, store, stage, known,
                                         notebook_url, max_attempts)
            artifacts.extend(stage_artifacts)
            initial_answer = stage_artifacts[0].answer
        else:
            retained = prior.for_stage(stage.stage_id)
            artifacts.extend(retained)
            retained_initial = prior.initial(stage.stage_id)
            initial_answer = retained_initial.answer if retained_initial else ""
        prior_initials.append((stage.title, initial_answer))
    return ExtractionResult(notebook_url=notebook_url, artifacts=artifacts)
```

### 3. 新增 issue → stage 映射

新增 `loop_apidoc/run/requery.py`：

```python
from __future__ import annotations

from loop_apidoc.run.correction import actionable_codes, classify_issue
from loop_apidoc.run.models import CorrectionCategory
from loop_apidoc.validate.models import ValidationReport


def stages_for_requery(report: ValidationReport) -> set[str]:
    """Map actionable RE_QUERY issues to the extraction stages that produced them.

    Coarse mapping (spec deferral #3): endpoint-shaped issues bundle stages 05
    (inventory) and 06 (details); security issues map to stage 04. An empty
    result means the locations could not be pinned to a stage — the caller
    falls back to a full re-extraction.
    """
    stages: set[str] = set()
    for issue in actionable_codes(report):
        if classify_issue(issue) is not CorrectionCategory.RE_QUERY:
            continue
        location = issue.location
        if location.startswith("components.securitySchemes"):
            stages.add("04")
        elif location.startswith("paths.") or location.startswith("endpoints["):
            stages.update({"05", "06"})
    return stages
```

（`actionable_codes` 已只回傳 ERROR 級且 AUTO_FIX/RE_QUERY 的 issue；此處再以 `classify_issue` 過濾出 RE_QUERY，AUTO_FIX 不納入 stage 映射。）

### 4. pipeline 的 requery closure：保留 + 合併

在 `loop_apidoc/run/pipeline.py`，用可變 holder 跨輪保留目前 extraction，並讓 requery 走 targeted 路徑：

```python
store = ExtractionStore(run_dir / "extraction")
extraction = run_extraction(adapter, notebook_url, store)
state = {"extraction": extraction}
plan = build_normalization_plan(extraction, manifest)
_persist_plan(run_dir, plan)
...
def requery(p, r):
    stages = stages_for_requery(r)
    if stages:
        fresh = rerun_stages(adapter, notebook_url, store,
                             state["extraction"], stages)
    else:
        fresh = run_extraction(adapter, notebook_url, store)
    state["extraction"] = fresh
    new_plan = build_normalization_plan(fresh, manifest)
    _persist_plan(run_dir, new_plan)
    return new_plan
```

需新增 import：`from loop_apidoc.extraction.orchestrator import rerun_stages`、`from loop_apidoc.run.requery import stages_for_requery`。

## 行為對照

| 情境 | 改動前 | 改動後 |
| --- | --- | --- |
| endpoint 缺 method/path 或 responses → requery | 重跑全部 10 stage | 只重查 stage 05+06 |
| 無 security scheme → requery | 重跑全部 10 stage | 只重查 stage 04 |
| RE_QUERY issue location 無法映射（防禦） | 重跑全部 10 stage | 退回完整重跑（不變） |
| 非 RE_QUERY（AUTO_FIX-only）輪次 | 不呼叫 requery | 不呼叫 requery（不變） |
| `run_extraction` 直接呼叫（首次擷取） | 全部 10 stage | 全部 10 stage（重構後行為不變） |

## 測試策略

`tests/extraction/`：

- **重構回歸**：既有 `run_extraction` 測試在抽出 `_run_stage` 後全綠（行為、artifact 數、順序不變）。
- **`rerun_stages`（fake counting adapter）**：
  - 只重查指定 stage：`stage_ids={"04"}` → 只有 stage 04 的查詢被打出；其餘 artifact 來自 `prior`，數量/內容與 prior 相同。
  - 合併正確：回傳的 ExtractionResult 對非重查 stage `for_stage(id)` == prior 的對應 artifact；對重查 stage 為新答案。
  - 脈絡鏈：當 `stage_ids={"05","06"}`，stage 06 的 INITIAL question 的 `known_summary` 含**新的** stage 05 答案（以可記錄問題的 fake adapter 驗證）。
  - 查詢次數遠少於 full（計數比較）。

`tests/run/test_requery.py`（新增）：

- `stages_for_requery`：
  - `components.securitySchemes` 的 RE_QUERY ERROR → `{"04"}`。
  - `paths./users.get` → `{"05","06"}`；`endpoints[0]` → `{"05","06"}`。
  - 混合 security + endpoint → `{"04","05","06"}`。
  - WARNING 級 REQUIRED_INFO_MISSING（summary/examples 缺）不計入（非 actionable）→ `set()`。
  - 非 RE_QUERY（如 SOURCE_CONFLICT、OPENAPI_INVALID）→ `set()`。
  - 空報告 → `set()`。

`tests/run/`（pipeline，counting adapter 或既有 scenario 風格）：

- endpoint-missing 報告驅動的 requery 只打到 stage 05/06；security 報告只打到 04。
- 空映射報告（防禦造例：以一個 location 不符前綴的 RE_QUERY issue）→ 退回完整 `run_extraction`。

`uv run pytest -q` 全綠（基線 212 passed + 1 skipped，預期隨新測試上升）。

## 文件與收尾

- 更新 plan-sequence memory 的 Plan 6 deferral #3，標註 per-stage requery 已實作（粗粒度 04／05+06、未映射 fallback 完整重查），保留邏輯與脈絡鏈說明。

## 替代方案（已評估、未採用）

- **精準 05 vs 06 區分**：依 evidence 字串分辨「缺 method/path」（05）與「缺 responses」（06），更省額度，但需解析中文 evidence（脆弱），且 05 變動時 06 未同步會不一致。否決。
- **每個 issue 的 location 精準到單一 endpoint 再 per-endpoint 重查**：屬另一個 carry-forward（per-endpoint fan-out），範圍更大，本次不做。

## 非目標

- 精準 stage 05/06 區分或 per-endpoint 細查。
- 改動 `build_normalization_plan`。
- 改動 `ExtractionStore` 持久化格式。
- 改動 `classify_issue` 或 §9.5 issue code。
