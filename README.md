# loop-apidoc

> Loop Engineering 的**來源依據式（source-grounded）API 文件 pipeline**

*English version: [README.en.md](README.en.md)*

`loop-apidoc` 是一套可重複執行的 CLI，將格式與完整度不一的 API 串接文件，整理成一致、可追溯的標準化產物：

- **OpenAPI 3.1 YAML**（`openapi.yaml`）
- **繁體中文 Markdown 串接文件**（`api-guide.zh-TW.md`）
- **離線人工核對頁**（`review.html`）
- **來源追溯資料**（`provenance.json`）
- **驗證與缺漏報告**（`validation/report.{json,md}`）

核心原則:**以來源文件為唯一事實依據**。來源未提供的資訊一律不推測;必要資訊缺漏時,驗證會失敗並明確列出缺項,而非以慣例補寫。

---

## 運作方式

擷取引擎是**當前的 coding agent 自己**:在 Claude Code plugin 或 OpenAI Codex CLI 的 session 裡,agent 依 `loop-apidoc` skill 讀來源、以**唯讀 subagent fan-out** 擷取,主 agent 把結果寫成 `inventory.json` + `endpoints/*.json`,再呼叫確定性 CLI `assemble` 跑後段 plan → generate → validate。

### 完整流程

```
preprocess(可選) → 擷取(agent 唯讀 subagent fan-out) → manifest → 規格化計畫 → 生成(OpenAPI + Markdown) → 驗證
```

驗證會輸出分類後的問題報告。修正由 agent 自行驅動:`assemble` 以 `--json` 回報結果,agent 依報告回頭重讀來源、覆寫擷取 JSON,再重新執行 `assemble`,直到通過或判定為無法修正的缺漏／衝突。

---

## 以 Claude Code plugin 執行(agent-native)

除了 CLI,本專案也是一個 Claude Code plugin:在 Claude session 裡呼叫 `loop-apidoc` skill,給它一或多個來源(本機檔案或公開 URL),由 agent 自己擷取、呼叫 `loop-apidoc assemble` 組裝與驗證,並在驗證失敗時自行回頭補齊缺漏。

此模式由當前 agent 直接擔任擷取引擎(唯一擷取路徑)。安裝 plugin 後即可在 Claude Code 中使用;CLI 由 plugin 內含,透過 `uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc assemble` 呼叫。

### 在 OpenAI Codex CLI 使用

同一份 skill 也能在 Codex 執行。Codex 不會設 `${CLAUDE_PLUGIN_ROOT}`,因此把 CLI 裝成全域指令,並把 skill 掛進 Codex 的 skills 目錄:

```bash
# 1. 把 CLI 裝成全域 loop-apidoc 指令(取代 plugin 內含的 uv run --project)
uv tool install --from /path/to/loop-apidoc loop-apidoc

# 2. 把 skill 掛進 Codex(symlink 即可,改檔自動同步)
ln -s /path/to/loop-apidoc/skills/loop-apidoc ~/.codex/skills/loop-apidoc
```

SKILL.md 以 `<APIDOC>` 佔位符自動辨識環境:有 `$CLAUDE_PLUGIN_ROOT` 走 plugin 內含 CLI,否則退到全域 `loop-apidoc`。其餘流程(擷取 → `assemble` → 驗證 → 修正)兩邊一致。

### Agent 交付層級

skill 在讀取來源前會先說明並詢問交付層級：`minimal`（預設）、`review`、`handoff` 或
`full`。`minimal` 只讓 agent 交付與傳遞 OpenAPI、provenance、驗證結果及需要時的整合
契約；未選取的衍生產物不會載入 agent context 或在 agent 間傳遞，以減少 token 消耗。
這是 agent 交付策略，不改變 CLI 的來源依據、驗證或相容 run-dir 結構。

發行說明：[`0.9.0`](docs/RELEASE_NOTES_0.9.0.md)。

---

## 安裝

