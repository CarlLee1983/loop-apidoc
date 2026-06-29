# 設計文件：HTML 架構圖視覺化增強

本文件定義 `docs/architecture-manual.html` 的架構圖增強設計。目標是在 HTML 手冊中提供比 Mermaid 更直覺、可互動、易理解的模組流程圖，同時保留 `docs/ARCHITECTURE.md` 的 Mermaid 作為純文字 source 與 fallback。

## 1. 目標與非目標

### 目標

- 讓 HTML 手冊中的「套件邊界與模組架構」從 Mermaid 草圖升級為原生 HTML/CSS/SVG/JS 視覺化架構地圖。
- 保留 Markdown Mermaid，讓架構仍能在 GitHub、終端或純文字閱讀環境中被理解。
- 讓讀者能快速看懂三件事：
  - `cli.py` 對外暴露哪些入口。
  - `agentcli/` 如何串起 manifest、extraction、plan、generate、validate、run。
  - 哪些模組是純邏輯，哪些模組擁有本機 I/O side effect。
- 維持單一自包含 HTML，不新增前端框架、build step 或外部圖表庫。

### 非目標

- 不重寫 `docs/ARCHITECTURE.md` 的 Mermaid 圖。
- 不改變架構內容、模組命名或 pipeline 語意。
- 不把文件站改成 SPA 或引入 Vite/React/Next.js。
- 不新增 runtime dependency。

## 2. 現況

`docs/architecture-manual.html` 目前已經有互動式 pipeline dashboard：左側步驟導覽、右側動態細節面板、深淺色主題與 responsive layout。

但底部「套件邊界與模組架構」仍直接嵌入 Mermaid：

- HTML 載入 Mermaid CDN。
- 模組圖只能呈現節點與箭頭，缺少可點選細節。
- `generate/` 與 `run/` 的 I/O 邊界雖有樣式標記，但不夠醒目。
- 閱讀者無法從圖上直接看出模組群組、side effect 邊界與公開 seam。

## 3. 設計概念

HTML 手冊使用專用的「架構地圖」取代 Mermaid runtime。Markdown 手冊繼續保留 Mermaid 作為 source/fallback。

架構地圖採三層視覺結構：

1. **入口層**：`cli.py` 與四個公開命令。
2. **編排層**：`agentcli/` 作為 assemble/preprocess 的後段編排中心。
3. **模組層**：依職責分群顯示 `manifest/`、`extraction/`、`plan/`、`generate/`、`validate/`、`run/`。

各模組以卡片呈現，使用 SVG connector 表示主要呼叫與資料方向。讀者點選模組後，旁邊的說明面板顯示該模組職責、公開 seam、輸入、輸出與 side-effect 分類。

## 4. 互動行為

### 4.1 預設狀態

- 預設選中 `agentcli/`，因為它是目前 HTML 底部架構圖的主要理解中心。
- 說明面板顯示：
  - 職責：組裝 agent 寫出的 JSON、串接 manifest -> plan -> generate -> validate。
  - 分類：Controller / orchestration。
  - side effect：由子步驟與 run/generate 承擔，本身作為流程入口。

### 4.2 點選模組

點選任一模組卡片時：

- 卡片加上 active 樣式。
- 相關 connector 加強顯示。
- 說明面板更新為該模組資料。
- 若模組是 `generate/` 或 `run/`，顯示 File I/O boundary 標籤。
- 若模組是 `plan/` 或 `validate/`，顯示 Pure logic 標籤。

### 4.3 手機版

在窄螢幕中：

- 架構地圖從多欄改為單欄分段。
- SVG connector 可簡化或隱藏，改由卡片順序與群組標題維持可讀性。
- 說明面板置於模組卡片下方。
- 所有文字必須在卡片內換行，不得重疊或溢出。

## 5. 視覺規範

沿用 `architecture-manual.html` 既有變數：

- `--bg-base`
- `--bg-card`
- `--bg-inset`
- `--border-main`
- `--border-active`
- `--text-primary`
- `--text-secondary`
- `--accent`
- `--color-io`
- `--color-pure`
- `--color-agent`

新增元件只使用既有色票衍生樣式，不建立另一套主題。卡片 border radius 控制在既有風格內，避免和上方 dashboard 不一致。

建議分類：

| 分類 | 模組 | 樣式意圖 |
| --- | --- | --- |
| Entry | `cli.py` | 中性入口，強調公開命令 |
| Controller | `agentcli/` | 編排中心，使用 accent |
| Agent data | `extraction/` | agent JSON 邊界 |
| Pure logic | `manifest/`, `plan/`, `validate/` | 穩定、可測試 |
| File I/O | `generate/`, `run/` | 明確標記 side effect |

`manifest/` 會讀來源目錄與 URL 清單，視覺分類可標為 Local I/O / source scan；但在圖上仍靠近 pure pipeline，避免誤導它是輸出寫入出口。

## 6. 資料模型

新增靜態資料物件 `moduleDataset`，與既有 `dataset` 模式一致：

```javascript
const moduleDataset = {
  agentcli: {
    title: "agentcli/",
    role: "assemble + preprocess",
    badgeClass: "agent",
    badgeLabel: "Controller",
    description: "...",
    seam: "run_assemble_pipeline(...)",
    inputs: "inventory.json, endpoints/*.json, sources, urls",
    outputs: "run-dir, --json report",
    sideEffect: "Delegates writes to generate/ and run/"
  }
};
```

HTML 模板只負責 layout，模組內容集中在資料物件中，避免文案散落在 DOM。

## 7. 技術實作邊界

- 移除 `architecture-manual.html` 的 Mermaid `<script type="module">` CDN import。
- 將底部 Mermaid `<div class="mermaid">` 替換為：
  - `architecture-map` 容器。
  - `svg.architecture-connectors` connector layer。
  - module card buttons。
  - module detail panel。
- 使用原生 JS 綁定 click event。
- 使用 `button` 或具等效 keyboard 操作語意的元素，確保基本可及性。
- 保留現有上方 pipeline dashboard，不重構既有互動邏輯。

## 8. 驗證策略

最小驗證：

- 靜態檢查 HTML 中不再含 Mermaid CDN import。
- 開啟 `docs/architecture-manual.html`，確認無 console error。
- 在桌面寬度確認：
  - 架構圖可見。
  - 點選模組會更新細節。
  - `generate/` 與 `run/` 的 I/O 標籤醒目。
- 在手機寬度確認：
  - 模組卡片不重疊。
  - 文字不溢出。
  - 詳細面板仍可讀。

若有瀏覽器自動化工具可用，使用 local file 或靜態 server 截圖檢查 desktop/mobile 兩種 viewport。

## 9. 驗收標準

- `docs/ARCHITECTURE.md` 的 Mermaid 圖仍保留。
- `docs/architecture-manual.html` 不再依賴 Mermaid runtime。
- HTML 架構圖由原生 HTML/CSS/SVG/JS 呈現。
- 模組圖能表達入口、編排、資料流與 I/O 邊界。
- 點選模組可更新旁側或下方說明。
- 桌面與手機 viewport 均無明顯重疊、溢出或空白圖。
- 無新增 dependency。
