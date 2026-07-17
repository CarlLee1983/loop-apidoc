# loop-apidoc 0.12.0 release notes

Release date: 2026-07-18

## Summary

新增來源新鮮度排程閘門:record-fingerprint / check-freshness 兩指令與 loop_apidoc/freshness/ 套件,讓排程比對來源、同版跳過解析、改版才重跑

## Changed

- 新增 `record-fingerprint` 指令:從已完成/採用的 run 目錄寫出 `source-fingerprint.json`
  基準側檔(本地來源以 sha256、每個 URL 來源各抓一次版本訊號);既有檔案不覆寫,除非 `--force`。
- 新增 `check-freshness` 指令:排程用的便宜前置閘門,重算各來源訊號並與基準比較。退出碼
  `0` 未變(略過重新解析)、`1` 變動(需重跑)、`2` 無法判定(來源連不上/需認證/搬移)。
  支援 `--sources`、`--json`、`--report-dir`。
- 分層變動訊號:機器可讀 OpenAPI 來源以 `info.version` 為準(同版即跳過,即使 bytes 不同);
  HTML 走 HTTP 條件請求(ETag/Last-Modified)再退 body sha256;本地檔用 sha256。
- 新增 `loop_apidoc/freshness/` 套件(models/signals/record/check/report),純函式為主,
  僅 `record.py`/`report.py` 為寫出口。
- skill 新增 `reference/freshness-scheduling.md`(無頭排程 loop 指引)與可執行範例
  `examples/freshness-scheduling/check-and-refresh.sh`。
- v1 限制:HTML 以原始 body 雜湊(尚無內容正規化);不偵測來源新增/移除(只重查基準內既有來源)。

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
