# 貢獻指南

歡迎為 `loop-apidoc` 貢獻。本文件說明開發環境、工作流程與送出變更前的檢查清單。

## 開發環境

需求:Python `>=3.11`、[`uv`](https://docs.astral.sh/uv/)。

```bash
uv sync                      # 安裝相依(含 dev group)
uv run loop-apidoc --help    # 確認 CLI 可執行
```

擷取由 agent 擔任引擎(`run-agent` 以子行程 `claude -p`,或 agent-native plugin 由當前 agent 直接讀來源);`run-agent` 需本機可執行的 agent CLI(預設 `claude`,可用 `--executable` 替換)。

### 跨 agent runtime 的 skill

`skills/loop-apidoc/SKILL.md` 設計為**單一可攜檔**,同時供 Claude Code plugin 與 OpenAI Codex CLI 載入。維護時請守住可攜性:

- CLI 一律以佔位符 `<APIDOC>` 表示,規則定義在 SKILL 頂部「CLI invocation」一節 —— 有 `$CLAUDE_PLUGIN_ROOT` 走 `uv run --project`,否則退到全域 `loop-apidoc`。**勿**寫死 `uv run --project "${CLAUDE_PLUGIN_ROOT}" …`。
- 環境前綴用陣列寫法(`RUN=(...)`;`"${RUN[@]}"`),bash/zsh 行為一致且空白安全。**勿**用 `${VAR:+…}` inline 展開(zsh 不切詞會壞)。
- 描述 agent 行為時用**動作**(讀檔、搜尋、抓取 URL)而非單一 runtime 的工具名(Read/Grep/Glob/WebFetch)。

Codex 端安裝步驟見 [`README.md`](README.md#在-openai-codex-cli-使用)。

## 核心原則

任何變更都必須維持專案的根本契約:

1. **以來源為唯一事實依據** —— 不得讓 pipeline 推測或以慣例補寫來源不存在的內容。缺漏必須顯性標記(`x-loop-status: missing-source` + provenance),而非靜默填補。
2. **驗證 fail-closed** —— 無法確認的來源、缺漏的必要欄位、來源衝突一律使驗證失敗,不可放行。
3. **生成層是唯一檔案 I/O 出口** —— `loop_apidoc/generate/` 與 `loop_apidoc/run/` 之外的模組應為純函式,便於測試。新增邏輯時優先設計成可注入 seam 的純函式。
4. **擷取與後段解耦** —— 兩種 agent 擷取模式都收斂成 `inventory.json` + `endpoints/*.json`,再交給共用的 plan→generate→validate;外部行程(`run-agent` 的子行程 CLI)一律經 `agentcli/` 的 runner 呼叫,不在核心流程直接耦合。

## 程式風格

- **不可變優先**:回傳新值而非就地修改輸入(Pydantic 用 `model_copy(update=...)`、dataclass 用 `replace`)。
- **小檔案**:高內聚低耦合,單檔以 200–400 行為宜、800 行為上限;從大模組抽出工具函式。
- **錯誤處理**:在有足夠上下文的邊界處理;在系統邊界(使用者輸入、外部 API)驗證,內部呼叫信任。保留原始錯誤的 cause chain。
- **不留除錯輸出**:送出前移除暫時性 `print` 與除錯碼。
- 中文為預設語言(註解、文件);commit message 依 Conventional Commits,語言依變更內容而定。

執行 lint:

```bash
uv run ruff check .
```

## 測試

採 TDD:先寫測試(RED)→ 最小實作(GREEN)→ 重構(IMPROVE)。

```bash
uv run pytest                      # 全套件
uv run pytest --cov=loop_apidoc    # 含覆蓋率
uv run pytest tests/plan/          # 單一套件
```

- 純函式以單元測試覆蓋;file-I/O 的 seam(`generate_outputs` / `run_assemble_pipeline`)以整合測試覆蓋。
- 兩種 agent 擷取模式(`run-agent` / `assemble`)以注入 fake runner 或預先寫好的擷取 JSON 測試,不需真實 agent CLI。

> **已知**:`tests/plan/test_classify.py` 的兩個 path-boundary 測試曾出現一次無法重現的偶發失敗;目前判定為一次性 heisenbug(非順序、非 hash-seed 相依)。若你穩定重現了它,請附上環境與 seed 開 issue。

## 提交流程

1. 從 `main`(或 `master`)開新分支,勿直接在主幹上開發。
2. 小步提交,訊息遵循 Conventional Commits:

   ```
   <type>: [ <scope> ] <subject>
   ```

   `type` ∈ `feat` / `fix` / `docs` / `style` / `refactor` / `perf` / `test` / `chore`。
3. 送 PR 前確認:

   - [ ] `uv run pytest` 全綠
   - [ ] `uv run ruff check .` 無錯誤
   - [ ] 新邏輯有對應測試,且維持上述核心原則
   - [ ] 沒有硬編碼祕密、沒有殘留除錯輸出
   - [ ] 變更涉及 CLI／輸出結構時,同步更新 `README.md`

## 專案結構

各套件職責見 [`README.md`](README.md#套件結構);整體流程與資料流見 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。完整設計 spec 與分階段實作 plan 位於 `docs/superpowers/`。
