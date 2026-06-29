# HTML Architecture Diagram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Mermaid-rendered module-boundary diagram in `docs/architecture-manual.html` with a native HTML/CSS/SVG/JS interactive architecture map while keeping Markdown Mermaid as source/fallback.

**Architecture:** Keep the existing single-file HTML manual and its current pipeline dashboard. Replace only the bottom module-boundary section with a data-driven architecture map: static module cards, an SVG connector layer, and a detail panel populated from `moduleDataset`. Remove the Mermaid CDN import from the HTML manual, but leave `docs/ARCHITECTURE.md` untouched.

**Tech Stack:** Static HTML, CSS custom properties, inline SVG, vanilla JavaScript, local shell validation, optional browser screenshot smoke check.

---

## File Structure

- Modify: `docs/architecture-manual.html`
  - Add CSS for `.architecture-map`, module cards, connector SVG, responsive mobile layout, and detail panel.
  - Replace the bottom `<div class="mermaid">...</div>` with native HTML module-map markup.
  - Add `moduleDataset`, `selectModule()`, and click binding beside the existing `dataset`/step logic.
  - Remove the Mermaid module import at the bottom.
- Keep unchanged: `docs/ARCHITECTURE.md`
  - Mermaid remains the Markdown source/fallback.

## Task 1: Add Static Validation Guard

**Files:**
- Create: `tests/docs/test_architecture_manual_html.py`

- [ ] **Step 1: Write failing tests for the desired HTML contract**

Create `tests/docs/test_architecture_manual_html.py` with:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "docs" / "architecture-manual.html"
MARKDOWN = ROOT / "docs" / "ARCHITECTURE.md"


def test_architecture_manual_uses_native_architecture_map():
    html = HTML.read_text(encoding="utf-8")

    assert 'class="architecture-map"' in html
    assert "const moduleDataset = {" in html
    assert "function selectModule(key)" in html
    assert 'class="module-card active"' in html
    assert 'id="module-detail-content"' in html


def test_architecture_manual_does_not_load_mermaid_runtime():
    html = HTML.read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net/npm/mermaid" not in html
    assert "mermaid.initialize" not in html
    assert '<div class="mermaid">' not in html


def test_architecture_markdown_keeps_mermaid_fallback():
    markdown = MARKDOWN.read_text(encoding="utf-8")

    assert "```mermaid" in markdown
    assert "flowchart TD" in markdown
```

- [ ] **Step 2: Run tests to verify they fail before implementation**

Run:

```bash
uv run pytest tests/docs/test_architecture_manual_html.py -q
```

Expected:

```text
FAILED tests/docs/test_architecture_manual_html.py::test_architecture_manual_uses_native_architecture_map
FAILED tests/docs/test_architecture_manual_html.py::test_architecture_manual_does_not_load_mermaid_runtime
```

The Markdown fallback test should pass.

- [ ] **Step 3: Commit the failing contract test**

Run:

```bash
git add tests/docs/test_architecture_manual_html.py
git commit -m "test: define native architecture map contract" \
  -m "Constraint: HTML manual should no longer depend on Mermaid runtime" \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: Keep ARCHITECTURE.md Mermaid as the plain-text fallback" \
  -m "Tested: uv run pytest tests/docs/test_architecture_manual_html.py -q (expected failure before implementation)" \
  -m "Not-tested: browser rendering before implementation"
```

## Task 2: Add Architecture Map Styles

**Files:**
- Modify: `docs/architecture-manual.html`

- [ ] **Step 1: Add CSS before `.footer` styles**

Insert this CSS after the existing `.panel-bottom h2` block:

```css
.architecture-map {
  display: grid;
  grid-template-columns: minmax(220px, 0.85fr) minmax(260px, 1fr) minmax(280px, 1.15fr);
  gap: 1.25rem;
  position: relative;
  margin-top: 1rem;
}

