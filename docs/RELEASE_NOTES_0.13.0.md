# loop-apidoc 0.13.0 release notes

Release date: 2026-07-18

## Summary

新增 check-freshness-batch:以巡檢清單(freshness-watchlist.json)一次比對多份文件來源,彙總成一份報表,退出碼決定性匯總 0/1/2

## Changed

- 新增 `check-freshness-batch` 指令:讀一份巡檢清單 `freshness-watchlist.json`
  (每項含 `label`/`fingerprint`,可選 `sources`/`run_dir`;相對路徑相對於清單檔目錄),
  對每個 docset 逐一跑 `check-freshness` 並彙總成一份報表。
- 決定性匯總退出碼:任一項變動→`1`(需重跑);否則有任一無法判定/錯誤→`2`(告警);
  全部未變→`0`(略過)。單項出錯記為 `error` 不中斷整批;清單檔本身壞掉才 fail-loud。
- `--report-dir` 另存彙總報表 `freshness-scan.{json,md}`;`--json` 輸出機器可讀結果。
- 新增 `loop_apidoc/freshness/batch.py`(`load_watchlist` + `scan_watchlist`,重用既有
  `check_freshness`,單項錯誤捕捉,自身不寫檔);`report.py` 新增批次報表輸出。
- skill `reference/freshness-scheduling.md` 加「Batch scan」段;範例
  `examples/freshness-scheduling/` README 補批次用法。

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
