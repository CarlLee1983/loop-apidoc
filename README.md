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

擷取階段透過 [PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill) 查詢 NotebookLM。該 skill 以本機瀏覽器自動化操作 NotebookLM,每次問題都是獨立 session、沒有對話上下文,因此 pipeline 的每一輪查詢都會帶上完整上下文(Notebook 身分、已知摘要、待確認項目、預期輸出格式)。

pipeline 不負責建立 Notebook、上傳來源或自動登入私有網站 —— 這些屬於人工前置作業(見下)。

### 完整流程

```
manifest → 擷取(NotebookLM 多輪查詢) → 規格化計畫 → 生成(OpenAPI + Markdown) → 驗證 → 修正(最多 3 輪)
```

驗證失敗時,pipeline 依驗證報告分類問題並嘗試修正後重新驗證,最多 3 輪;三輪後仍失敗則輸出缺漏／衝突報告並以非零狀態結束。

---

## 安裝

需求:Python `>=3.11`,並使用 [`uv`](https://docs.astral.sh/uv/) 管理環境。

```bash
# 安裝相依套件
uv sync

# 確認 CLI 可執行
uv run loop-apidoc --help
```

擷取功能另需 NotebookLM skill 的本機 checkout(預設目錄 `notebooklm-skill`,可用 `--skill-root` 或環境變數 `LOOP_APIDOC_SKILL_ROOT` 指定)。先用 `doctor` 檢查環境是否就緒。

---

## 人工前置作業

以下步驟**不屬於 CLI**,需人工完成:

1. 建立 NotebookLM Notebook。
2. 將所有來源文件與公開 URL 手動加入 Notebook。
3. 取得該 Notebook 的分享連結。
4. 在本機保留一份與 Notebook 內容對應的來源目錄。

Notebook 必須可由本機瀏覽器登入的 Google 帳號存取;分享設定或帳號權限不足時,CLI 會在 NotebookLM 預檢階段失敗。

### 第一版支援的來源格式

PDF、Markdown、Microsoft Word、OpenAPI JSON／YAML、公開 URL。

---

## 使用方式

### `run` — 執行完整流程

```bash
uv run loop-apidoc run \
  --notebook-url "https://notebooklm.google.com/notebook/..." \
  --sources ./sources \
  --output ./output
```

| 參數 | 說明 |
| --- | --- |
| `--notebook-url` | NotebookLM 分享連結(必填) |
| `--sources` | 本機來源目錄(必填) |
| `--output` | 輸出根目錄;會在其下建立 `<run-id>` 子目錄(必填) |
| `--url` | 公開來源 URL,可重複指定 |
| `--skill-root` | notebooklm-skill checkout 目錄(預設 `notebooklm-skill`) |

預設值:輸出語言 `zh-TW`、規格 OpenAPI 3.1、最大修正輪數 3、禁止推測啟用。

退出碼:驗證通過(`PASSED`)回傳 `0`,其餘狀態(`failed` / `early-stopped` / `blocked`)回傳非零。

### `doctor` — 環境檢查

```bash
uv run loop-apidoc doctor
```

檢查 Python、NotebookLM skill、skill 依賴、Chrome、瀏覽器驗證狀態與必要驗證工具。**唯讀**,不修改 Notebook 或輸出文件。就緒回傳 `0`,否則回傳 `1`。

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

---

## 輸出結構

每次執行使用獨立 run directory:

```text
output/
└── <run-id>/                    # run-id 格式:%Y%m%dT%H%M%SZ
    ├── manifest.json            # 來源 manifest
    ├── extraction/
    │   ├── queries.jsonl        # 每輪查詢紀錄
    │   └── answers/             # 原始擷取 artifact(逐輪保存,不覆蓋)
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

修正迴圈會將問題分類:`OPENAPI_INVALID` / `OUTPUT_MISMATCH` → 自動修正;`REQUIRED_INFO_MISSING` → 重新查詢(僅針對相關 stage);`SOURCE_UNVERIFIED` / `SOURCE_CONFLICT` / `UNSUPPORTED_ASSERTION` → 無法自動修正(fail-closed,迴圈提早結束)。

---

## 開發

```bash
# 執行測試(248 passed + 1 skipped)
uv run pytest

# 含覆蓋率
uv run pytest --cov=loop_apidoc

# Lint
uv run ruff check .
```

real NotebookLM skill 的 smoke 測試以 `smoke` marker 標記,僅在設定 `LOOP_APIDOC_SMOKE=1` 時執行。

### 套件結構

| 套件 | 職責 |
| --- | --- |
| `loop_apidoc/manifest/` | 來源掃描與 manifest 建立 |
| `loop_apidoc/notebooklm/` | NotebookLM skill adapter(僅包裝 `auth_status` + `ask`)、retry、錯誤分類 |
| `loop_apidoc/doctor/` | 唯讀環境檢查 |
| `loop_apidoc/extraction/` | 多輪查詢、答案保存、JSON 區塊解析 |
| `loop_apidoc/plan/` | 規格化計畫建構與來源比對分類 |
| `loop_apidoc/generate/` | OpenAPI / Markdown / provenance 生成(唯一檔案 I/O 出口) |
| `loop_apidoc/validate/` | 結構／完整性／一致性／禁止推測驗證與報告 |
| `loop_apidoc/run/` | run-id、修正迴圈、完整 pipeline 編排 |

---

## 設計文件

- 架構總覽與資料流(含流程圖):[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 貢獻指南:[`CONTRIBUTING.md`](CONTRIBUTING.md)
- 系統設計 spec:[`docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md`](docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md)
- 各階段實作計畫:`docs/superpowers/plans/`
