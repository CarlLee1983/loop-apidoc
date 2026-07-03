# sole_source 升級為「唯一文件」：URL + 快照檔摺疊

- 日期:2026-07-04
- 狀態:已核准(brainstorming 完成)
- 相關:`docs/superpowers/plans/2026-07-03-url-source-coverage.md`(URL 涵蓋檢核)、merge f8115f3

## 問題

`loop_apidoc/plan/classify.py` 的 `sole_source` 後備只在「manifest 恰好一個可用來源」時生效:引註 locator 寫章節名(非檔名)的 plan item,單一來源時仍可歸屬,多來源時嚴格比對落空 → `SOURCE_UNVERIFIED`(error)→ run FAIL。

而 URL 抓取 SOP(`skills/loop-apidoc/reference/url-fetching.md`)要求把抓到的頁面存成本地快照檔、同時把入口 URL 傳給 `--url`;新的 `--url-coverage` guard 又強制搭配 `--url`。結果:**每個照 SOP 走的 URL run,同一份文件被算成兩個來源(快照檔 + URL),`sole_source` 永遠失效**。實測 line-pay-online-v3 benchmark:不帶 `--url` PASS(6 warning),帶 `--url` 爆 66 個 `SOURCE_UNVERIFIED` error,而該 66 項內容其實全部真的在來源裡——fail-closed 的假陰性,可用性成本。

另 `reference/extraction-schemas.md` 明寫 `source` 可引「章節/頁碼/URL anchor」,與分類器只認檔名/完整 URL 的行為有落差;本設計以摺疊文件數修復最常見的觸發鏈,不改嚴格比對本身。

## 決策(brainstorming 定案)

1. **配對依據 = coverage.json 帳本**(`results[].file` 的明確映射)。無帳本 → 完全維持現狀,不用目錄慣例或「1 檔 + 1 URL」盲摺疊等啟發式。
2. **接線方式 = 寫進 manifest**:`UrlSource` 加 optional 欄位,classify 維持純函式只吃 manifest;配對關係落地到 `manifest.json`,下游(diff/foundry/人眼)可追溯。

## 設計

### 1. Manifest schema(additive)

`loop_apidoc/manifest/models.py` 的 `UrlSource` 加:

```python
snapshot_file: str | None = None  # 該 URL 快照對應的本地來源 relative_path
```

舊 manifest.json 讀回不受影響(預設 None)。

### 2. 回填邏輯(assemble.py)

`run_assemble_pipeline` 在 `build_manifest` 之後、build plan 之前,若本次有 coverage 帳本:

- 對每個 `url_source`,在帳本 `results` 中找 URL 相符的條目。URL 比對用既有 `_normalize_url`(去 fragment、去尾斜線;自 `preparation/assess.py` 移到 `preparation/coverage.py` 成為公開的 `normalize_url`,兩處共用,避免重複實作)。
- 只有帶 `file` 的 result 提供映射(`fetched` / `fetched_rendered` / `auth_required` 且 `file` 非 null)。
- 帳本 `file` 路徑(相對 work dir,如 `sources/online-api-v3-overview.md`)對 manifest `relative_path`(相對 sources_root)採**路徑後綴匹配**:帳本路徑以 `/` 為界、以某本地來源的 `relative_path` 結尾即命中。
- **須唯一命中才配對**;零命中或多重命中(含多個 result 映到不同檔) → 維持 `None`,不報錯——配對是歸屬優化,不是輸入錯誤,寧可不摺疊也不誤配。
- 沒傳 `--url-coverage` → 此步驟整段跳過,行為與現狀完全相同。

### 3. sole_source(classify.py)

文件數定義改為:

```
documents = 可用本地來源
          + [u for u in url_sources
             if u.snapshot_file 未指向任何可用本地來源]
```

即 `snapshot_file` 指向一個可用(supported 且非 UNREADABLE/UNSUPPORTED/DUPLICATE)本地來源的 URL **不另計一份文件**。恰好 1 份文件時回傳其識別字串;摺疊配對的情況回傳**本地檔的 relative_path**(內容實際所在、provenance 可指向的 artifact),不回傳 URL。

`match_manifest_source` 的嚴格比對邏輯**完全不動**:locator 明確寫出檔名或 URL 時行為不變。

### 4. 效果與非目標

- line-pay 情境(1 快照檔 + 1 entry URL + 帳本)→ 1 份文件 → 章節式 locator 歸屬回快照檔 → PASS 恢復。
- 多頁快照(如 ecpay 28 頁 + 1 entry URL)→ 即使 entry URL 摺疊仍是多文件 → 維持嚴格比對。語意正確,**非本設計要修的對象**;多來源 run 的 locator 仍須寫出檔名或 URL。
- 不改驗證閘(severity 決定 FAIL)、不改 warning-only 的 url_coverage phase、不改 `match_manifest_source`。

### 5. 錯誤處理

- 帳本本身的格式錯誤已由 `load_coverage` fail-loud(exit 2、無孤兒 run dir),本設計不新增錯誤路徑。
- 配對失敗(路徑對不上、模糊)一律靜默維持 None:此時行為退回現狀(嚴格比對),不會比今天更差。

### 6. 測試(TDD)

- **classify 單元測試**:摺疊後唯一文件 → sole_source 回傳本地檔;snapshot_file 指向不可用來源 → 不摺疊;無 snapshot_file → 現狀;多檔多 URL → 仍 None。
- **assemble 回填測試**:帳本映射正確寫進 manifest.json 的 `url_sources[].snapshot_file`;後綴匹配、正規化 URL 匹配、零/多重命中 → None;無 `--url-coverage` → 欄位維持 None。
- **整合測試**:以 line-pay 形狀(單快照檔 + entry URL + 帳本、章節式 locator)驗證「加 `--url` + `--url-coverage` 後 run 仍 PASS」;對照無帳本時維持現狀(UNVERIFIED)。
- 既有回歸:全套測試 + benchmark harness 不變。
