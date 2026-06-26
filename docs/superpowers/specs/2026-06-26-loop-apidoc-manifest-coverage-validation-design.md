# loop-apidoc — manifest-coverage 驗證設計

- **日期**：2026-06-26
- **狀態**：設計已批准，待實作
- **範圍**：Plan 6 deferral #2 的收尾。啟用 `validate_outputs` 閒置的 `manifest` 參數，把無法納入規格化的本機來源浮現為驗證 issue（spec §6）。

## 背景與問題

`validate_outputs(plan, result, manifest)`（`loop_apidoc/validate/validator.py`）聚合四項 §9 驗證類別（structure / completeness / consistency / speculation）。`manifest` 參數**已被接收但從未使用**，docstring 註明為「deferred enhancement」。

spec §6「來源 Manifest」要求 manifest 用於「發現本機漏檔、重複檔與不支援格式」，且 §11 明定「不支援檔案：加入 manifest issue，不靜默略過」。manifest scanner 已將每個本機來源標記 `ProcessingStatus`：

- `UNREADABLE`：檔案存在但讀取失敗（OSError／broken symlink）。
- `UNSUPPORTED`：格式不受支援，無法被 NotebookLM 納入。
- `DUPLICATE`：與既有來源內容相同（已記錄 `duplicate_of`）。
- `PENDING`：正常待處理。

目前這些狀態只存在於 `manifest.json`，驗證層完全不檢視，因此「來源無法納入規格化」不會反映在驗證報告或 run 結果。

## 目標

- 把無法納入規格化的本機來源浮現為驗證 issue，不靜默略過（§6 / §11）。
- 同時涵蓋兩條既有路徑：修正循環的 in-memory `validate_outputs`，與 standalone `loop-apidoc validate --output <run-dir>`（經 `validate_run_dir`，已強制載入並傳入 manifest）。
- 不浪費 NotebookLM 額度：這類 issue 在修正循環中必須被視為不可自動修正。

## 決策

| 主題 | 決定 | 理由 |
| --- | --- | --- |
| IssueCode | 複用 `SOURCE_UNVERIFIED` | 未支援／無法讀取的來源 = 內容無法被驗證納入輸出，語義相符。修正循環 `classify_issue` 已將 `SOURCE_UNVERIFIED` 映射為 `UNFIXABLE` → early-stop、不浪費額度。零 enum／classify／§9.5 改動。 |
| UNREADABLE 嚴重度 | `ERROR`（阻擋） | 真實 I/O 故障、零資訊的 coverage gap；符合 §6「未確認來源 → 完整性驗證不得通過」。 |
| UNSUPPORTED 嚴重度 | `WARNING`（不阻擋） | 可能是偏門檔（logo／zip 等非 API 來源）；浮現供人判斷，但不讓 sources 目錄的雜訊檔誤報 run 失敗。 |
| DUPLICATE | 不浮現 | 刻意去重，內容已由原檔涵蓋，非 coverage gap；manifest 已記錄 `duplicate_of`。 |

## 方案

### 新增 `loop_apidoc/validate/coverage.py`

```python
from __future__ import annotations

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import Issue, IssueCode, Severity


def check_manifest_coverage(manifest: Manifest) -> list[Issue]:
    """§6 來源涵蓋檢查：把無法納入規格化的本機來源浮現為 issue。

    - UNREADABLE 來源 → ERROR（讀取失敗、零資訊的 coverage gap）。
    - UNSUPPORTED 來源 → WARNING（格式不支援，浮現但不阻擋）。
    - DUPLICATE 不浮現（刻意去重，內容已由原檔涵蓋）。

    issue code 一律用 SOURCE_UNVERIFIED；location 用來源 relative_path
    （§6 穩定來源識別碼）。修正循環會將之分類為 UNFIXABLE。
    """
    issues: list[Issue] = []
    for source in manifest.unreadable():
        issues.append(
            Issue(
                code=IssueCode.SOURCE_UNVERIFIED,
                severity=Severity.ERROR,
                location=source.relative_path,
                evidence="來源無法讀取，內容未納入驗證",
                suggested_fix="確認檔案可讀取後重新掃描",
            )
        )
    for source in manifest.unsupported():
        issues.append(
            Issue(
                code=IssueCode.SOURCE_UNVERIFIED,
                severity=Severity.WARNING,
                location=source.relative_path,
                evidence=f"來源格式不受支援（{source.source_format.value}），未納入規格化",
                suggested_fix="轉為受支援格式（PDF／Markdown／Word／OpenAPI）或確認可略過",
            )
        )
    return issues
```

