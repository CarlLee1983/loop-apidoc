# 架構

本文件說明 `loop-apidoc` 的整體流程、資料流與套件邊界。完整設計依據見 [`docs/superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md`](superpowers/specs/2026-06-25-loop-api-documentation-pipeline-design.md)。

## 執行模式:agent-native

`loop-apidoc` 的擷取引擎是**當前的 coding agent 自己**。在 Claude Code plugin 或 OpenAI Codex CLI 的 session 內,agent 依 [`skills/loop-apidoc/SKILL.md`](../skills/loop-apidoc/SKILL.md) 讀來源、以**唯讀 subagent fan-out** 擷取(每個 subagent 只讀檔與搜尋、回傳 JSON,**不寫檔**),主 agent 把回傳的 JSON 寫成 `inventory.json` + `endpoints/*.json`,再呼叫確定性 CLI `assemble` 跑後段 plan→generate→validate,並以 `--json` 回報結果供 agent 自行驅動修正。

擷取(agent)與後段(CLI 純函式管線)以 `inventory.json` + `endpoints/*.json` 為唯一交界:agent 負責「從來源讀出結構化 JSON」,CLI 負責「把 JSON 確定性地組裝、生成、驗證」,兩邊各自可獨立測試。

> 早期曾有以子行程 `claude -p` 擷取的 `run-agent` CLI 模式,已於 2026-06 退役(連同 NotebookLM 擷取後端一併移除);現在**唯一**擷取路徑是 agent-native。

### Skill 可攜性(Claude Code + Codex 雙棲)

`skills/loop-apidoc/SKILL.md` 是**單一可攜檔**,同一份同時供 Claude Code plugin 與 OpenAI Codex CLI 載入,不分叉。可攜性靠兩個抽象:

- **CLI 佔位符 `<APIDOC>`**:SKILL 頂部定義一次解析規則 —— 環境有 `$CLAUDE_PLUGIN_ROOT`(Claude plugin 安裝時自動帶入)走 plugin 內含 CLI(`uv run --project "$CLAUDE_PLUGIN_ROOT" loop-apidoc`),否則退到全域 `loop-apidoc`(Codex / 獨立,`uv tool install`)。前綴用陣列寫法(`RUN=(...)`;`"${RUN[@]}"`)以兼顧 bash/zsh 與含空白路徑;**不**用 `${VAR:+…}` inline 展開(zsh 不切詞會壞)。
- **工具名中性化**:描述 agent 行為時用動作(讀檔、搜尋、抓取 URL)而非單一 runtime 的工具名,擷取的唯讀 subagent fan-out 語意兩邊一致。

設計依據見 [`docs/superpowers/specs/2026-06-27-portable-skill-codex-design.md`](superpowers/specs/2026-06-27-portable-skill-codex-design.md),安裝路徑見 [`README.md`](../README.md)。

## 高層流程

```mermaid
flowchart LR
    PRE["preprocess（可選）<br/>PDF→markdown"] --> EX

    subgraph AGENT["agent 擷取（Claude Code / Codex）"]
        EX["唯讀 subagent fan-out<br/>讀來源 → 回傳 JSON"] --> WR["主 agent 寫檔<br/>inventory.json + endpoints/*.json"]
    end

    subgraph CLI["assemble（確定性 CLI 後段）"]
        M["manifest<br/>掃描來源"] --> P["規格化計畫<br/>normalization-plan.json"]
        P --> G["生成<br/>OpenAPI + Markdown + provenance"]
        G --> V["驗證<br/>結構/完整性/一致性/禁止推測"]
        V -->|通過| OK["PASS（exit 0）"]
        V -->|分類問題| R[("--json report")]
    end

    WR --> M
    R -.agent 重讀來源、覆寫 JSON 後重跑 assemble.-> EX
```

