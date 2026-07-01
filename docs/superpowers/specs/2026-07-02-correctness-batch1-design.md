# 正確性修正第一批(correctness batch 1)設計

日期:2026-07-02
狀態:已與使用者確認設計,待實作
範圍來源:2026-07-02 整體健檢(架構/測試/功能三路審視)第一級發現

## 背景

整體健檢找出三項正確性/資料遺失風險,彙整為第一批修正。三項互相獨立,
共用同一分支 `fix/correctness-batch1`,全程 TDD(先寫失敗測試再修)。

本批**不含**新能力(如 `.docx`→markdown 轉換)與架構收斂(loader 重複、
死碼清除等,屬第二批)。

## 1. `preprocess` 不再靜默丟棄來源

### 現況

`loop_apidoc/agentcli/preprocess.py` 的 `prepare_markdown`:

- `.pdf` → `pdf_to_markdown` 轉成 `<stem>.md`
- `.md` / `.markdown` / `.txt` → 原樣複製
- **其他副檔名(`.docx`、`.json`、`.yaml`、`.html` …)→ 不寫入、不警告**

但 README 明列 Word 與 OpenAPI JSON/YAML 為支援的來源格式。任何依 SKILL
把 `<EXTRACT_SOURCES>` 指到 `sources_md/` 的 run,這些來源會憑空缺料。

### 設計

- 非 PDF、非文字白名單的**所有其他檔案**一律以位元組原樣(binary-safe)
  複製到 `dest_dir`,歸類為 `passthrough`。
- `prepare_markdown` 回傳值從 `Path` 改為 frozen dataclass
  `PreprocessResult`:
  - `dest_dir: Path`
  - `converted: list[Path]`(PDF→md)
  - `copied: list[Path]`(文字白名單複製)
  - `passthrough: list[Path]`(其他格式原樣複製)
  - 三個清單記 dest 端相對路徑,排序穩定。
- 唯一呼叫端 `cli.py` 的 `preprocess` 命令改印分類摘要:
  `converted N / copied M / passthrough K`,並逐行列出 passthrough 檔名
  (提示這些檔案未經轉換,agent 需自行判讀)。
- 同名碰撞維持現行「後寫覆蓋」語意不變(rglob 排序穩定),不在本批擴大。

### 驗收

- `.docx` / `.json` / `.yaml` 來源出現在 `dest_dir` 且位元組相同。
- 回傳的 `PreprocessResult` 三清單分類正確。
- CLI stdout 含分類摘要與 passthrough 清單。
- 既有 pdf / md 行為與測試不變。

## 2. `assemble --score` 不再吞任意例外

### 現況

`loop_apidoc/cli.py` assemble 命令的 score 區塊:

```python
except ScoreInputError as exc:
    score_error = str(exc)
    ...
except Exception as exc:          # ← 吞掉 score 模組任何 bug
    score_error = f"score failed: {exc}"
    ...
```

### 設計

- 移除 `except Exception` 分支。只保留 `ScoreInputError`(可預期的輸入
  問題)維持現有降級行為:設 `score_error`、印 stderr、繼續輸出 assemble
  主結果與 exit code。
- 其他例外直接上拋(traceback)。assemble 主流程產物此時已落地於
  run-dir,不會遺失;裸 traceback 指向 score 的真實 bug,優於靜默。
- `--json` payload 的 `score_error` 欄位語意不變(只在 `ScoreInputError`
  時出現)。

### 驗收

- `ScoreInputError` 路徑行為不變(既有測試繼續通過)。
- 注入非 `ScoreInputError` 的例外(monkeypatch `evaluate_score`)時,
  CLI 上拋而非降級為 `score_error`。

## 3. diff 修兩個誤報

### 3a. object→scalar 結構變更雙重回報

`loop_apidoc/diff/compare.py` 的 `_compare_schema`:頂層 signature 改變時
發出 `schema changed`(BREAKING),之後仍無條件走 property 層 diff——
base 為 object、head 為 scalar 時,base 的每個子屬性再各發一筆
`property removed`,雜訊淹沒重點。

**設計**:當 base 與 head 的 signature 型別在「object ↔ 非 object」之間
翻轉時,發出 `schema changed` 後**提前 return**,抑制 property /
required 層的後續 walk。兩邊皆為 object(僅其他 signature 欄位變動)時
行為不變。

### 3b. provenance entry 順序誤報

`_provenance_map` 對每個 `target` 以來源出現順序 append entry,
`_compare_provenance` 直接以 list 相等比較——entry 重排但語意相同會
誤報 `SOURCE_ONLY`。

**設計**:`_provenance_map` 在每個 target 分組內依
`(manifest_source, query_id)` 排序後再比較(target 已是分組 key),
使比較對順序不敏感。

### 驗收

- 3a:object→scalar 的 fixture 只產生一筆 BREAKING `schema changed`,
  無 property removed;既有 33 個 diff+CLI 測試綠燈。
- 3b:entry 重排但內容相同的 fixture 不產生任何 finding;真實內容變更
  仍回報。
- 新測試依既有 diff 測試風格斷言 `DiffImpact` enum identity。

## 收尾(隨本批一併)

- `docs/PIPELINE_FOLLOWUPS.md` item 8:標記第 1、4、5 項為 resolved
  (健檢確認先前已修),本批修掉第 2(3a)、3(3b)項後亦標記;
  第 6(CLI summary `.get`)與 7(覆蓋缺口)維持 open 待第二批。
- 延後清單中「examples 編碼一致性」「generator 原生 oneOf/discriminator」
  經健檢確認已實作,予以銷帳;保留「path 參數不在 URL 樣板時被靜默丟棄」
  為新的已知邊角。
- `docs/ARCHITECTURE.md` seam 表的 `prepare_markdown` 回傳型別同步更新。

## 測試策略

全程 TDD。新增/調整測試落點:

- `tests/test_cli_preprocess.py` 與 `tests/agentcli/`:passthrough
  複製、分類清單、CLI 摘要輸出。
- `tests/test_cli_assemble.py`:score 例外上拋 regression。
- `tests/diff/test_compare_openapi.py`:object→scalar 單筆回報。
- `tests/diff/test_compare_supporting_artifacts.py`:provenance 重排
  不誤報。
