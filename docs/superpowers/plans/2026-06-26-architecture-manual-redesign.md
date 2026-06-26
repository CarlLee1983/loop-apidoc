# Architecture Manual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `docs/architecture-manual.html` into a premium, interactive pipeline dashboard with a dynamic steps navigation and dual-tab detail inspector.

**Architecture:** A static HTML file using CSS custom variables for light/dark OS detection, CSS grid for responsive layout, and Vanilla JavaScript with a clean data-driven model to render steps dynamically without any third-party dependencies.

**Tech Stack:** HTML5, Vanilla CSS, Vanilla JavaScript, Mermaid.js (via CDN).

---

### Task 1: Setup HTML Document Shell & Theme variables

**Files:**
- Modify: `docs/architecture-manual.html`

- [ ] **Step 1: Setup `<head>` and CSS theme variables**
Update the `<head>` of `docs/architecture-manual.html` with clean document titles, responsive meta tags, and high-fidelity zinc-based CSS variables supporting prefers-color-scheme.

```html
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>架構手冊 · loop-apidoc</title>
<style>
  :root {
    --bg-base: #f8fafc;
    --bg-card: #ffffff;
    --bg-inset: #f1f5f9;
    --border-main: #e2e8f0;
    --border-active: #6366f1;
    
    --text-primary: #0f172a;
    --text-secondary: #475569;
    --text-muted: #94a3b8;
    
    --accent: #4f46e5;
    --accent-hover: #4338ca;
    --accent-soft: #e0e7ff;
    
    --color-manual: #d97706;
    --color-io: #3b82f6;
    --color-pure: #10b981;
    
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif;
    --font-mono: "Fira Code", ui-monospace, SFMono-Regular, monospace;
    
    --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
    --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -4px rgba(0, 0, 0, 0.05);
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --bg-base: #0b0f19;
      --bg-card: #111827;
      --bg-inset: #1f2937;
      --border-main: #1f2937;
      --border-active: #818cf8;
      
      --text-primary: #f9fafb;
      --text-secondary: #d1d5db;
      --text-muted: #6b7280;
      
      --accent: #6366f1;
      --accent-hover: #4f46e5;
      --accent-soft: rgba(99, 102, 241, 0.15);
      
      --color-manual: #fbbf24;
      --color-io: #60a5fa;
      --color-pure: #34d399;
      
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.5);
      --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
      --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
    }
  }

  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin: 0;
    background: var(--bg-base);
    color: var(--text-primary);
    font-family: var(--font-sans);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }
</style>
</head>
```

- [ ] **Step 2: Commit styling base**
```bash
git add docs/architecture-manual.html
git commit -m "docs: setup head structure and CSS variables for manual redesign"
```

---

### Task 2: Implement Layout & Card Styles

**Files:**
- Modify: `docs/architecture-manual.html`

- [ ] **Step 1: Add layout and component CSS classes**
Add core CSS layout definitions to target 2-column dashboard grid, vertical timeline line, timeline cards, badge pill tags, tabs headers, metadata tables, and bottom panels.

