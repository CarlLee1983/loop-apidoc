# 設計文件：URL 來源完整撈取與涵蓋率檢核（防遺漏）

## 1. 背景與問題

pipeline 支援公開 URL 作為來源，但目前 `skills/loop-apidoc/SKILL.md` 對 URL 撈取只規定「每個 URL 抓一次、存到 `<WORK>/url_sources/`」，**撈取方法完全由 agent 臨場決定**。實務上（benchmarks 經驗）已知的失效模式：

1. **頁面級遺漏**：文件入口頁下散落數十個子頁，連結發現不完整，只抓到一部分。
2. **內容級遺漏**：JS SPA 頁面未經瀏覽器渲染就被存檔，內容是空殼或半頁（tab／折疊區塊未展開）。
3. **無聲遺漏**（最危險）：以上兩種發生後沒有任何訊號——agent 與使用者都以為抓齊了，缺漏直接變成下游 `missing` 或錯誤產物。

本設計的核心不是「怎麼抓」，而是「**怎麼知道抓齊了**」：讓遺漏變成看得見、可檢核的 finding，符合 pipeline 的 fail-closed 精神。

## 2. 定位與架構分工

沿用既有 agent-native 分工——agent 做需要理解與瀏覽器的工作，CLI 做 deterministic 檢核：

| 層 | 職責 | 改動 |
| --- | --- | --- |
| Skill（SOP） | 撈取決策樹：發現 → 確認 → 撈取 → 回報 | 新增 `skills/loop-apidoc/reference/url-fetching.md`；`SKILL.md` 編排層加一行指引（維持漸進揭露、Codex 可攜） |
| Agent 產物 | 機器可讀的涵蓋率清單 | 新增 `<WORK>/url_sources/coverage.json`（agent 撰寫） |
| CLI（deterministic） | 「應抓 vs 實抓」比對，出 finding | `loop_apidoc/preparation/` 新增一個 phase 讀取並檢核 `coverage.json` |

「抓齊了沒」不靠 agent 自律，而是由 preparation 階段的程式閘門把關。

## 3. 撈取 SOP（`reference/url-fetching.md` 的內容骨架）

### 3.1 發現（Discovery）

1. 抓入口頁；若偵測為 JS SPA 空殼（見 3.5），改用 Playwright 渲染後再解析。
2. 以**導覽樹（sidebar／選單）為權威「應抓清單」**：選單列出的每一頁都應抓到，選單外不追（避免爆量）。
3. 若站點提供 `sitemap.xml`，取入口路徑子樹與導覽樹做交叉比對補漏；沒有則不強求。

### 3.2 確認（Confirm，人在迴圈）

開抓前，把應抓清單（頁面標題＋URL＋層級）列給使用者增刪確認。使用者移除的頁記為 `skipped_by_user`。非互動情境（如 CI）跳過確認、直接以發現結果為準，並在 coverage 註記未經人工確認。

### 3.3 撈取（Fetch）

- 每頁優先用 defuddle-cli 抓取（省 token）；命中空殼偵測或內容過短 → 升級 Playwright 渲染重抓。
- 每頁存入 `<WORK>/url_sources/`，記錄抓取方式（`defuddle` / `playwright`）與結果狀態。
- 重抓後仍為空殼 → 保留 `empty_suspect` 狀態，不得以推測內容補齊。

### 3.4 回報（Coverage）

撈取結束後寫出 `url_sources/coverage.json`（schema 見 §4）。

### 3.5 空殼偵測（heuristics）

任一命中即視為疑似空殼，升級渲染重抓：

- 正文（去除 nav／footer 後）字數低於門檻
- 頁面僅剩 loading／skeleton 標記或空 `<div id="root">` 類容器
- 正文長度與 `<title>`／導覽選單規模比例顯著異常

### 3.6 登入驗證資源

安全紅線：**pipeline 與 agent 永不經手、不記錄帳密**。

- **互動 session**：以 Playwright 開真瀏覽器，由**使用者親手完成登入**（含 2FA），登入後 agent 於同一 session 依已確認清單逐頁抓取。
- **非互動、或登入流程過於複雜**（企業 SSO、裝置綁定）：該頁標為 `auth_required`，由使用者自行登入後另存（HTML／PDF）放入本地 sources，pipeline 當一般本地檔處理。
- 不做憑證自動化（env token／cookie 注入）——YAGNI，遇到實際需求再另行設計。

## 4. `coverage.json` schema

```json
{
  "entry_url": "https://docs.example.com/api/",
  "confirmed_by_user": true,
  "expected": [
    { "url": "https://docs.example.com/api/auth", "title": "驗證", "source": "nav" }
  ],
  "results": [
    {
      "url": "https://docs.example.com/api/auth",
      "status": "fetched",
      "file": "url_sources/auth.md",
      "method": "defuddle"
    }
  ]
}
```

- `expected[].source`：`nav` | `sitemap` | `user`（使用者於確認階段新增）
- `results[].status`：`fetched` | `fetched_rendered` | `empty_suspect` | `fetch_failed` | `auth_required` | `skipped_by_user`
- `results[].method`：`defuddle` | `playwright`（`auth_required`／`fetch_failed`／`skipped_by_user` 可省略 `file`／`method`）

## 5. Preparation 新 phase：URL coverage 檢核

於 `loop_apidoc/preparation/assess.py` 新增一個 phase（僅在 run 有 URL 來源時啟用），全部為 **warning** 級——遺漏是「誠實回報的缺口」，不擋 pipeline，但必須看得見：

| 情況 | Finding（warning） |
| --- | --- |
| `expected` 中有頁 `fetch_failed` 或 `empty_suspect` | 列出缺頁 URL，訊息指引重抓或改用渲染 |
| `auth_required` 且 sources 內無對應本地替代檔 | 指引「登入後另存頁面放入 sources」 |
| 有 `--url` 來源但 `url_sources/coverage.json` 不存在 | 提示未按 SOP 撈取，涵蓋率未知 |
| `confirmed_by_user: false` | 註記應抓清單未經人工確認 |

不新增 error 級 finding；既有 severity 閘（error 才 FAIL）不變。

## 6. 不在本次範圍

- 憑證自動化（token／cookie／帳密注入）
- 通用全站爬蟲（跨 domain、無界深度追連結）
- 在 CLI 內建瀏覽器渲染（playwright Python 依賴）——渲染一律由 agent 透過 Playwright MCP 執行
- 對既有 `manifest`／`generate`／`validate` 行為的任何變更

## 7. 測試策略

- **preparation 新 phase**：TDD 單元測試覆蓋各狀態組合——涵蓋齊全→無 finding、`fetch_failed`／`empty_suspect`→warning、`auth_required` 有無本地替代檔兩態、coverage.json 缺檔→warning、無 URL 來源→phase 不啟用。
- **coverage.json 邊界**：格式錯誤（缺 key、未知 status）時 fail loudly（比照 `input_schema.py` 的 pydantic 邊界驗證模式）。
- **SOP 文件**：屬 skill 指引，於下一次真實 e2e（選一個多子頁文件站）人工驗證發現→確認→撈取→回報全流程。
