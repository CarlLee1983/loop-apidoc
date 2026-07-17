# loop-apidoc 0.11.0 release notes

Release date: 2026-07-17

## Summary

新增舊版 PDF 多方法端點與來源缺口保真改善

## Changed

- 支援以 `methods` 表示同一路徑共用同一份契約的多個 HTTP 方法，並在組裝前正規化為個別 OpenAPI operations。
- 對 HTTP 方法加入嚴格驗證：拒絕空白、重複、空白包覆或不支援的方法，同時保留既有小寫單一 `method` 的相容性。
- 當來源明確標示「範例」缺失時，警示仍會保留，但評分不再將其誤判為未揭露的文件品質缺口。
- 若來源未提供可用於 path operation 的 concrete server URL，完整性驗證會提出可追溯警示。
- 新增 JiLi 舊版繁中 PDF benchmark fixture，涵蓋 25 個 operations 及上述來源缺口語意。

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