.architecture-lane {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.lane-title {
  font-size: 0.72rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.module-card {
  width: 100%;
  border: 1px solid var(--border-main);
  background: var(--bg-card);
  border-radius: 12px;
  padding: 0.9rem;
  text-align: left;
  color: var(--text-primary);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}

.module-card:hover {
  border-color: var(--text-secondary);
  transform: translateY(-1px);
}

.module-card.active {
  border-color: var(--border-active);
  background: var(--accent-soft);
  box-shadow: var(--shadow-md);
}

.module-card.io-boundary {
  border-color: color-mix(in srgb, var(--color-io) 45%, var(--border-main));
}

.module-name {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  font-family: var(--font-mono);
  font-size: 0.88rem;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.module-role {
  margin-top: 0.35rem;
  font-size: 0.78rem;
  line-height: 1.5;
  color: var(--text-secondary);
}

.command-list {
  display: grid;
  gap: 0.45rem;
}

.command-chip {
  border: 1px solid var(--border-main);
  background: var(--bg-inset);
  border-radius: 8px;
  padding: 0.45rem 0.55rem;
  font-family: var(--font-mono);
  font-size: 0.74rem;
  color: var(--text-secondary);
}

.module-group {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.architecture-connectors {
  position: absolute;
  inset: 1.8rem 0 0;
  width: 100%;
  height: calc(100% - 1.8rem);
  z-index: 1;
  pointer-events: none;
  color: var(--border-main);
}

.architecture-connectors path {
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.architecture-detail {
  margin-top: 1.25rem;
  border: 1px solid var(--border-main);
  background: var(--bg-inset);
  border-radius: 12px;
  padding: 1.25rem;
}

.architecture-detail h3 {
  margin: 0;
  font-size: 1rem;
}

.module-detail-grid {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 0.65rem 1rem;
  margin-top: 1rem;
  font-size: 0.84rem;
}

.module-detail-label {
  font-weight: 800;
  color: var(--text-secondary);
}

.module-detail-value {
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.module-detail-value code {
  color: var(--accent);
}

@media (max-width: 900px) {
  .architecture-map {
    grid-template-columns: 1fr;
  }

  .architecture-connectors {
    display: none;
  }

  .module-group {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .module-detail-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 2: Verify no behavior changed yet**

Run:

```bash
uv run pytest tests/docs/test_architecture_manual_html.py -q
```

Expected: still failing for missing markup and Mermaid runtime.

## Task 3: Replace Mermaid Markup With Native Map

**Files:**
- Modify: `docs/architecture-manual.html`

- [ ] **Step 1: Replace the bottom Mermaid `<div>`**

Inside the bottom section headed `套件邊界與模組架構`, replace the existing `<div class="mermaid">...</div>` with:

```html
<div class="architecture-map" aria-label="loop-apidoc module architecture map">
  <svg class="architecture-connectors" viewBox="0 0 1000 360" preserveAspectRatio="none" aria-hidden="true">
    <path d="M 235 70 C 300 70, 300 80, 365 80" />
    <path d="M 520 80 C 600 80, 620 72, 690 72" />
    <path d="M 520 110 C 600 110, 620 132, 690 132" />
    <path d="M 520 140 C 600 140, 620 192, 690 192" />
    <path d="M 520 170 C 600 170, 620 252, 690 252" />
    <path d="M 810 252 C 875 252, 875 306, 940 306" />
  </svg>

  <div class="architecture-lane">
    <div class="lane-title">Entry</div>
    <button type="button" class="module-card" data-module="cli">
      <div class="module-name">cli.py <span class="pill prep">Entry</span></div>
      <div class="module-role">Typer 入口，只暴露 preprocess、manifest、assemble、validate。</div>
    </button>
    <div class="command-list" aria-label="public commands">
      <div class="command-chip">preprocess</div>
      <div class="command-chip">manifest</div>
      <div class="command-chip">assemble</div>
      <div class="command-chip">validate</div>
    </div>
  </div>

  <div class="architecture-lane">
    <div class="lane-title">Controller</div>
    <button type="button" class="module-card active" data-module="agentcli">
      <div class="module-name">agentcli/ <span class="pill agent">Controller</span></div>
      <div class="module-role">組裝 agent 擷取 JSON，串接後段 deterministic pipeline。</div>
    </button>
  </div>

  <div class="architecture-lane">
    <div class="lane-title">Modules</div>
    <div class="module-group">
      <button type="button" class="module-card" data-module="manifest">
        <div class="module-name">manifest/ <span class="pill io">Scan</span></div>
        <div class="module-role">掃描來源、URL 與雜湊，建立 provenance 基礎。</div>
      </button>
      <button type="button" class="module-card" data-module="extraction">
        <div class="module-name">extraction/ <span class="pill agent">Data</span></div>
        <div class="module-role">共用擷取 models、stage 與問題結構。</div>
      </button>
      <button type="button" class="module-card" data-module="plan">
        <div class="module-name">plan/ <span class="pill pure">Pure</span></div>
        <div class="module-role">把擷取結果規格化為 normalization plan。</div>
      </button>
      <button type="button" class="module-card io-boundary" data-module="generate">
        <div class="module-name">generate/ <span class="pill io">File I/O</span></div>
        <div class="module-role">輸出 OpenAPI、Markdown 與 provenance。</div>
      </button>
      <button type="button" class="module-card" data-module="validate">
        <div class="module-name">validate/ <span class="pill pure">Pure</span></div>
        <div class="module-role">檢查結構、完整性、一致性與禁止推測。</div>
      </button>
      <button type="button" class="module-card io-boundary" data-module="run">
        <div class="module-name">run/ <span class="pill io">File I/O</span></div>
        <div class="module-role">管理 run-id 並將計畫與產物落到 run-dir。</div>
      </button>
    </div>
  </div>
</div>

<div class="architecture-detail" id="module-detail-content" aria-live="polite">
  <!-- Rendered dynamically -->
</div>
```

- [ ] **Step 2: Run contract test**

Run:

```bash
uv run pytest tests/docs/test_architecture_manual_html.py -q
```

Expected: the native map test may pass, but the Mermaid runtime test still fails until Task 5 removes the import.

## Task 4: Add Module Dataset and Interaction

**Files:**
- Modify: `docs/architecture-manual.html`

- [ ] **Step 1: Add `moduleDataset` after the existing `dataset` object**

Add this object after the closing `};` of `const dataset = { ... };`:

```javascript
const moduleDataset = {
  cli: {
    title: "cli.py",
    badgeClass: "prep",
    badgeLabel: "Entry",
    description: "Typer CLI 入口，對外暴露 preprocess、manifest、assemble、validate 四個命令，將使用者操作導向對應的 deterministic pipeline seam。",
    seam: "loop_apidoc.cli",
    inputs: "CLI arguments: sources, extraction-dir, output-root, run-id, urls",
    outputs: "Delegates to preprocess / manifest / assemble / validate commands",
    sideEffect: "Dispatch only; side effects depend on selected command"
  },
  agentcli: {
    title: "agentcli/",
    badgeClass: "agent",
    badgeLabel: "Controller",
    description: "後段組裝入口，讀取 agent 寫出的 inventory.json 與 endpoints/*.json，串接 manifest、plan、generate、validate，並以 --json 回報 ok、run_dir 與 report。",
    seam: "run_assemble_pipeline(...)",
    inputs: "inventory.json, endpoints/*.json, sources root, urls",
    outputs: "run-dir plus JSON status report",
    sideEffect: "Coordinates pipeline; generate/ and run/ own file writes"
  },
  manifest: {
    title: "manifest/",
    badgeClass: "io",
    badgeLabel: "Source Scan",
    description: "掃描本機來源與公開 URL，記錄格式、大小、雜湊與掃描時間，作為後續 provenance 對齊基礎。",
    seam: "build_manifest(sources_root, urls, generated_at)",
    inputs: "sources root, URL list",
    outputs: "manifest.json data structure",
    sideEffect: "Reads local source metadata; does not write final artifacts"
  },
  extraction: {
    title: "extraction/",
    badgeClass: "agent",
    badgeLabel: "Agent Data",
    description: "定義擷取階段、問題與共用資料模型，讓 agent-native 擷取結果可被 deterministic CLI 後段理解。",
    seam: "inventory_to_stage_answers(inventory)",
    inputs: "inventory.json and endpoint extraction JSON",
    outputs: "stage-shaped answers for plan construction",
    sideEffect: "No direct file output in the module boundary diagram"
  },
  plan: {
    title: "plan/",
    badgeClass: "pure",
    badgeLabel: "Pure Logic",
    description: "把碎片化擷取結果與 manifest 來源資訊重構成 normalization-plan.json 的結構化計畫。",
    seam: "build_normalization_plan(extraction, manifest)",
    inputs: "stage answers, endpoints, manifest",
    outputs: "normalization plan data",
    sideEffect: "Pure transformation"
  },
  generate: {
    title: "generate/",
    badgeClass: "io",
    badgeLabel: "File I/O",
    description: "把 normalization plan 轉成實際交付產物，包含 OpenAPI、Markdown guide 與 provenance mapping。",
    seam: "generate_outputs(plan, manifest, run_dir)",
    inputs: "normalization plan, manifest, run-dir path",
    outputs: "openapi.yaml, api-guide.zh-TW.md, provenance.json",
    sideEffect: "Writes generated artifact files"
  },
  validate: {
    title: "validate/",
    badgeClass: "pure",
    badgeLabel: "Pure Logic",
    description: "驗證 OpenAPI、Markdown 與 provenance 的結構、完整度、一致性與禁止推測規則。",
    seam: "validate_outputs(plan, result, manifest) / validate_run_dir(run_dir)",
    inputs: "generated outputs, plan, manifest",
    outputs: "validation report data and report files through run-dir flow",
    sideEffect: "Core validation is pure; run-dir validation reads existing files"
  },
  run: {
    title: "run/",
    badgeClass: "io",
    badgeLabel: "File I/O",
    description: "管理 run-id 與 run-dir persistence，保存 normalization plan、產物與驗證報告。",
    seam: "persist.py / runid.py",
    inputs: "run id, output root, generated artifacts, reports",
    outputs: "stable run directory layout",
    sideEffect: "Writes run-dir files"
  }
};
```

- [ ] **Step 2: Add `selectModule` after `switchTab`**

Add:

```javascript
function selectModule(key) {
  const data = moduleDataset[key];
  if (!data) return;

  document.querySelectorAll('.module-card').forEach(card => {
    card.classList.toggle('active', card.dataset.module === key);
  });

  const container = document.getElementById('module-detail-content');
  if (!container) return;

  container.innerHTML = `
    <div class="detail-headline">
      <h3>${data.title}</h3>
      <span class="pill ${data.badgeClass}">${data.badgeLabel}</span>
    </div>
    <div class="detail-desc">${data.description}</div>
    <div class="module-detail-grid">
      <div class="module-detail-label">公開 seam</div>
      <div class="module-detail-value"><code>${data.seam}</code></div>
      <div class="module-detail-label">輸入</div>
      <div class="module-detail-value">${data.inputs}</div>
      <div class="module-detail-label">輸出</div>
      <div class="module-detail-value">${data.outputs}</div>
      <div class="module-detail-label">Side effect</div>
      <div class="module-detail-value">${data.sideEffect}</div>
    </div>
  `;
}
```

- [ ] **Step 3: Bind module card clicks inside `DOMContentLoaded`**

Inside the existing `DOMContentLoaded` callback, after tab button binding, add:

```javascript
document.querySelectorAll('.module-card').forEach(card => {
  card.addEventListener('click', () => {
    selectModule(card.dataset.module);
  });
});

selectModule('agentcli');
```

- [ ] **Step 4: Run contract test**

Run:

```bash
uv run pytest tests/docs/test_architecture_manual_html.py -q
```

Expected: only the Mermaid runtime removal assertion fails if the import still exists.

## Task 5: Remove Mermaid Runtime

**Files:**
- Modify: `docs/architecture-manual.html`

- [ ] **Step 1: Delete the Mermaid module script at the bottom**

Remove:

```html
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({ startOnLoad: true, theme: dark ? "dark" : "default", securityLevel: "loose" });
</script>
```

- [ ] **Step 2: Run contract test**

Run:

```bash
uv run pytest tests/docs/test_architecture_manual_html.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 3: Commit implementation**

Run:

```bash
git add docs/architecture-manual.html tests/docs/test_architecture_manual_html.py
git commit -m "docs: render architecture map without Mermaid runtime" \
  -m "Constraint: HTML manual remains a single self-contained static file" \
  -m "Rejected: Keeping Mermaid as the HTML renderer | it cannot provide the module detail interaction wanted for the manual" \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: Preserve ARCHITECTURE.md Mermaid as the fallback/source diagram" \
  -m "Tested: uv run pytest tests/docs/test_architecture_manual_html.py -q" \
  -m "Not-tested: browser visual smoke check"
```

## Task 6: Browser Smoke Check and Final Polish

**Files:**
- Modify if needed: `docs/architecture-manual.html`

- [ ] **Step 1: Serve docs locally**

Run:

```bash
python3 -m http.server 8765 --directory docs
```

Expected:

```text
Serving HTTP on :: port 8765
```

- [ ] **Step 2: Open desktop viewport**

Open:

```text
http://127.0.0.1:8765/architecture-manual.html
```

Use a desktop viewport around `1440x1000`. Verify:

- Architecture map is visible under `套件邊界與模組架構`.
- `agentcli/` is selected by default.
- Clicking `generate/` updates the detail panel and shows `File I/O`.
- No visible text overlaps.

- [ ] **Step 3: Open mobile viewport**

Use a mobile viewport around `390x844`. Verify:

- Module cards stack in one column.
- SVG connectors are hidden.
- Detail panel remains readable.
- No visible text overlaps or spills outside cards.

- [ ] **Step 4: Run final static validation**

Run:

```bash
uv run pytest tests/docs/test_architecture_manual_html.py -q
rg -n "mermaid|cdn.jsdelivr.net/npm/mermaid" docs/architecture-manual.html docs/ARCHITECTURE.md
```

Expected:

```text
3 passed
```

The `rg` command should show Mermaid only in `docs/ARCHITECTURE.md`, not in `docs/architecture-manual.html`.

- [ ] **Step 5: Commit visual polish if any edits were needed**

If Task 6 required edits, run:

```bash
git add docs/architecture-manual.html
git commit -m "docs: polish responsive architecture map rendering" \
  -m "Constraint: mobile and desktop views must remain readable without Mermaid" \
  -m "Confidence: high" \
  -m "Scope-risk: narrow" \
  -m "Directive: Keep connector SVG decorative and hide it on narrow screens" \
  -m "Tested: desktop and mobile browser smoke check; uv run pytest tests/docs/test_architecture_manual_html.py -q" \
  -m "Not-tested: cross-browser matrix beyond local smoke check"
```
