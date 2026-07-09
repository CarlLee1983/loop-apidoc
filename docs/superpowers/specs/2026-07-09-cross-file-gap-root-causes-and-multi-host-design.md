# 跨檔偵測缺口、根因收斂與多主機端點:設計

日期:2026-07-09
對應 issue:[#7](https://github.com/CarlLee1983/loop-apidoc/issues/7)、[#4](https://github.com/CarlLee1983/loop-apidoc/issues/4)、[#8](https://github.com/CarlLee1983/loop-apidoc/issues/8)

## 背景

`loop-apidoc` 的擷取層在 2026-07-09 放寬了寫入契約:端點 subagent 自行寫 `endpoints/ep<N>.json`,不再把完整 JSON 搬運回 orchestrator 的 context。這個交換把「搬運」換成「驗證」——`agentcli/cross_file.py` 的五條跨檔不變式負責攔截所有會**遺失資料**的失效模式。

本設計處理該交換留下的一個缺口,外加兩項獨立的改善。三者互不衝突,落在同一組檔案與測試,一併實作。

---

## 一、#7:null-path 端點的身份鍵

### 問題

不變式 2(`(method, path)` 多重集合相等)與不變式 3(同一端點不得出現在兩個檔)目前豁免 `path: null` 的 webhook/callback 端點。原因是端點檔裡沒有任何欄位能區分兩個 null-path 端點,`(method, path)` 會把它們全部塌成同一個鍵 `POST ?`。

當 inventory 有**兩個以上**全為 null-path 的端點時,以下失效模式無法偵測:

- subagent 把 webhook A 的內容寫進兩個檔,webhook B 的檔從沒被寫出
- 不變式 1(數量)看到 `2 == 2`,通過
- 不變式 2、3 把兩個 null-path 端點都過濾掉,沉默
- 結果:B 的資料靜默遺失,零違規

**這個缺口在 benchmark 裡是活的。** `benchmarks/newebpay-mpg/` 有三個 null-path webhook(`ep7`/`ep8`/`ep9` = NotifyURL / ReturnURL / CustomerURL),而這三個端點檔目前都沒有 `summary`。

### 決策

`summary` 就是 null-path 端點的身份。這不是新發明的概念:`generate/naming.py:71` 的 `webhook_items` 早就用 `summary` 幫 webhook 產生 OpenAPI `webhooks` 的鍵名。閘門看不到它,只是因為 `EndpointDetailInput` 沒有這個欄位。

被否決的替代方案:

- **用 `(method, source)` 當鍵** — 兩邊都已有 `source`,零 schema 變更。但 `plan/builder.py:331` 的註解明講:同一頁上的多個 webhook 會塌成同一個 `manifest_source`。換個欄位塌一次,盲區沒真的關掉。
- **用檔名索引 `ep<N>` ↔ `inventory.endpoints[N-1]`** — 最簡單,但推翻 `cross_file.py:9-11` 明文的既有設計決策(「Deliberately set-based, never index-based」)。generation 完全不看檔名,兩個檔內容互換沒有下游後果、不該被拒。
- **新增專屬的 `webhook_id` 短欄位** — 憑空發明一個來源文件裡不存在的概念,違反 source-grounded 的核心不變式。

### 實作

1. `agentcli/input_schema.py`:`EndpointDetailInput` 新增 `summary: str | None = None`。
2. `agentcli/cross_file.py`:
   - `_key` 改為:`path` 是字串時用 `(method, path)`;否則用 `(method, summary)`。
   - `_keyed` 的 null-path 豁免整個移除。不變式 2、3 恢復全覆蓋。
   - summary 比對前做空白正規化:`" ".join(s.split())`。這些敘述很長、跨行複製容易差一個空格;除此之外要求逐字相符。
3. `agentcli/source_guard.py`:新增邊界檢查——端點檔 `path` 為 null 時 `summary` 必填,否則 `exit 2`,訊息指名檔案。

### 範圍界線

`plan/builder.py:329` 用 locator + `manifest_source` 配對 path-less webhook detail 的啟發式,在有了 `summary` 之後可以改成直接用 summary 配對。**本次不碰。** 那是獨立的清理,與關閉缺口無關;混進來只會擴大 diff 與迴歸面。

### 相容性

`benchmarks/newebpay-mpg/extraction/endpoints/ep{7,8,9}.json` 需補上 `summary`(逐字取自 `inventory.json` 對應條目)。補完之後 benchmark harness 應仍 PASS——這同時證明新的必填欄位沒有打破既有行為。

---

## 二、#4:validation report 的根因收斂

### 問題

一個根因(`integration.json` 的 `source` 格式不合)在 `validation/report.json` 裡展開成 32 筆各自獨立的 issue,evidence 全是同一句話。SKILL.md 指示 orchestrator 依 `location` + `suggested_fix` 逐一重讀該 scope——照做會觸發 32 次 requery,但正確動作是對 `integration.json` 做一次統一改寫。issue 的粒度把 O(1) 的修法誤導成 O(n)。

(觸發此 issue 的具體場景已被 #1 消掉:不合格的 `source` 現在在 assemble 輸入邊界就被擋下。但底層問題對其他 issue code 仍然成立。)

### 決策

純加法。`ValidationReport` 新增 `root_causes: list[RootCause]`,`issues[]` 一個字不動。

被否決的替代方案:

- **把同根因的 issues 塌成單筆,帶 `affected_locations`** — report 更短,但改變 `issues[]` 的語意:issue 數不再等於問題點數。既有消費端(`score/`、`review.html`、benchmark 測試)全要跟著改。收益不值這個破壞。
- **只改 `suggested_fix` 文案** — 最小改動,但 orchestrator 仍看到 32 筆、仍可能 requery 32 次。issue 的核心抱怨沒解決。

### 實作

1. `validate/models.py` 新增:

   ```python
   class RootCause(BaseModel):
       code: IssueCode
       severity: Severity
       target_file: str
       fix_once: str
       affected_locations: list[str]
   ```

   `ValidationReport` 新增 `root_causes: list[RootCause] = Field(default_factory=list)`。

2. 分組鍵 `(code, severity, target_file)`。**只在 `target_file` 非 null 且組內 ≥2 筆時**產出一筆 `RootCause`。

   `target_file` 為 null 的 issue 不分組。沒有可靠的一次修完目標,硬分組只會製造假的根因。`severity` 進鍵是因為混合嚴重度的組無法給出單一 `fix_once`。

3. `fix_once` 來自一張 per-code 對照表,只填有實證的條目;查不到就沿用組內共同的 `suggested_fix`(若組內 `suggested_fix` 不一致,同樣沿用第一筆——分組鍵已保證同 code 同檔,文案差異不影響動作)。

4. `validate/report.py` 的 `render_markdown` 在有 `root_causes` 時,於 issue 清單前加一節「根因(優先處理)」。

### 不變式

`ok` / severity 閘 / exit code / `score` 全部不受影響。這是刻意的:消費端可以完全無視 `root_causes`,行為不變。

---

## 三、#8:endpoints[].server 多主機支援

### 問題

`endpoints[].path` 剝除 base URL 前綴後(#2 已修),當一份文件有兩個以上 base URL 時(實例:`{api_url}` 與 `{getBetData_url}`,5 支報表類端點在後者),「哪支端點在哪個主機」這個來源明載的事實,在目前的 schema 裡沒有欄位可以承載。

### 實作

1. `inventory.endpoints[]` 支援可選的 `server`,值指向 `environments[].name`。
2. `agentcli/cross_file.py` 新增第六條不變式:`server` 若存在,必須解析得到某個 `environments[].name`。精神上與現有 `schema_ref` / `security[]` 的解析檢查同構,但**迭代對象是 `inventory.endpoints[]` 而非端點檔**(`server` 住在 inventory 側),因此獨立成 `_server_violations(inventory)`,不塞進逐檔迭代的 `_reference_violations`。
3. `generate/openapi.py`:該欄位存在時,為該 operation 產出 operation-level `servers: [{url, description}]`,取自對應 environment 的 `base_url` / `name`。OpenAPI 3.1 允許 operation 覆寫 root `servers`。
4. 欄位缺席時行為完全不變(沿用 root-level `servers`)。

---

## 測試策略

TDD:先寫測試,確認 RED,再實作。

`cross_file` / `source_guard` 是純函式,三項都能單元測試。

關鍵測試(#7):**兩個端點檔寫同一個 webhook、第三個 webhook 沒人寫**——inventory 三筆、檔案三個,數量不變式通過,但現在必須被不變式 2、3 抓到。這正是 issue #7 描述的失效模式,也是修正前會靜默放行的那一個。

其餘:

- #7:null-path 且無 summary → `exit 2`,訊息指名檔案。
- #7:summary 只差空白 → 通過(正規化生效)。
- #4:同 `(code, severity, target_file)` 的 2 筆以上 → 產出一筆 `RootCause`;`target_file` 為 null → 不分組;單筆 → 不分組。
- #4:`root_causes` 不改變 `report.ok`。
- #8:`server` 指向不存在的 environment name → 違規;指向存在的 → operation-level `servers` 出現在 OpenAPI 且通過 3.1 schema 驗證;欄位缺席 → 產物與現況逐字相同。
- benchmark harness(`tests/test_benchmarks.py`)在 `ep{7,8,9}.json` 補上 summary 後仍全數 PASS。

## 文件

- `skills/loop-apidoc/reference/extraction-schemas.md`:null-path 端點的 `summary` 規則(含正反例)、`endpoints[].server` 欄位與 `environments[].name` 的關係。
- `skills/loop-apidoc/reference/assemble-and-correction.md`:`root_causes` 的消費方式——correction loop 應優先消費 `root_causes`,再處理未被分組的 `issues`。
- `CLAUDE.md`:`cross_file.py` 的不變式數量由五條改為六條。
