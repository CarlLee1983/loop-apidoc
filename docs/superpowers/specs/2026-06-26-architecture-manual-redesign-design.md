# 設計文件：架構手冊 (architecture-manual.html) 互動式儀表板重構

本文件定義 `docs/architecture-manual.html` 的視覺與互動重構設計。目標是擺脫傳統將 Markdown 直接轉譯成 HTML 的單調排版，以及流於俗氣的「AI 包殼味」霓虹設計，改用符合現代高品質工程美學（類似 Tailwind/Shadcn/Stripe）的互動式 Pipeline 儀表板，提升人類閱讀時的直覺性與檢索效率。

---

## 1. 系統定位與目標

* **受眾**：開發人員、架構師與系統操作者。
* **痛點**：舊版手冊僅是 Markdown 轉成 HTML，雖然有 Mermaid 靜態流程圖，但資訊層次扁平。程式碼 Seams（進入點與純邏輯）與實際資料流（輸入/輸出）分散在表格中，閱讀時不易對齊。
* **目標**：
  * **高直覺視覺**：左側展示直觀的 Pipeline 時間線與流程狀態，右側展示詳盡的說明。
  * **程式碼/資料對齊**：點擊 Pipeline 的任一步驟，立即可於右側分頁動態檢視其職責與程式碼公開介面（Seams）對照。
  * **純原生技術**：不引入 Vite/Next.js 等複雜前端框架，維持單一自包含 HTML 檔案，載入極速且便於本機離線開啟。

---

## 2. 介面架構設計 (UX/UI)

新版 `architecture-manual.html` 採用兩欄式儀表板配置：

```
+-------------------------------------------------------------------------+
|  loop-apidoc 架構說明手冊                                                 |
+-------------------------------------------------------------------------+
|  [ 左側：時間線導覽 (360px) ]        [ 右側：動態細節面板 (Flex 1) ]       |
|                                                                         |
|  ( 垂直貫穿時間線 )                   +-------------------------------+ |
|                                       | [ 詳細說明 ]   [ 系統對照 ]     | |
|  ● Prep 人工前置作業                   +-------------------------------+ |
|    |                                  |                               | |
|  ● Step 01 來源掃描 (Active) --------> | - 標題與類型標籤 (如 Local I/O) | |
|    |                                  | - 核心職責、規格描述             | |
|  ● Step 02 資料擷取                    | - [Tab 系統對照模式下]          | |
|    |                                  |   - 公開 Seam: build_manifest()| |
|  ● Step 03 規格化計畫                  |   - 輸入資料: --sources <path> | |
|    |                                  |   - 輸出產物: manifest.json    | |
|  ● Step 04 生成產物                    +-------------------------------+ |
|    |                                                                    |
|  ● Step 05 產物驗證                                                      |
|    |                                                                    |
|  ● Step 06 修正迴圈                                                      |
+-------------------------------------------------------------------------+
```

### 2.1 左側導覽列 (Timeline Panel)
* **導覽線**：以 `1.5px solid var(--border-main)` 繪製垂直的時間線。
* **流程節點 (Cards)**：
  * 每個步驟是一個卡片元件，包含步驟名稱、序號、與專屬的 **SVG 圖示**。
  * 游標移入時微幅上浮 `translateY(-1px)` 並加深邊框。
  * 選中狀態 (Active) 邊框變為**靛藍色 (Indigo)**，並有淡色背景。

### 2.2 右側細節面板 (Detail Panel)
* **雙分頁 (Tabbed Navigation)**：
  * **詳細說明 (Overview)**：展示步驟描述、核心機制說明與設計考量。
  * **系統對照 (Technical)**：展示公開 Seam 介面（含程式碼高亮）、輸入參數、輸出檔案路徑。
* **分類徽章 (Badge Pill)**：
  * `Manual` (黃色)：人工前置作業。
  * `Local I/O / Network I/O / File Output` (藍色)：帶有 side-effect 的 I/O 操作。
  * `Pure Logic / Controller` (綠色)：純函數邏輯，利於單元測試。

### 2.3 響應式佈局 (Responsive)
* 當螢幕寬度小於 `900px` 時，左右兩欄式佈局自動轉為單欄式垂直堆疊，確保在平板與行動裝置上的閱讀體驗。

---

## 3. 色調與視覺規範 (Theme Style)

採用高對比、低飽和度的現代科技灰階色調，提供 OS 自動偵測的淺色 (Light) 與深色 (Dark) 雙色配置：

| 變數 | 淺色模式 (Light Mode) | 深色模式 (Dark Mode) |
| --- | --- | --- |
| 頁面背景 `--bg-base` | `#f8fafc` (鋅灰) | `#0b0f19` (深 slate 藍) |
| 卡片背景 `--bg-card` | `#ffffff` (純白) | `#111827` (深灰) |
| 框線顏色 `--border-main` | `#e2e8f0` | `#1f2937` |
| 強調色 (Active) `--accent` | `#4f46e5` (Stripe 靛藍) | `#6366f1` (亮靛藍) |
| 選中背景 `--accent-soft` | `#e0e7ff` | `rgba(99, 102, 241, 0.15)` |

---

## 4. 資料模型與轉譯機制

儀表板採用**資料驅動 (Data-Driven)** 架構。手冊中所有步驟的詳細文案都以靜態 JavaScript Object 格式存儲：

```javascript
const dataset = {
  prep: {
    num: "PREP",
    title: "人工前置作業",
    pillClass: "prep",
    pillLabel: "Manual",
    desc: "...",
    details: "...",
    seam: "N/A",
    inputs: "...",
    outputs: "..."
  },
  // scan, extract, plan, generate, validate, loop...
};
```

* **好處**：當需要修改說明文案或更新 Seam 函數時，只需修改 `dataset` 物件中的資料，完全不需更動 HTML/DOM 模板。

---

## 5. 原生互動實現

我們使用原生 JavaScript (Vanilla JS) 實現零依賴的流暢切換：

1. **節點點擊事件**：點選左側 `step-card` 後，更新 `currentKey`，並為該卡片加上 `.active` class（同時移除其他卡片的 active 狀態），然後呼叫 `updateDisplay()`。
2. **分頁切換事件**：點選右側頁籤，切換 `currentTab` 狀態，加上底線樣式，並呼叫 `updateDisplay()`。
3. **動態渲染 `updateDisplay()`**：清空右側 `detail-content-area`，依據選定的 `currentKey` 與 `currentTab` 動態組裝 HTML 字串並寫入。

---

## 6. 原先 ARCHITECTURE.md 其餘內容之整合

原本 `ARCHITECTURE.md` 包含的其餘文字：
1. **套件邊界圖**（使用 Mermaid 渲染）：我們將其保存在儀表板最下方，提供獨立區塊，並以原生的 CSS 進行區塊美化。
2. **來源追溯與驗證對齊文字說明**：整合進 Step 05（產物驗證）的詳細說明與核心機制中。
3. **擷取查詢分段 (01-10)**：整合進 Step 02（資料擷取）的核心機制說明中，點選即可查看 10 大查詢階段。

---

## 7. 驗證與驗收標準 (Success Criteria)

* [ ] 檔案為單一 `.html` 格式，無外部 CSS/JS 庫依賴（除了 Mermaid 圖表載入）。
* [ ] 點選左側任一 Pipeline 步驟，右側詳細說明與系統對照分頁能即時反應。
* [ ] 提供淺色/深色模式，符合 `@media (prefers-color-scheme)` 偵測。
* [ ] 在行動版/窄螢幕下，佈局能自適應堆疊，且可流暢操作。