```css
/* Add inside <style> tag */
.layout {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem 1.5rem 6rem;
}

.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border-main);
  padding-bottom: 1rem;
  margin-bottom: 2rem;
}

.top-bar h1 {
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0;
}

.top-bar .back-link {
  font-size: 0.85rem;
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
}
.top-bar .back-link:hover {
  text-decoration: underline;
}

.dashboard {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 2rem;
  margin-bottom: 3rem;
}

@media (max-width: 900px) {
  .dashboard {
    grid-template-columns: 1fr;
  }
}

.timeline-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-main);
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: var(--shadow-sm);
  position: relative;
}

.timeline-line {
  position: absolute;
  left: 2.35rem;
  top: 2rem;
  bottom: 2rem;
  width: 2px;
  background: var(--border-main);
  z-index: 1;
}

.timeline-steps {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.step-card {
  background: var(--bg-card);
  border: 1px solid var(--border-main);
  border-radius: 12px;
  padding: 0.75rem 1rem;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 1rem;
}

.step-card:hover {
  border-color: var(--text-secondary);
  transform: translateY(-1px);
}

.step-card.active {
  border-color: var(--border-active);
  background: var(--accent-soft);
  box-shadow: var(--shadow-md);
}

.step-icon {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 8px;
  background: var(--bg-inset);
  border: 1px solid var(--border-main);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-secondary);
  transition: all 0.2s ease;
}

.step-card.active .step-icon {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.step-card-content {
  flex: 1;
}

.step-card-num {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
}

.step-card.active .step-card-num {
  color: var(--accent);
}

.step-card-title {
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--text-primary);
  margin-top: 0.1rem;
}

.detail-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-main);
  border-radius: 16px;
  padding: 2rem;
  box-shadow: var(--shadow-md);
  display: flex;
  flex-direction: column;
}

.tab-header {
  display: flex;
  gap: 1.5rem;
  border-bottom: 1px solid var(--border-main);
  padding-bottom: 0.75rem;
  margin-bottom: 1.5rem;
}

.tab-btn {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  position: relative;
  transition: color 0.2s ease;
}
.tab-btn:hover {
  color: var(--text-primary);
}
.tab-btn.active {
  color: var(--accent);
}
.tab-btn.active::after {
  content: '';
  position: absolute;
  bottom: -0.85rem;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--accent);
}

.detail-headline {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.detail-headline h3 {
  font-size: 1.25rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0;
}

.pill {
  font-size: 0.65rem;
  font-family: var(--font-mono);
  padding: 0.2rem 0.5rem;
  border-radius: 9999px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.pill.prep { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
.pill.io { background: #dbeafe; color: #1d4ed8; border: 1px solid #bfdbfe; }
.pill.pure { background: #d1fae5; color: #047857; border: 1px solid #a7f3d0; }

.detail-desc {
  font-size: 0.92rem;
  line-height: 1.7;
  color: var(--text-secondary);
  margin-bottom: 1.5rem;
}

.section-label {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-muted);
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
}

.info-card {
  background: var(--bg-inset);
  border: 1px solid var(--border-main);
  border-radius: 12px;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
  font-size: 0.9rem;
}

.info-card p, .info-card ul {
  margin: 0 0 0.5rem;
}
.info-card ul {
  padding-left: 1.25rem;
}
.info-card li {
  margin-bottom: 0.25rem;
}

.specs-list {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 0.75rem 1.5rem;
  font-size: 0.85rem;
  border-top: 1px solid var(--border-main);
  padding-top: 1.5rem;
}

.specs-label {
  font-weight: 700;
  color: var(--text-secondary);
}

.specs-value code {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  padding: 0.15rem 0.35rem;
  background: var(--bg-inset);
  border: 1px solid var(--border-main);
  border-radius: 6px;
  color: var(--accent);
}

.panel-bottom {
  background: var(--bg-card);
  border: 1px solid var(--border-main);
  border-radius: 16px;
  padding: 2rem;
  box-shadow: var(--shadow-sm);
  margin-bottom: 2rem;
}

.panel-bottom h2 {
  font-size: 1.2rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin-top: 0;
  margin-bottom: 1rem;
}

.footer {
  margin-top: 4rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border-main);
  color: var(--text-muted);
  font-size: 0.8rem;
  text-align: center;
}
```

- [ ] **Step 2: Commit layout CSS**
```bash
git add docs/architecture-manual.html
git commit -m "docs: implement responsive layout and UI component styles"
```

---

### Task 3: Build HTML Body Layout and Step Nodes

**Files:**
- Modify: `docs/architecture-manual.html`

- [ ] **Step 1: Write dashboard HTML structure**
Update the `<body>` of `docs/architecture-manual.html` with the top header, grid wrapper, timeline steps sidebar containing clean inline SVGs, details container, bottom sections for packages, and script loading.

