# 架構

本文件說明 `loop-apidoc` 的整體流程、資料流與套件邊界。完整設計依據見 [`docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md`](superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md)。

## 三種執行模式

擷取後段(規劃→生成→驗證→修正)在三種模式下共用同一套確定性管線,差別只在**誰擔任擷取引擎**:

| 模式 | 入口 | 擷取引擎 | 適用 |
| --- | --- | --- | --- |
| NotebookLM | `run` | NotebookLM 多輪查詢(本機瀏覽器自動化) | 已建好 Notebook 的標準流程 |
| coding-agent CLI | `run-agent` | 子行程 `claude -p`(或其他 agent CLI) | 不想經 NotebookLM、由 CLI 自行 spawn agent |
| agent-native plugin | `assemble`(由 skill 呼叫) | 當前 Claude agent 自己讀來源 | 在 Claude session 內,agent 擷取後呼叫 CLI 組裝 |

`run-agent` 與 `assemble` 由 `loop_apidoc/agentcli/` 提供;兩者都把擷取結果收斂成 `inventory.json` + `endpoints/*.json`,再交給共用的 plan→generate→validate。`assemble` 不負責擷取,只組裝 agent 已寫出的 JSON,並以 `--json` 回報結果供 agent 驅動修正迴圈。

## 高層流程(NotebookLM `run`)

```mermaid
flowchart LR
    subgraph 人工["人工前置作業（不屬 CLI）"]
        H1[建立 NotebookLM Notebook]
        H2[上傳來源 + 公開 URL]
        H3[取得分享連結]
        H4[保留本機來源目錄]
    end

    subgraph CLI["loop-apidoc run"]
        M[manifest<br/>掃描本機來源] --> E[擷取<br/>NotebookLM 多輪查詢]
        E --> P[規格化計畫<br/>normalization-plan.json]
        P --> G[生成<br/>OpenAPI + Markdown + provenance]
        G --> V[驗證<br/>結構/完整性/一致性/禁止推測]
        V -->|有 ERROR| C{修正分類}
        C -->|AUTO_FIX| G
        C -->|RE_QUERY| E
        C -->|UNFIXABLE| X[早停]
        V -->|通過| OK[PASSED]
    end

    人工 -.分享連結 + 來源目錄.-> CLI
```

修正迴圈最多 3 輪;`UNFIXABLE`(來源無法確認／衝突／不支援斷言)會 fail-closed 提早結束。

## 套件邊界

```mermaid
flowchart TD
    cli[cli.py<br/>Typer 進入點]

    cli --> doctor[doctor/<br/>唯讀環境檢查]
    cli --> manifest[manifest/<br/>掃描 + manifest]
    cli --> run[run/<br/>pipeline 編排]
    cli --> agentcli[agentcli/<br/>run-agent + assemble]
    cli --> validate[validate/<br/>驗證 + 報告]

    run --> manifest
    run --> extraction[extraction/<br/>多輪查詢 + 答案保存]
    run --> plan[plan/<br/>規格化計畫 + 來源比對]
    run --> generate[generate/<br/>OpenAPI/MD/provenance]
    run --> validate

    agentcli --> manifest
    agentcli --> plan
    agentcli --> generate
    agentcli --> validate

    extraction --> notebooklm[notebooklm/<br/>skill adapter + retry]
    doctor --> notebooklm
    plan --> manifest

    classDef io fill:#fde,stroke:#c69
    class generate,run io
```

**唯一檔案 I/O 出口**:只有 `generate/`(`generate_outputs`)與 `run/`(`run_pipeline` 擁有 run-dir)寫檔;其餘模組皆為純函式,便於單元測試。

## 資料流與關鍵 seam

| 階段 | 公開 seam | 產物 |
| --- | --- | --- |
| 掃描 | `build_manifest(sources_root, urls, generated_at)` | `manifest.json` |
| 擷取 | `run_extraction(adapter, notebook_url, store, *, max_attempts=3)` | `extraction/queries.jsonl`、`extraction/answers/` |
| 計畫 | `build_normalization_plan(extraction, manifest)` | `plan/normalization-plan.json` |
| 生成 | `generate_outputs(plan, manifest, run_dir)` | `openapi.yaml`、`api-guide.zh-TW.md`、`provenance.json` |
| 驗證 | `validate_outputs(plan, result, manifest)`(純）／ `validate_run_dir(run_dir)`(讀檔) | `validation/report.{json,md}` |
| 修正迴圈 | `run_correction_loop(plan, result, *, regenerate, requery, validate, max_rounds=3)` | — |
| 完整流程 | `run_pipeline(*, notebook_url, sources_root, output_root, adapter, run_id, generated_at, urls, max_rounds=3)` | 整個 run-dir |

agentcli 模式另有兩個公開 seam(共用上方的 plan→generate→validate):

| 階段 | 公開 seam | 產物 |
| --- | --- | --- |
| agent CLI 擷取 | `run_agent_pipeline(*, sources_root, output_root, run_id, generated_at, executable, model, urls)` | 整個 run-dir(內含 `inventory.json` + `endpoints/*.json`) |
| 組裝(不擷取) | `run_assemble_pipeline(*, sources_root, extraction_dir, output_root, run_id, generated_at, urls)` | 整個 run-dir;`--json` 回報 `ok`/`run_dir`/`report` |

`run_assemble_pipeline` 會先驗證擷取輸入(`inventory.json` + `endpoints/*.json`)再建 run 目錄;輸入有誤時拋 `AssembleInputError`,CLI 以退出碼 `2` 結束、不留下孤兒目錄。

## 擷取查詢分段

擷取採分段策略,避免單一回答承載全部內容(spec §7.1):

```
01 Notebook 與來源盤點        06 逐 endpoint 細節（method/path/參數/req/resp/範例）
02 API 系統概覽與術語          07 共用 schema / enum / 資料限制
03 環境 / base URL / 版本      08 錯誤碼與失敗行為
04 驗證 / 授權 / 簽章          09 rate limit / timeout / retry / idempotency / webhook
05 Endpoint 清單              10 來源衝突、缺漏、無法確認事項
```

混合回答契約:盤點型 stage(03–09)要求 fenced `json` 區塊;敘事型 stage(01/02/10)為純文字 artifact。每輪回答逐一保存,不覆蓋或丟棄,作為審計軌跡。

## 來源追溯與驗證對齊

`provenance.json` 的 `target` 字串與 OpenAPI 位置**逐一對齊**(如 `paths.{path}.{method}`、`components.schemas.{name}`、`components.securitySchemes.{name}`),驗證的禁止推測檢查即在這些 target 上做交叉比對:任何進入輸出的內容都必須能追溯回具來源依據的計畫項目,否則視為違規。