`assemble` 不擷取,只組裝 agent 已寫出的 JSON:`manifest → plan → generate → validate`,再以 `--json` 回報 `ok`/`run_dir`/`report`。修正由 **agent 自行驅動**(無 CLI 內建迴圈):agent 依報告回頭重讀相關來源、覆寫對應的 `inventory.json` 或 `endpoints/<NN>.json`,再重跑 `assemble`,最多 3 輪。`UNFIXABLE`(來源無法確認／衝突／不支援斷言)為 fail-closed,回報為缺漏／衝突而不補寫。

`assemble --score` 在驗證報告寫出後讀取同一個 run-dir artifact 集合並產生
`score/score.{json,md}`；這是後段品質摘要，不會回頭擷取來源，也不改變
validation pass/fail 的語意。

## 套件邊界

```mermaid
flowchart TD
    cli[cli.py<br/>Typer 進入點]

    cli --> manifest[manifest/<br/>掃描 + manifest]
    cli --> agentcli[agentcli/<br/>assemble + 前處理]
    cli --> validate[validate/<br/>驗證 + 報告]
    cli --> diff[diff/<br/>run 對 run 版本差異]
    cli --> score[score/<br/>run-dir 評分 + 報告]

    agentcli --> manifest
    agentcli --> extraction[extraction/<br/>共用 models + 工具]
    agentcli --> plan[plan/<br/>規格化計畫 + 來源比對]
    agentcli --> generate[generate/<br/>OpenAPI/MD/review.html/provenance]
    agentcli --> validate
    agentcli --> run[run/<br/>run-id + 寫入 run-dir]
    agentcli --> preparation[preparation/<br/>產生前就緒度評估]

    plan --> manifest

    classDef io fill:#fde,stroke:#c69
    class generate,run,diff,score,preparation io
```

`cli.py`(Typer)暴露七個指令:`preprocess`(PDF→markdown)、`manifest`(掃描)、`verify-extraction`(以 `assemble` 相同的輸入閘門單獨檢查 agent 寫出的擷取 JSON,不寫檔、不建立 run 目錄;乾淨 `exit 0`,任何違規或硬 schema 錯誤 `exit 2`——絕不會是 `1`,`1` 代表 validate FAIL;`--json` 印出違規字串的 JSON 陣列,乾淨時為 `[]`)、`assemble`(組裝 + 驗證,可選 `--score`)、`validate`(驗證既有 run-dir)、`score`(評分既有 run-dir)、`diff`(比較兩個已完成 run-dir 的版本差異)。`agentcli/` 內含八個檔案:`assemble.py`(組裝 agent 寫出的 JSON)、`input_schema.py`(pydantic 型別守衛)、`source_guard.py`(三項輸入邊界檢查,違規即 `exit 2` 且不建立 run 目錄:`source` 引用格式、`endpoints[].path` 根路徑、`path` 為 `null` 的 webhook/callback 端點必須帶 `summary`;`source` 以「檔案」為範圍——整份檔無一引用命中 manifest 才擋,部分命中則交給 validate 逐筆報 `SOURCE_UNVERIFIED`)、`cross_file.py`(純函式,檢查 `endpoints/*.json` 與 `inventory.json` 的六項跨檔不變式:端點檔數等於 inventory 筆數、身份多重集合相等(有 `path` 用 `(method, path)`,`path` 為 `null` 的 webhook/callback 端點改用 `(method, summary)`)、同一身份不得寫進兩個檔案、`schema_ref` 與 `security[]` 各自指向 inventory 既有的 schema/security scheme 名稱、`endpoints[].server` 需指向某個 `environments[].name`;null-path 端點不再豁免多重集合與重複檢查——`source_guard` 已在邊界保證它們必有 `summary`)、`gate.py`(`check_extraction`,`assemble` 與 `verify-extraction` 共用的唯一聚合閘門,兩個入口因此不可能漂移)、`verify.py`(`verify-extraction` 的薄殼:建 manifest → 讀擷取目錄 → 呼叫閘門;只讀不寫,不建立 run 目錄)、`extraction.py`(把 `inventory.json` 轉成 plan 各 stage 的初始答案)、`preprocess.py`(pymupdf4llm 把 PDF 轉 markdown)。`diff/` 內含四個檔案:`loader.py`(讀取已完成 run-dir 的產物,輸入有誤拋 `DiffInputError`)、`compare.py`(跨 `openapi.yaml`/`integration-contract.json`/`provenance.json`/`validation/report.json`/`manifest.json` 分類差異)、`models.py`(`DiffFinding`/`DiffImpact`/`DiffReport`)、`report.py`(輸出 `diff/report.{json,md}`)。`preparation/` 內含 `assess.py`(`assess_preparation` 把 manifest + inventory + endpoints + plan 評成就緒度報告,phase/finding、severity `error`/`warning`、status `blocked`/`needs_attention`/`ready`)與 `report.py`(寫出 `preparation-report.{json,md}`),在 `assemble` 內於 plan 之後、generate 之前執行,並被 `diff/` 讀回比較。`score/` 內含 `loader.py`(`load_score_inputs`)、`evaluate.py`(`evaluate_score`,五類加權 openapi_validity/completeness/consistency/source_grounding/reviewability → 0–100,`ci`/`review` profile)與 `report.py`(寫出 `score/score.{json,md}`),經 `score` 命令或 `assemble --score` 產生,不改變 validation pass/fail。