```html
<body>
<div class="layout">
  <div class="top-bar">
    <h1>loop-apidoc 架構說明手冊</h1>
    <a href="operator-manual.html" class="back-link">← 操作者手冊</a>
  </div>

  <div class="dashboard">
    <!-- Left Timeline Navigation -->
    <div class="timeline-panel">
      <div class="timeline-line"></div>
      <div class="timeline-steps">
        <!-- Prep -->
        <div class="step-card" id="step-prep" onclick="selectStep('prep')">
          <div class="step-icon">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
            </svg>
          </div>
          <div class="step-card-content">
            <div class="step-card-num">Prep</div>
            <div class="step-card-title">人工前置作業</div>
          </div>
        </div>

        <!-- Step 01 -->
        <div class="step-card active" id="step-scan" onclick="selectStep('scan')">
          <div class="step-icon">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <div class="step-card-content">
            <div class="step-card-num">Step 01</div>
            <div class="step-card-title">來源掃描 (Scan)</div>
          </div>
        </div>

        <!-- Step 02 -->
        <div class="step-card" id="step-extract" onclick="selectStep('extract')">
          <div class="step-icon">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 4H6a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-2m-4-1v8m0 0l3-3m-3 3L9 8m-5 5h2.586a1 1 0 01.707.293l2.414 2.414a1 1 0 00.707.293h3.172a1 1 0 00.707-.293l2.414-2.414a1 1 0 01.707-.293H20" />
            </svg>
          </div>
          <div class="step-card-content">
            <div class="step-card-num">Step 02</div>
            <div class="step-card-title">資料擷取 (Extract)</div>
          </div>
        </div>

        <!-- Step 03 -->
        <div class="step-card" id="step-plan" onclick="selectStep('plan')">
          <div class="step-icon">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
            </svg>
          </div>
          <div class="step-card-content">
            <div class="step-card-num">Step 03</div>
            <div class="step-card-title">規格化計畫 (Plan)</div>
          </div>
        </div>

        <!-- Step 04 -->
        <div class="step-card" id="step-generate" onclick="selectStep('generate')">
          <div class="step-icon">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div class="step-card-content">
            <div class="step-card-num">Step 04</div>
            <div class="step-card-title">生成產物 (Generate)</div>
          </div>
        </div>

        <!-- Step 05 -->
        <div class="step-card" id="step-validate" onclick="selectStep('validate')">
          <div class="step-icon">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <div class="step-card-content">
            <div class="step-card-num">Step 05</div>
            <div class="step-card-title">產物驗證 (Validate)</div>
          </div>
        </div>

        <!-- Step 06 -->
        <div class="step-card" id="step-loop" onclick="selectStep('loop')">
          <div class="step-icon">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H18.5" />
            </svg>
          </div>
          <div class="step-card-content">
            <div class="step-card-num">Step 06</div>
            <div class="step-card-title">修正迴圈 (Loop)</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Right Detail Panel -->
    <div class="detail-panel">
      <div class="tab-header">
        <div class="tab-btn active" id="tab-overview" onclick="switchTab('overview')">詳細說明</div>
        <div class="tab-btn" id="tab-technical" onclick="switchTab('technical')">系統對照</div>
      </div>
      <div id="detail-content-area">
        <!-- Rendered dynamically -->
      </div>
    </div>
  </div>

  <!-- Bottom Section: Package Boundaries -->
  <div class="panel-bottom">
    <h2>套件邊界與模組架構</h2>
    <div class="mermaid">
      flowchart TD
          cli[cli.py<br/>Typer 進入點]

          cli --> doctor[doctor/<br/>唯讀環境檢查]
          cli --> manifest[manifest/<br/>掃描 + manifest]
          cli --> run[run/<br/>pipeline 編排]
          cli --> validate[validate/<br/>驗證 + 報告]

          run --> manifest
          run --> extraction[extraction/<br/>多輪查詢 + 答案保存]
          run --> plan[plan/<br/>規格化計畫 + 來源比對]
          run --> generate[generate/<br/>OpenAPI/MD/provenance]
          run --> validate

          extraction --> notebooklm[notebooklm/<br/>skill adapter + retry]
          doctor --> notebooklm
          plan --> manifest

          classDef io fill:#e0e7ff,stroke:#6366f1,stroke-width:2px;
          class generate,run io
    </div>
    <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 1rem; line-height: 1.6;">
      <strong>唯一檔案 I/O 出口</strong>：只有 <code>generate/</code> (<code>generate_outputs</code>) 與 <code>run/</code> (<code>run_pipeline</code>) 擁有寫入檔案權限；其餘模組均設計為無 Side-effects 的純函式，以簡化單元測試之複雜度。
    </div>
  </div>

  <div class="footer">
    由專案 Markdown 產生 · loop-apidoc · 來源依據式 API 文件 pipeline
  </div>
</div>

<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({ startOnLoad: true, theme: dark ? "dark" : "default", securityLevel: "loose" });
</script>
</body>
```

