# 設計:loop-apidoc SKILL 可攜化(Claude Code + Codex 雙棲)

> 日期:2026-06-27 · 狀態:已核可,待實作

## 目標

讓**同一份** `skills/loop-apidoc/SKILL.md` 同時在 Claude Code plugin 與 OpenAI Codex CLI 兩個 agent runtime 運作,不分叉成兩份檔案。兩者皆以 `~/.codex/skills/<dir>/SKILL.md`(Codex)或 plugin 機制(Claude)載入相同格式的 skill。

## 背景與限制

現行 SKILL.md 綁了兩個 Claude 專屬假設:

1. **`${CLAUDE_PLUGIN_ROOT}`** —— 用於 `uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc`。Codex 不會設這個環境變數,直接搬過去會失效。
2. **Claude 工具名** —— `Read` / `Grep` / `Glob` / `WebFetch` / `defuddle`、以及「dispatch a subagent restricted to read-only tools (Read/Grep/Glob)」。Codex 有自己的 shell 與 subagent 機制(omx `multi_agent = true`、`.codex/agents`)。

跨平台 skill 慣例:skill 應以「動作」描述(讀檔、搜尋、抓取 URL),而非寫死單一 runtime 的工具名。

## 設計

### 1. CLI 呼叫橋接(核心)

SKILL.md 頂部新增「CLI invocation」一節,定義一次規則,後續指令用佔位符 `<APIDOC>` 代表 CLI 前綴:

- 環境有 `$CLAUDE_PLUGIN_ROOT`(Claude plugin 安裝時自動帶入)→ `uv run --project "$CLAUDE_PLUGIN_ROOT" loop-apidoc`
- 否則(Codex / 獨立)→ 直接呼叫全域 `loop-apidoc`(由 `uv tool install` 安裝)

附一段 **bash/zsh 行為一致、空白安全** 的陣列 snippet 供需要決定性的 agent 照貼:

```bash
RUN=(loop-apidoc); [ -n "$CLAUDE_PLUGIN_ROOT" ] && RUN=(uv run --project "$CLAUDE_PLUGIN_ROOT" loop-apidoc)
"${RUN[@]}" assemble --sources "<SOURCES>" --extraction "<WORK>" --output "<OUT>" --json
```

**為何用陣列而非 `${CLAUDE_PLUGIN_ROOT:+...}` inline 展開**:後者在 bash 會正確切詞,但 zsh 預設不對未加引號的 `${...}` 做 word splitting,會把 `uv run --project /path loop-apidoc` 整段當成單一參數而失效(實測確認)。陣列指派 `RUN=(...)` 與 `"${RUN[@]}"` 在 bash/zsh 行為一致。

只有 `preprocess` 與 `assemble` 兩處是真正的 CLI 呼叫,改動範圍小。

### 2. 工具名中性化

把 Claude 專屬工具名換成動作描述,保留 orchestration / 唯讀 subagent fan-out 語意:

| 原文 | 改為 |
| --- | --- |
| subagents read the file directly with Read | 由 subagent 直接讀檔 |
| Grep/Glob | 搜尋 |
| fetch as text with WebFetch or defuddle | 以文字抓取 URL |
| subagent restricted to read-only tools (Read/Grep/Glob — no web, no write) | 唯讀 subagent(僅檔案讀取與搜尋,禁網路、禁寫入) |

### 3. 安裝文件

README 與 CONTRIBUTING 各補一段 Codex 安裝路徑:

```bash
uv tool install --from /path/to/repo loop-apidoc                     # 全域 loop-apidoc 指令
ln -s /path/to/repo/skills/loop-apidoc ~/.codex/skills/loop-apidoc   # 掛入 Codex skills
```

## 驗證

- 只改 Markdown,`uv run pytest` 與 `uv run ruff check .` 不受影響(回歸保險)。
- 人眼確認 Claude 端 `${CLAUDE_PLUGIN_ROOT}` 行為向後相容(有設仍走 `uv run --project`)。
- 陣列 snippet 已在 bash 與 zsh 各自驗證:root 設(含空白路徑)→ 4 段前綴正確;root 未設 → 退成單一 `loop-apidoc`。

## 非目標(YAGNI)

- 不提供自動化 install 腳本(使用者選擇手動文件)。
- 不分叉成 Codex 專用 SKILL 副本。
- 不改動 plan→generate→validate 後段 pipeline。
