# loop-apidoc 0.32.0 release notes

Release date: 2026-08-07

## Summary

靜態 HTML 快照正規化保留文件結構：根節點選取、巢狀清單與具標籤連結。

## Changed

- `html_to_markdown` 依 `main` → `article` → `body` → 文件根的順序選取單一根節點，
  並持續排除 `aside`、`footer`、`nav`、`script`、`style`、`template`。
- 巢狀有序／無序清單以決定性方式輸出：保留來源中重複的清單項，並且不因包裹元素
  （如 `div`）而重複父項文字。
- 具標籤的 `<a>` 以 `[label](href)` 呈現，href 原樣保留、不做 URL 解析；無標籤的
  連結不產生任何輸出。
- 表格、跳脫直線、多行 `pre` 區塊與原始檔 SHA-256 provenance sidecar 行為不變；
  取得來源、爬取、JS 轉譯與 provenance 範圍皆未更動（issue #37）。

## Strategy impact

- [x] None — 這次變更只影響已下載 HTML 的可讀化呈現；原始 HTML 仍是唯一權威證據，
  來源接地政策、取得流程與產品方向都沒有改變。
- [ ] Updated — <list each strategy document changed>

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