- [ ] **Step 2: Commit HTML template body**
```bash
git add docs/architecture-manual.html
git commit -m "docs: build HTML body structure, steps timeline sidebar, and bottom section"
```

---

### Task 4: Define Steps Dataset

**Files:**
- Modify: `docs/architecture-manual.html`

- [ ] **Step 1: Write Javascript Steps data store**
Embed the static `dataset` in a `<script>` tag inside `docs/architecture-manual.html` describing each steps' detail contents.

```html
<!-- Inside body before closing tag -->
<script>
  const dataset = {
    prep: {
      num: "PREP",
      title: "人工前置作業",
      pillClass: "prep",
      pillLabel: "Manual",
      desc: "在啟動自動化 CLI 工具前，操作者必須進行的前置準備工作（不屬於 CLI 本身）。包含在 NotebookLM 中建立一個專屬 Notebook、上傳所有 API 文件來源並取得分享連結，同時在本機保留一份完全對應的原始檔案目錄。",
      details: "<p>第一版支援的來源格式：PDF、Markdown、Word、OpenAPI JSON/YAML 及公開網頁 URL。</p><p>Notebook 必須可由本機瀏覽器登入的 Google 帳號存取；分享設定或帳號權限不足時，CLI 會在預檢階段失敗。</p>",
      seam: "N/A (手動前置操作)",
      inputs: "API 原始文件來源 (本機目錄)",
      outputs: "NotebookLM 分享連結, 本機對應目錄"
    },
    scan: {
      num: "STEP 01",
      title: "來源掃描 (Scan)",
      pillClass: "io",
      pillLabel: "Local I/O",
      desc: "透過 <code>loop-apidoc manifest</code> 掃描指定之本機來源目錄與公開 URL，詳細記錄各檔案的相對路徑、格式、大小、SHA-256 雜湊值與掃描時間。生成一份標準的來源清單檔案，作為後續所有 API 輸出項目追溯來源 (Provenance) 的依據。",
      details: "<p>在此階段，系統會過濾出不受支援的格式，自動偵測重複檔案，若發現檔案不可讀即觸發警告。此過程為純本機磁碟讀取。</p>",
      seam: "build_manifest(sources_root, urls, generated_at)",
      inputs: "--sources <目錄路徑>, --url <URL清單>",
      outputs: "manifest.json"
    },
    extract: {
      num: "STEP 02",
      title: "資料擷取 (Extraction)",
      pillClass: "io",
      pillLabel: "Network I/O",
      desc: "以分段擷取策略，透過自動化瀏覽器向 NotebookLM 進行多輪對答查詢（避免單次傳輸量過大導致 NotebookLM 漏失欄位或發生幻覺）。每一輪查詢（包含 10 個核心分段主題）皆為獨立 Session，因此程式會帶上已收集到的已知摘要、待確認項目與目標格式契約。",
      details: "<h4>10 大查詢分段主題</h4><ul><li>01 Notebook 與來源盤點</li><li>02 API 系統概覽與術語</li><li>03 環境 / base URL / 版本</li><li>04 驗證 / 授權 / 簽章</li><li>05 Endpoint 清單</li><li>06 逐 endpoint 細節（method/path/參數/req/resp/範例）</li><li>07 共用 schema / enum / 資料限制</li><li>08 錯誤碼與失敗行為</li><li>09 rate limit / timeout / retry / idempotency / webhook</li><li>10 來源衝突、缺漏、無法確認事項</li></ul><p>對答契約：盤點型階段（03-09）強迫要求 fenced JSON 區塊以利程式化解析；敘事型階段（01, 02, 10）則為純文字 Markdown。</p>",
      seam: "run_extraction(adapter, notebook_url, store, *, max_attempts=3)",
      inputs: "manifest.json, NotebookLM 筆記 URL",
      outputs: "extraction/queries.jsonl, extraction/answers/ (原始歷程)"
    },
    plan: {
      num: "STEP 03",
      title: "規格化計畫 (Build Plan)",
      pillClass: "pure",
      pillLabel: "Pure Logic",
      desc: "比對擷取到的 JSON/Markdown 資料與 sources 的 <code>manifest.json</code> 雜湊，交叉比對來源，將碎片化的資訊重構為單一結構的 <code>normalization-plan.json</code>。本階段屬於純函數轉譯邏輯，完全沒有檔案或網路 I/O，便於單元測試。",
      details: "<p>規格化計畫中會詳細指出哪些 API 欄位來源充足，哪些必要欄位在來源中缺失（需以預設值占位）或來源衝突（列入重新查詢清單）。</p>",
      seam: "build_normalization_plan(extraction, manifest)",
      inputs: "extraction/ 原始歷程資料, manifest.json",
      outputs: "plan/normalization-plan.json"
    },
    generate: {
      num: "STEP 04",
      title: "生成產物 (Generate)",
      pillClass: "io",
      pillLabel: "File Output",
      desc: "讀取規格化計畫與來源清單，正式產生交付之標準化產物檔案。本模組是整個 Pipeline 唯二具有檔案寫入（I/O）職責的出口之一。若有 OpenAPI 必填但來源缺失的欄位，會以最小合法占位值填入，並標記 <code>x-loop-status: missing-source</code>。",
      details: "<p>導出產物包含：</p><ul><li><b>openapi.yaml</b>: 標準 OpenAPI 3.1 規範檔案</li><li><b>api-guide.zh-TW.md</b>: 繁體中文 API 串接指南手冊</li><li><b>provenance.json</b>: 詳細記錄每個 OpenAPI 及 Markdown 欄位的來源追溯 mapping</li></ul>",
      seam: "generate_outputs(plan, manifest, run_dir)",
      inputs: "normalization-plan.json, manifest.json",
      outputs: "openapi.yaml, api-guide.zh-TW.md, provenance.json"
    },
    validate: {
      num: "STEP 05",
      title: "產物驗證 (Validate)",
      pillClass: "pure",
      pillLabel: "Pure Logic",
      desc: "對生成的 OpenAPI/Markdown/Provenance 執行四類嚴格驗證檢查。特別是<b>「禁止推測」</b>：任何進入輸出的內容都必須對應到 <code>provenance.json</code> 的 target 上，交叉比對是否有來源依據，嚴格阻絕推測與幻覺。",
      details: "<h4>四大驗證維度</h4><ul><li><b>結構驗證</b>：檢查 OpenAPI 規格合法性，端點必須包含 method、path 與至少一個 response</li><li><b>完整度驗證</b>：標記為 unverified 的來源、必要欄位缺失、不可讀來源皆會使驗證失敗</li><li><b>一致性驗證</b>：OpenAPI 與 Markdown / Provenance 的端點集合與 security 名稱必須完全一致</li><li><b>禁止推測驗證</b>：任何輸出項目必須對應 provenance 來源；無來源支持的內容視為違規</li></ul>",
      seam: "validate_outputs(plan, result, manifest) / validate_run_dir(run_dir)",
      inputs: "openapi.yaml, api-guide.zh-TW.md, provenance.json",
      outputs: "validation/report.json, validation/report.md"
    },
    loop: {
      num: "STEP 06",
      title: "修正迴圈 (Correction Loop)",
      pillClass: "pure",
      pillLabel: "Controller",
      desc: "工作流的校正控制器。如果驗證報告發現 ERROR，修正迴圈會依錯誤屬性分類並重試。上限最多 3 輪。如果三輪後仍有錯誤，或遇到 unfixable 問題，會提早早停退出並以非零碼退出 (Fail-Closed)。",
      details: "<h4>錯誤分類與修正策略</h4><ul><li><b>OPENAPI_INVALID / OUTPUT_MISMATCH</b>: 執行本地自動生成修正 (AUTO_FIX)</li><li><b>REQUIRED_INFO_MISSING</b>: 鎖定特定階段對 NotebookLM 發起重新擷取 (RE_QUERY)</li><li><b>SOURCE_UNVERIFIED / SOURCE_CONFLICT / UNSUPPORTED_ASSERTION</b>: 無法自動修正 (UNFIXABLE)，Pipeline 立即早停</li></ul>",
      seam: "run_correction_loop(plan, result, *, regenerate, requery, validate, max_rounds=3)",
      inputs: "validation/report.json",
      outputs: "修正重製後的產物檔或早停錯誤日誌"
    }
  };
</script>
```

