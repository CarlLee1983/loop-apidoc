# loop-apidoc skill 拆分 + 對齊設計

> 把單一 256 行的 `skills/loop-apidoc/SKILL.md` 重構為「精簡編排層 + 按需參考檔」,
> 同時消除 skill 文字與現行程式碼之間的漂移。風格依循 superpowers 的
> `writing-skills`(一個 SKILL.md + 數個參考檔,漸進揭露)。

## 背景與問題

`SKILL.md` 是 Claude Code plugin 與 OpenAI Codex CLI **共用的單一可攜檔**(靠 `<APIDOC>`
佔位符與工具名中性化達成可攜)。它每次進 session 都整份載入,但其中約 100 行是擷取用的
JSON schema、約 40 行是只在驗證失敗時才需要的修正細節——這些「重型且只在特定階段才需要」
的內容墊高了每次的載入成本。

同時,skill 文字與程式碼已出現漂移(經兩支唯讀稽核 subagent 實證,附 `file:line`):

- `assemble --json` 實際輸出 **6 個 key**,skill 只記 4 個。
- 每個 issue 實際有 **9 個欄位**,skill 漏 `auto_fixable`。
- 「以 issue 碼分 fixable / fail-closed」與程式碼不符:真正的通過閘是 **severity**
  (有任何 ERROR 才 FAIL;WARNING 不擋),`CorrectionCategory` 是死碼。
- skill 只命名 6 個 issue 碼中的 3 個。
- exit 2 除了擷取輸入錯誤,也由 **run 目錄碰撞** 觸發。
- 證據檢查把 `examples/` 與 `integration-contract.json` 說成「來源有才產出」,實際 **恆產出**
  (空/`<placeholder>` 即「無資料」訊號);且漏列恆產出的 `preparation-report.{json,md}`
  與 `plan/normalization-plan.json`。
- 證據檢查要求在 `review.html` 看「validation summary」,但該頁 **不含** 驗證摘要,只連到
  `validation/report.md`。

## 目標

1. **結構**:`SKILL.md` 瘦成 ~130 行的編排層;重型內容外移到 `reference/`,按需載入。
2. **對齊**:skill 描述的 CLI 契約、產物、issue 模型與修正策略,逐項對齊程式碼事實。
3. **可攜性零回歸**:仍是 `skills/loop-apidoc/` 單一目錄,Codex 安裝說明不變(symlink 一個目錄,
   參考檔隨之帶入;無跨 skill 解析需求)。
4. **驗證延後**:本次只做基本內部一致性(連結可達、內容無遺失),不跑 benchmark / 不做 skill-TDD。

## 設計:結構

```
skills/loop-apidoc/
  SKILL.md                      # 編排層 ~130 行(每次載入,保持精簡)
  reference/
    extraction-schemas.md       # 三份擷取 JSON schema + 全部欄位慣例 ~120 行
                                #   → 僅擷取期(步驟 2–4)按需載入
    assemble-and-correction.md  # assemble --json 契約、Issue 模型、severity 閘、
                                #   六碼策略、結構化路由、run_dir 產物全圖、
                                #   review.html 區塊對照 ~90 行
                                #   → 僅處理 assemble 結果 / 修正(步驟 5–7)時載入
```

### 各檔職責與載入時機

| 檔 | 內容 | 何時載入 |
| --- | --- | --- |
| `SKILL.md` | 核心 invariant、`<APIDOC>` 解析、線性流程摘要、**subagent 契約 + grounding rule**、來源前處理(精簡 inline)、assemble 呼叫與 happy-path、證據檢查、其他指令、Important | 每次 |
| `reference/extraction-schemas.md` | inventory / endpoint / integration 三份 schema 逐欄、巢狀 dotted-path、`one_of`/`discriminator`、webhooks、英文 key 規則、容忍鍵(`enum`/`location`/`schema`)、檔名與檔數核對 | 擷取中段 |
| `reference/assemble-and-correction.md` | `--json` 6 key、Issue 9 欄、severity 閘、六碼意義+回應、結構化路由修正法、fail-closed 原則、run_dir 產物全圖、review.html 區塊、exit code | 驅動 assemble / 修正失敗時 |

「來源前處理」評估後留在主檔 inline:它屬線性 happy-path,且 PDF/URL 是最常見輸入,留 inline
讓常見情境一檔自足(取捨:不外移成第三個參考檔)。

## 與程式碼對齊:漂移修正清單

| # | 現況 | 事實(file:line) | 修正落點 |
|---|---|---|---|
| 1 | `--json` 4 key | 6 key:`run_id/run_dir/review_html/ok/status/report`(`cli.py:184-193`) | assemble-and-correction.md |
| 2 | Issue 5+3 欄 | 9 欄含 `auto_fixable`(`validate/models.py:22-33`);結構化欄未設為 `null` | assemble-and-correction.md |
| 3 | 以碼分 fixable/fail-closed | 閘是 severity(`models.py:40-41`);`auto_fixable=True` 僅 integration 三處(`integration.py:97,115,185`);`CorrectionCategory` 死碼 | assemble-and-correction.md(改教看 severity + 結構化路由) |
| 4 | 命名 3/6 碼 | 6 碼俱在(`models.py:8-14`) | assemble-and-correction.md(全列) |
| 5 | exit 2 = 擷取輸入錯誤 | 2 也由 run 目錄碰撞觸發(`cli.py:176-181`) | assemble-and-correction.md + SKILL Important |
| 6 | examples/`integration-contract.json` 條件產出 | 恆產出;空/`<placeholder>`=無資料(`writer.py:46-56`、`plan/integration.py:102`、`examples.py:44`) | SKILL 證據檢查 + 參考檔 |
| 7 | review.html 有 validation summary | 無;只連 `validation/report.md`(`review.py:57,471`) | SKILL 證據檢查 + 參考檔(列真實區塊) |
| 8 | 產物清單漏列 | 恆產出 `preparation-report.{json,md}`、`plan/normalization-plan.json` | SKILL 證據檢查 + 參考檔 |
| 9 | schema 容忍鍵未提 | guard 容忍 `enum`/`location`/`schema`(`input_schema.py:32`);endpoints 以字典序讀檔(`assemble.py:62`) | extraction-schemas.md(補註;建議檔名補零 `ep00.json`) |

## 流程與範圍

1. 把目前未提交的 WIP 改動(preflight、EXTRACT_SOURCES、URL 快取、檔數核對、證據檢查)中的
   好料整理進新結構,不佳處重寫。
2. 寫本設計稿並 commit;再實作三個 skill 檔。
3. 基本一致性檢查(連結可達、內容無遺失、字數預算)。
4. **範圍外**:`CLAUDE.md` 也有同款「以碼分類」的 fail-closed 段落(與程式碼同樣不精準),本次不動,
   僅標記為後續可選跟進。

## 取捨 / 風險

- **參考檔 vs 跨 skill**:選一目錄內參考檔(非並列子 skill),以保 Codex 可攜性與「單一可攜檔不分叉」
  的既有設計不變量。
- **內容外移的風險**:主檔對重型內容改用「摘要 + 指向參考檔」,需確保指向明確、agent 會在對的階段
  載入;故主檔每個外移點都留一句「見 reference/…」並說明何時需要。
- **不重寫語意**:schema 內容經稽核屬準確,逐字保留;改動集中在「結構搬移 + 後半段契約對齊」。