需求:Python `>=3.11`,並使用 [`uv`](https://docs.astral.sh/uv/) 管理環境。

```bash
# 安裝相依套件
uv sync

# 確認 CLI 可執行
uv run loop-apidoc --help
```

---

## 支援的來源格式

PDF、Markdown、Microsoft Word、OpenAPI JSON／YAML、公開 URL。

---

## 使用方式

### `manifest` — 建立來源 manifest

```bash
uv run loop-apidoc manifest --sources ./sources [--url <URL> ...] [--output manifest.json]
```

掃描本機來源,記錄相對路徑、格式、大小、SHA-256、掃描時間、是否受支援、重複判定與處理狀態;公開 URL 另記錄擷取時間、HTTP 狀態與內容雜湊。省略 `--output` 時輸出至 stdout。

### `catalog-url` / `select-url` — 先建立導航索引，再選取擷取範圍

```bash
# 只下載入口頁一次；它不會追蹤或下載側欄子頁。
uv run loop-apidoc catalog-url \
  --url "https://docs.example.com/api/introduction" \
  --output ./work/url_sources/catalog.json

# 選擇要擷取的文件分支與主題；此步驟同樣不下載正文。
uv run loop-apidoc select-url \
  --catalog ./work/url_sources/catalog.json \
  --branch "轉帳錢包" --term "轉帳" \
  --output ./work/url_sources/selection.json
```

`catalog.json` 是完整的導航 **coverage universe**，用於看見網站有哪些文件；
`selection.json` 可作為人工指定的模型閱讀起點。它不必限制工具端的快取範圍。

當網站擷取成本低、但模型 context 昂貴時，快取完整 catalog，然後只把候選卡片交給模型：

```bash
# 保存 raw HTML 與清除導覽後的正文；建立 heading、內部連結與實體索引。
uv run loop-apidoc cache-url-pages \
  --catalog ./work/url_sources/catalog.json \
  --output ./work/url_corpus

# 以正文內部連結、共享 Action／錯誤碼和導航層級產生小型候選卡片。
uv run loop-apidoc related-url-pages \
  --corpus ./work/url_corpus/corpus.json \
  --url "https://docs.example.com/api/action19" \
  --output ./work/action19-candidates.json
```

`cache-url-pages` 不呼叫模型；`corpus.json` 不嵌入正文，只指向本機 `raw/` 與 `body/`
檔。`related-url-pages` 輸出標題、breadcrumb、分數和關聯理由，模型只在需要時才讀取
候選頁的 `body_file`。這可保留完整來源與 coverage，又避免不相干分支、重複側欄和所有
正文一起進入模型。

靜態單頁文件的 sidebar anchor 會保留為 catalog 節點的 `anchor`，並在 corpus 的單一入口
頁卡片中列為 `sections`（同一 HTML 只下載一次）。catalog 為空或沒有側欄時，使用
`cache-url-entry --url ... --output ...` 直接快取入口頁。已下載的 HTML 可用
`normalize-html-snapshot --input page.html --url ... --output sources/page.md` 轉為受支援
Markdown；命令會寫出帶原始 URL 與 SHA-256 的 `.source.json` provenance sidecar。HTML
本身也會在 manifest 中列為受支援格式。

### Codex 與 Claude Code 的模型分工

skill 不綁定特定模型：由宿主將快速模型用於候選頁路由、一般模型用於受限的單頁擷取、
高推理模型用於跨頁審核。CLI 持續負責抓取、解析、provenance、coverage 與驗證；角色間
只傳遞 artifact 路徑與精簡摘要，不能因為模型 context 較大就把完整 corpus 放進去。詳見
[`model-orchestration.md`](skills/loop-apidoc/reference/model-orchestration.md) 的角色矩陣、
交接契約與 Codex／Claude 對應方式。

### `validate` — 驗證既有 run 目錄

```bash
uv run loop-apidoc validate --output ./output/<run-id>
```

對 run 目錄輸出執行結構／完整性／一致性／禁止推測四類驗證,並將報告寫入 `<run-dir>/validation/`。通過回傳 `0`,有 ERROR 級問題回傳 `1`。

### `score` — 評分既有 run 目錄

```bash
uv run loop-apidoc score --output ./output/<run-id> [--profile ci|review] [--min-score 85] [--json]
```

讀取既有 run 目錄的 `validation/report.json`、`openapi.yaml`、
`provenance.json`、`manifest.json` 與選填的 `plan/normalization-plan.json`，
輸出 `score/score.json` 與 `score/score.md`。`ci` profile 預設門檻為
`85`，`review` profile 預設門檻為 `70`。退出碼：`0` = pass，`1` =
needs_attention / fail，`2` = run-dir 輸入錯誤。

### `diff` — 比較兩次 run 的版本差異

```bash
uv run loop-apidoc diff --base ./output/<old-run> --head ./output/<new-run>
```

比較兩個已完成 run directory，依 downstream impact 輸出差異報告。預設寫入
`<new-run>/diff/report.{json,md}`；可用 `--output` 指定其他目錄。差異分類為
`breaking`、`additive`、`changed`、`source_only`，比較範圍包含
`openapi.yaml`、`integration-contract.json`、`provenance.json`、
`validation/report.json` 與 `manifest.json`。第一版不比較 Markdown guide 或
generated examples。

### `foundry` — API 專案本地資產治理

```bash
uv run loop-apidoc foundry [init|import|approve|list|current] --help
```

提供管理 docset、將 run 目錄匯入為 candidate、以及核准 asset 以更新 `current` 指標的子指令。適用於需要對文件版本進行人為審核與發布管理的場景。

### `preprocess` — PDF 轉高保真 markdown(可選)

```bash
uv run loop-apidoc preprocess --sources ./sources --out ./work/sources_md
```

以 pymupdf4llm 把 `--sources` 下的每個 PDF 轉成保留表格與標題結構的 markdown(非 PDF 文字來源原樣複製)。表格密集或大型 PDF 在擷取前先轉換,可避免原始 PDF 讀取扭曲表格;之後把擷取 subagent 指向 `--out` 目錄。

### `assemble` — 從 agent 產出的擷取 JSON 組裝(由 skill 呼叫)

```bash
uv run loop-apidoc assemble \
  --sources ./sources \
  --extraction ./work \
  --output ./output \
  [--url <URL> ...] [--source-quality ./work/source-quality] [--json] [--score]
```

**不擷取**,只把 agent 已產出的擷取目錄(`inventory.json` + `endpoints/*.json`,以及選填的 `integration.json` 簽章/加密契約)組裝成輸出:manifest → plan → generate → validate。若傳入 `assess-sources` 已產出的 `--source-quality` 目錄，`reject` 結論會在建立 run-dir 前中止；`pass` 的來源品質報告與來源差異會被寫入 run-dir，供稽核與 Foundry 保留。`--json` 會把 `run_id`、`run_dir`、`review_html`、`ok`、`status`、`report` 印到 stdout 供 agent 解析並驅動修正迴圈。退出碼:`0`=驗證 PASS、`1`=驗證 FAIL、`2`=擷取輸入檔錯誤。這是上方 [agent-native plugin](#以-claude-code-plugin-執行agent-native) 模式所呼叫的命令。加上 `--score` 時，`assemble` 完成後會額外寫出 `score/score.json` 與
`score/score.md`；assemble 的退出碼仍維持既有驗證語意。

---

## 輸出結構

每次執行使用獨立 run directory:

```text
output/
└── <run-id>/                       # run-id 格式:%Y%m%dT%H%M%S.%fZ(含微秒,避免同秒衝突)
    ├── manifest.json               # 來源 manifest
    ├── extraction/                 # 擷取稽核軌跡(非可重跑的原始輸入)
    │   ├── queries.jsonl           # 每輪查詢紀錄
    │   └── answers/                # 各查詢回應 <query_id>.txt
    ├── plan/
    │   └── normalization-plan.json      # 機器可讀規格化計畫
    ├── openapi.yaml                # OpenAPI 3.1
    ├── api-guide.zh-TW.md          # 繁體中文串接文件
    ├── review.html                 # 生成產物人工核對頁(離線 HTML)
    ├── provenance.json             # 每個輸出項目的來源追溯
    ├── integration-contract.json   # 簽章/加密整合契約(來源有提供時)
    ├── examples/                   # 逐端點 curl / TypeScript / Python 請求範例(產出時)
    ├── handoff/                    # 開發交接輔助(衍生產物,非契約來源)
    │   ├── integration-tasks.md    # 實作順序/執行設定/阻塞項檢查表
    │   ├── postman_collection.json # Postman v2.1 請求形狀集合(可匯入)
    │   └── sdk-hints.json          # 精簡 SDK/client 生成提示(不複製 schema)
    ├── validation/
    │   ├── report.json
    │   └── report.md
    ├── source-quality/              # 傳入 --source-quality 時保留來源品質稽核
    │   ├── source-quality-report.json
    │   ├── source-quality-report.zh-TW.md
    │   ├── source-diff.json
    │   └── source-diff.md
    ├── score/                       # 文件品質評分（使用 loop-apidoc score 或 assemble --score）
    │   ├── score.json
    │   └── score.md
    └── diff/                       # 與另一個 run 比較版本差異時(loop-apidoc diff)
        ├── report.json
        └── report.md
```

`handoff/` 為衍生的工程導引與工具轉接產物,**契約來源仍是 `openapi.yaml` 與 `integration-contract.json`**,不重複 schema。

> 注意:agent 產出的擷取輸入(`inventory.json` + `endpoints/*.json` + 選填 `integration.json`)位於傳給 `--extraction` 的工作目錄,**不在** run-dir。run-dir 的 `extraction/` 只保留稽核軌跡(`queries.jsonl` + `answers/`)。

只有同時存在於計畫、且具來源依據的內容,才會進入 OpenAPI 與 Markdown。OpenAPI 必填但來源缺失的欄位,會以最小合法占位填入,並標記 `x-loop-status: missing-source` 與 provenance 缺漏紀錄;若該缺漏影響可串接性,完整性驗證仍會失敗。

---

## 驗證規則摘要

| 類別 | 內容 |
| --- | --- |
| **結構** | OpenAPI 3.1 合法性;endpoint 必須有 method、path 與至少一個 response |
| **完整性** | 標記 `unverified` 的來源、缺漏必要欄位、manifest 涵蓋缺口(不可讀來源等)會使驗證失敗 |
| **一致性** | OpenAPI 與 Markdown／provenance 的 endpoint 集合與 security 名稱需一致 |
| **禁止推測** | 每個輸出項目須對應 provenance 來源;無來源支持的內容視為違規 |

驗證會將問題分類:`OPENAPI_INVALID` / `OUTPUT_MISMATCH` → 可由重新生成修正;`REQUIRED_INFO_MISSING` → agent 重讀相關來源補齊;`SOURCE_UNVERIFIED` / `SOURCE_CONFLICT` / `UNSUPPORTED_ASSERTION` → 無法修正(fail-closed,回報為缺漏／衝突)。修正由 agent 依 `assemble --json` 回報自行驅動(重讀來源、覆寫擷取 JSON 後重跑),而非由 CLI 內建迴圈。

---

## 開發

```bash
# 執行測試
uv run pytest

# 含覆蓋率
uv run pytest --cov=loop_apidoc

# Lint
uv run ruff check .
```

### 套件結構

| 套件 | 職責 |
| --- | --- |
| `loop_apidoc/manifest/` | 來源掃描與 manifest 建立 |
| `loop_apidoc/agentcli/` | `assemble.py`(組裝 agent 寫出的擷取 JSON → plan→generate→validate)、`extraction.py`(把 `inventory.json` 轉成 plan 各 stage 答案)、`preprocess.py`(PDF→md 前處理,pymupdf4llm) |
| `loop_apidoc/extraction/` | agent 擷取共用的 models 與工具(models、stages、questions、store、jsonblock) |
| `loop_apidoc/plan/` | 規格化計畫建構與來源比對分類 |
| `loop_apidoc/generate/` | OpenAPI / Markdown / provenance 生成(唯一檔案 I/O 出口) |
| `loop_apidoc/validate/` | 結構／完整性／一致性／禁止推測驗證與報告 |
| `loop_apidoc/run/` | run-id 產生、結果／狀態 models、將計畫寫入 run 目錄 |
| `loop_apidoc/diff/` | 比較兩個 run 目錄的版本差異，依 impact 分類並輸出報告 |
| `loop_apidoc/preparation/` | 在 assemble 內把 manifest 與 plan 評成準備度報告 |
| `loop_apidoc/score/` | 既有 run-dir 文件品質評分(JSON/Markdown report, CI gate 狀態) |
| `loop_apidoc/source_quality/` | 擷取前來源品質評估與來源版本差異報告；通過報告可隨 run-dir 稽核保存 |
| `loop_apidoc/url_catalog.py` / `url_corpus.py` | 受限 URL 導航索引、頁面快取與關聯候選，讓 agent 以本機證據讀取網頁文件 |
| `loop_apidoc/foundry/` | API 專案本地資產治理，管理 docset、candidate 匯入與 asset 核准 |

---

## 設計文件

- 架構總覽與資料流(含流程圖):[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 貢獻指南:[`CONTRIBUTING.md`](CONTRIBUTING.md)
- 系統設計 spec:[`docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md`](docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md)
- 各階段實作計畫:`docs/superpowers/plans/`