- [ ] **Step 2: Commit Javascript dataset**
```bash
git add docs/architecture-manual.html
git commit -m "docs: embed static steps dataset into html manual"
```

---

### Task 5: Implement Dynamic Rendering Logic

**Files:**
- Modify: `docs/architecture-manual.html`

- [ ] **Step 1: Write Vanilla JavaScript rendering logic**
Add UI state variables `currentKey` and `currentTab`, define functions `selectStep(key)`, `switchTab(tab)`, and `updateDisplay()` inside `<script>` tag. Ensure initial loading runs correctly.

```javascript
/* Inside script tag below dataset definition */
let currentKey = 'scan';
let currentTab = 'overview';

function updateDisplay() {
  const data = dataset[currentKey];
  const container = document.getElementById('detail-content-area');
  
  if (currentTab === 'overview') {
    container.innerHTML = `
      <div class="detail-headline">
        <h3>${data.title}</h3>
        <span class="pill ${data.pillClass}">${data.pillLabel}</span>
      </div>
      <div class="detail-desc">${data.desc}</div>
      
      <div class="section-label">核心機制說明</div>
      <div class="info-card">
        ${data.details}
      </div>
    `;
  } else {
    container.innerHTML = `
      <div class="detail-headline">
        <h3>${data.title}</h3>
        <span class="pill ${data.pillClass}">${data.pillLabel}</span>
      </div>
      
      <div class="section-label">Pipeline 對照參數</div>
      <div class="specs-list">
        <div class="specs-label">公開 Seam 介面</div>
        <div class="specs-value"><code>${data.seam}</code></div>
        
        <div class="specs-label">輸入參數 / 檔案</div>
        <div class="specs-value"><code>${data.inputs}</code></div>
        
        <div class="specs-label">生成產物 / 輸出</div>
        <div class="specs-value" style="font-weight: 600;"><code>${data.outputs}</code></div>
      </div>
    `;
  }
}

window.selectStep = function(key) {
  currentKey = key;
  document.querySelectorAll('.step-card').forEach(card => {
    card.classList.remove('active');
  });
  const activeCard = document.getElementById('step-' + key);
  if (activeCard) {
    activeCard.classList.add('active');
  }
  updateDisplay();
};

window.switchTab = function(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('active');
  });
  const activeBtn = document.getElementById('tab-' + tab);
  if (activeBtn) {
    activeBtn.classList.add('active');
  }
  updateDisplay();
};

// Initial invocation
document.addEventListener('DOMContentLoaded', () => {
  updateDisplay();
});
```

- [ ] **Step 2: Commit rendering logic**
```bash
git add docs/architecture-manual.html
git commit -m "docs: write vanilla JS interactive rendering and switch routines"
```

---

### Task 6: Visual verification and Cleanup

**Files:**
- Modify: `docs/architecture-manual.html`

- [ ] **Step 1: Perform visual verification**
Open `docs/architecture-manual.html` in browser to make sure the interface renders correctly, all buttons respond on click, tab changes update details section properly, and dark/light prefers-color-scheme styles trigger correctly.

- [ ] **Step 2: Clean up temporary mockup files**
Run clean script or remove the session directory inside `.superpowers/brainstorm`.
Run:
```bash
rm -rf .superpowers/brainstorm/
```

- [ ] **Step 3: Verify overall git status**
Run: `git status`
Make sure all modified files are clean and committed.
