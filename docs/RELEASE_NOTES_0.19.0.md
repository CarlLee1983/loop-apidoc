# loop-apidoc 0.19.0 release notes

Release date: 2026-07-21

## Summary

Adds single-file source support and schema-field-level evidence tracing for more precise provenance validation.

## Changed

- `manifest --sources` now accepts either a local source directory or one local
  source file. For a single file, its parent is used as `sources_root` and the
  manifest includes only the selected file.
- Schema fields may carry their own optional source citation. When present, the
  generated provenance records the exact OpenAPI schema-property target, making
  evidence and no-speculation checks more precise for nested fields and arrays.

## 繁體中文摘要

`manifest --sources` 現在可接受本機來源目錄或單一來源檔案；單一檔案會以其父目錄作為
`sources_root`，且 manifest 僅納入該檔案。schema 欄位也可各自提供選填的來源引用，讓
provenance 與禁止推測檢查能對應到精確的 OpenAPI 屬性位置（含巢狀欄位與陣列）。

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
