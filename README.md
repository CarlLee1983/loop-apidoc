# loop-apidoc

> Loop Engineering 的**來源依據式（source-grounded）API 文件 pipeline**

*English version: [README.en.md](README.en.md)*

`loop-apidoc` 是一套可重複執行的 CLI，將格式與完整度不一的 API 串接文件，整理成一致、可追溯的標準化產物：

- **OpenAPI 3.1 YAML**（`openapi.yaml`）
- **繁體中文 Markdown 串接文件**（`api-guide.zh-TW.md`）
- **來源追溯資料**（`provenance.json`）
- **驗證與缺漏報告**（`validation/report.{json,md}`）

核心原則:**以來源文件為唯一事實依據**。來源未提供的資訊一律不推測;必要資訊缺漏時,驗證會失敗並明確列出缺項,而非以慣例補寫。

---

## 運作方式

pipeline 有**兩種執行模式**,差別只在**誰擔任擷取引擎**;擷取後段(規格化計畫 → 生成 → 驗證)為兩種模式共用的同一套確定性管線:

| 模式 | 入口指令 | 擷取引擎 |
| --- | --- | --- |
| coding-agent CLI | `run-agent` | 子行程 `claude -p`(或以 `--executable` 指定其他 agent CLI) |
| agent-native plugin | `assemble`(由 skill 呼叫) | 當前 Claude agent 自己讀來源 |

兩種模式都把擷取結果收斂成 `inventory.json` + `endpoints/*.json`,再交給共用的 plan → generate → validate。

### 完整流程

```
manifest → 擷取(agent 讀來源) → 規格化計畫 → 生成(OpenAPI + Markdown) → 驗證
```

驗證會輸出分類後的問題報告。修正由 agent 自行驅動:`assemble` 以 `--json` 回報結果,agent 依報告回頭重讀來源、覆寫擷取 JSON,再重新執行 `assemble`,直到通過或判定為無法修正的缺漏／衝突。

---

## 以 Claude Code plugin 執行(agent-native)

除了 CLI,本專案也是一個 Claude Code plugin:在 Claude session 裡呼叫 `loop-apidoc` skill,給它一或多個來源(本機檔案或公開 URL),由 agent 自己擷取、呼叫 `loop-apidoc assemble` 組裝與驗證,並在驗證失敗時自行回頭補齊缺漏。

此模式由當前 agent 直接擔任擷取引擎,不另行 spawn `claude -p`。安裝 plugin 後即可在 Claude Code 中使用;CLI 由 plugin 內含,透過 `uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc assemble` 呼叫。

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

### `validate` — 驗證既有 run 目錄

```bash
uv run loop-apidoc validate --output ./output/<run-id>
```

對 run 目錄輸出執行結構／完整性／一致性／禁止推測四類驗證,並將報告寫入 `<run-dir>/validation/`。通過回傳 `0`,有 ERROR 級問題回傳 `1`。

### `run-agent` — 以 coding-agent CLI 擷取

```bash
uv run loop-apidoc run-agent \
  --sources ./sources \
  --output ./output \
  [--executable claude] [--model <model>] [--url <URL> ...]
```

以 coding-agent CLI(預設 `claude -p`)擔任擷取引擎:manifest → PDF 轉 markdown(pymupdf4llm,保留表格與結構)→ 一次 inventory + 逐 endpoint 擷取 → 規劃 → 生成 → 驗證。`--executable` 可換成其他 agent CLI(如 `codex`)。退出碼:驗證通過 `0`,否則 `1`。

| 參數 | 說明 |
| --- | --- |
| `--sources` | 本機來源目錄(必填) |
| `--output` | 輸出根目錄;會在其下建立 `<run-id>` 子目錄(必填) |
| `--executable` | agent CLI 執行檔(預設 `claude`) |
| `--model` | 指定 agent 使用的模型(可選) |
| `--url` | 公開來源 URL,可重複指定 |

### `assemble` — 從 agent 產出的擷取 JSON 組裝(供 agent-native plugin)

```bash
uv run loop-apidoc assemble \
  --sources ./sources \
  --extraction ./work \
  --output ./output \
  [--url <URL> ...] [--json]
```

**不擷取**,只把 agent 已產出的擷取目錄(`inventory.json` + `endpoints/*.json`)組裝成輸出:manifest → plan → generate → validate。`--json` 會把 `run_id`、`run_dir`、`ok`、`status`、`report` 印到 stdout 供 agent 解析並驅動修正迴圈。退出碼:`0`=驗證 PASS、`1`=驗證 FAIL、`2`=擷取輸入檔錯誤。這是上方 [agent-native plugin](#以-claude-code-plugin-執行agent-native) 模式所呼叫的命令。

---

## 輸出結構

每次執行使用獨立 run directory:

```text
output/
└── <run-id>/                    # run-id 格式:%Y%m%dT%H%M%SZ
    ├── manifest.json            # 來源 manifest
    ├── extraction/
    │   ├── inventory.json       # API 盤點(agent 擷取產出)
    │   └── endpoints/           # 逐 endpoint 擷取 JSON
    ├── plan/
    │   └── normalization-plan.json   # 機器可讀規格化計畫
    ├── openapi.yaml             # OpenAPI 3.1
    ├── api-guide.zh-TW.md       # 繁體中文串接文件
    ├── provenance.json          # 每個輸出項目的來源追溯
    └── validation/
        ├── report.json
        └── report.md
```

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
| `loop_apidoc/agentcli/` | coding-agent CLI 擷取後端(`run-agent`)與 `assemble` 組裝流程、子行程 runner／錯誤型別／`AskResult`／答案品質偵測、PDF→md 前處理(pymupdf4llm) |
| `loop_apidoc/extraction/` | agent 擷取模式共用的 models 與工具(models、stages、questions、store、jsonblock) |
| `loop_apidoc/plan/` | 規格化計畫建構與來源比對分類 |
| `loop_apidoc/generate/` | OpenAPI / Markdown / provenance 生成(唯一檔案 I/O 出口) |
| `loop_apidoc/validate/` | 結構／完整性／一致性／禁止推測驗證與報告 |
| `loop_apidoc/run/` | run-id 產生、結果／狀態 models、將計畫寫入 run 目錄 |

---

## 設計文件

- 架構總覽與資料流(含流程圖):[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 貢獻指南:[`CONTRIBUTING.md`](CONTRIBUTING.md)
- 系統設計 spec:[`docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md`](docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md)
- 各階段實作計畫:`docs/superpowers/plans/`
