# loop-apidoc 0.11.2 release notes

Release date: 2026-07-17

## Summary

normalize-html-snapshot 保留表格與程式碼區塊,manifest 掃描忽略 provenance sidecar

## Changed

- `normalize-html-snapshot`:`html_to_markdown` 現在將 `<table>` 轉為 Markdown 管線表格(先前被壓成單行,可能造成參數/型別錯位),並保留 `<pre>` 程式碼區塊內的換行(先前被折成空白)。表格與 `pre` 區塊會消化其子節點,避免儲存格/行內容被重複輸出。
- manifest 掃描:`DEFAULT_EXCLUDES` 新增 `*.source.json`,使 `normalize-html-snapshot` 自身寫出的 provenance sidecar 不再被誤掃為 openapi-json 來源。

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