`manifest/scanner.py` 以 `DEFAULT_EXCLUDES`(`README*`/`LICENSE*`/`CHANGELOG*`/`CONTRIBUTING*`/`.DS_Store`/`.git/*`)加上 `--exclude` 傳入的 glob 排除非規格檔:命中者仍列在 `manifest.json` 但 `status: ignored`、不雜湊、不可作為來源證據(`plan/classify.py` 的 `_UNUSABLE` 含 `IGNORED`,故單一文件的 `sole_source` 歸因不會被一份 README 打斷)。

**檔案 I/O 出口**:只有 `generate/`(`generate_outputs`)、`run/`(`persist.py` 將計畫寫入 run-dir)、`preparation/report.py`(`write_reports` 寫出 `preparation-report.{json,md}`)、`diff/report.py`(`write_reports` 寫出 `diff/report.{json,md}`)與 `score/report.py`(`write_reports` 寫出 `score/score.{json,md}`)寫檔;其餘模組皆為純函式,便於單元測試。

## 資料流與關鍵 seam

| 階段 | 公開 seam | 產物 |
| --- | --- | --- |
| 前處理(可選) | `prepare_markdown(sources_dir, dest_dir)` → `PreprocessResult` / `pdf_to_markdown(pdf_path)` | `<WORK>/sources_md/`(PDF 轉 markdown;文字檔複製;其他來源 passthrough) |
| 擷取(agent 寫出) | —(agent 依 SKILL 寫檔) | `inventory.json` + `endpoints/*.json` |
| 組裝入口 | `run_assemble_pipeline(*, sources_root, extraction_dir, output_root, run_id, generated_at, urls)` | 整個 run-dir;`--json` 回報 `ok`/`run_dir`/`review_html`/`report` |
| 掃描 | `build_manifest(sources_root, urls, generated_at, excludes)` | `manifest.json` |
| inventory→plan 答案 | `inventory_to_stage_answers(inventory)` | plan 各 stage 的初始結構化答案 |
| 計畫 | `build_normalization_plan(extraction, manifest)` | `plan/normalization-plan.json` |
| 就緒度評估(產生前) | `assess_preparation(manifest, inventory, endpoint_texts, plan)` → `write_reports(report, run_dir)` | `<run-dir>/preparation-report.{json,md}` |
| 生成 | `generate_outputs(plan, manifest, run_dir)` | `openapi.yaml`、`api-guide.zh-TW.md`、`review.html`、`provenance.json`、`handoff/` |
| 驗證 | `validate_outputs(plan, result, manifest)`(純）／ `validate_run_dir(run_dir)`(讀檔) | `validation/report.{json,md}` |
| 評分(可選) | `load_score_inputs(run_dir)` → `evaluate_score(inputs, profile, min_score)` → `write_reports(report, score_dir)` | `<run-dir>/score/score.{json,md}` |
| 版本差異(可選) | `load_run_artifacts(run_dir)` → `build_diff_report(base, head)`(純）→ `write_reports(report, out_dir)` | `<head>/diff/report.{json,md}` |

`handoff/`(`integration-tasks.md`/`postman_collection.json`/`sdk-hints.json`)為衍生工程導引,由 `build_handoff(openapi, plan, integration)` 純函式產出,不做檔案 I/O、不重讀 `openapi.yaml`、不複製 schema;契約來源仍為 OpenAPI 與 integration-contract。

`build_diff_report` 比較兩個已完成 run-dir,依 downstream impact 把差異分類為 `breaking`／`additive`／`changed`／`source_only`(涵蓋 OpenAPI 路徑·方法·參數·schema·security·webhook、integration-contract、provenance、validation 摘要與 manifest;第一版不比較 Markdown guide 與 generated examples)。退出碼:`0`=完成、`2`=輸入 run-dir 缺檔或格式錯誤(`DiffInputError`)。

`run_assemble_pipeline` 會先驗證擷取輸入(`inventory.json` + `endpoints/*.json`)再建 run 目錄;輸入有誤時拋 `AssembleInputError`,CLI 以退出碼 `2` 結束、不留下孤兒目錄。退出碼:`0`=驗證 PASS、`1`=驗證 FAIL、`2`=擷取輸入檔錯誤。

### Foundry 資產層(`.foundry/api/`)

生成流程保持確定性且預設不信任:CLI 僅寫出 run 目錄,不做其他。**Foundry** 層是一個獨立、明確的治理步驟,將選定的 run 轉為受管的專案資產:

```
output/<run-id>/
  → foundry import  → .foundry/api/docsets/<docset-id>/candidates/<run-id>/   (候選資產)
  → foundry approve → .foundry/api/docsets/<docset-id>/assets/<asset-id>/     (已批准、版本化)
                      + current.json (供下游使用的確定性指標)
```

- **docset** 是一組來源文件的分組,這些文件共同定義一個 API 契約。
- **import** 將已完成的 run 複製到 `candidates/` 目錄(完整性由重用的 `diff` 載入器把關)。
- **approve** 將候選資產複製到自含、不可變的 `assets/<asset-id>/artifacts/` 目錄,記錄 `asset.json`(狀態、驗證、評分、來源雜湊、產物路徑、取代關係(supersedes)、批准元資料),取代先前的已批准資產,並更新 `current.json` / `docset.json` / `catalog.json`。
- 下游工作(SDK 編寫、CI 契約檢查、整合)經由 `foundry current` / `query.load_current_asset` 讀取**當前**資產,而不是任意的 run 目錄。

`openapi.yaml` 與 `integration-contract.json` 保持為權威契約;Foundry 逐字複製它們並加入治理,不改寫契約。

## 擷取分段

擷取採分段策略,避免單一回答承載全部內容(spec §7.1)。`loop_apidoc/extraction/` 提供 stage 與 question 模型,agent 依此分段擷取、`extraction.py` 再把 `inventory.json` 對映回各 stage 餵給 plan:

```
01 來源盤點                   06 逐 endpoint 細節（method/path/參數/req/resp/範例）
02 API 系統概覽與術語          07 共用 schema / enum / 資料限制
03 環境 / base URL / 版本      08 錯誤碼與失敗行為
04 驗證 / 授權 / 簽章          09 rate limit / timeout / retry / idempotency / webhook
05 Endpoint 清單              10 來源衝突、缺漏、無法確認事項
```

agent 擷取會收斂成 `inventory.json`(系統概覽 + endpoint 清單 + 共用 schema/錯誤碼等盤點)與逐 endpoint 的 `endpoints/*.json`,作為後段 plan→generate→validate 的輸入。

## 來源追溯與驗證對齊

`provenance.json` 的 `target` 字串與 OpenAPI 位置**逐一對齊**(如 `paths.{path}.{method}`、`components.schemas.{name}`、`components.securitySchemes.{name}`),驗證的禁止推測檢查即在這些 target 上做交叉比對:任何進入輸出的內容都必須能追溯回具來源依據的計畫項目,否則視為違規。