`manifest.unreadable()` 與 `manifest.unsupported()` helper 已存在於 `loop_apidoc/manifest/models.py`。

### 接線 `validate_outputs`

在 `loop_apidoc/validate/validator.py` 既有四項檢查之後追加：

```python
issues += check_manifest_coverage(manifest)
```

並把 docstring 中「`manifest` is accepted but not yet consumed: …deferred enhancement…」改寫為描述已實作的 §6 涵蓋檢查。新增 `from loop_apidoc.validate.coverage import check_manifest_coverage` import。

由於 `validate_run_dir` 已載入 `manifest.json` 並傳入 `validate_outputs`，standalone `validate` 指令自動受惠，無需改動 `loader.py`。

## 修正循環互動（確認無副作用）

- UNREADABLE（ERROR, `SOURCE_UNVERIFIED`）→ `classify_issue` = `UNFIXABLE`。若為唯一 error，`actionable_codes` 為空 → 循環 early-stops（`EARLY_STOPPED`），不浪費額度。與 RE_QUERY error 混合時，循環處理 RE_QUERY 後此 error 仍在 → 最終 `FAILED` 或在僅剩 unfixable 時 early-stop。
- UNSUPPORTED（WARNING）→ 不影響 `ValidationReport.ok`，永不進入 `actionable_codes`（其只收 ERROR），不觸發任何修正輪次。

## 行為對照

| manifest 狀態 | 改動前 | 改動後 |
| --- | --- | --- |
| 含 UNREADABLE 來源 | 驗證不檢視；報告無此 issue | 1 個 ERROR `SOURCE_UNVERIFIED`，阻擋驗證通過 |
| 含 UNSUPPORTED 來源 | 同上 | 1 個 WARNING `SOURCE_UNVERIFIED`，不阻擋 |
| 含 DUPLICATE 來源 | 同上 | 不浮現（行為不變） |
| 乾淨／空 manifest（僅 PENDING） | 0 個 coverage issue | 0 個 coverage issue（不變） |

## 測試策略

新增 `tests/validate/test_coverage.py`：

- UNREADABLE 來源 → 恰 1 個 issue，severity `ERROR`，code `SOURCE_UNVERIFIED`，location == 該來源 `relative_path`。
- UNSUPPORTED 來源 → 恰 1 個 issue，severity `WARNING`，evidence 含格式字串。
- DUPLICATE 來源 → 0 個 issue。
- 乾淨 manifest（僅 PENDING／空 `local_sources`）→ 0 個 issue。
- 混合（1 UNREADABLE + 1 UNSUPPORTED + 1 DUPLICATE）→ 2 個 issue，計數與嚴重度正確。

回歸保護：

- 掃描既有 `tests/validate/` 與 `tests/integration/` 中呼叫 `validate_outputs` 或 `validate_run_dir` 的 fixture，確認沒有任何測試以「帶 UNREADABLE／UNSUPPORTED 來源的 manifest」卻斷言 0 issue。多數測試使用空或僅 PENDING 的 manifest，不受影響；若發現有受影響者，更新其期望值。
- `uv run pytest -q` 全綠（基線 203 passed + 1 skipped，預期隨新測試上升）。

## 文件與收尾

- 更新 `validate_outputs` docstring（移除 deferred 字樣）。
- 更新 plan-sequence memory 的 Plan 6 deferral #2，標註 manifest-coverage 已實作（UNREADABLE→ERROR／UNSUPPORTED→WARNING／DUPLICATE 不浮現，code=SOURCE_UNVERIFIED），URL-coverage 仍為未來工作。

## 替代方案（已評估、未採用）

- **新增 `MANIFEST_COVERAGE` IssueCode**：語義最乾淨，但需動 enum + `classify_issue` 映射 + §9.5 code 清單；對單一檢查而言表面積過大（YAGNI）。複用 `SOURCE_UNVERIFIED` 在語義與修正循環分類上皆相符。
- **複用 `REQUIRED_INFO_MISSING`**：會在修正循環映射為 `RE_QUERY` → 觸發 NotebookLM 重查，但重查無法修復本機檔案問題（分類錯誤、浪費額度）。否決。

## 非目標

- URL 來源 coverage（`url_sources` 的 http_status 失敗）。
- DUPLICATE 浮現。
- 新增 §9.5 IssueCode 或修改 `classify_issue`。
- 改動 `loader.py` / `validate_run_dir`（已自動傳入 manifest）。
