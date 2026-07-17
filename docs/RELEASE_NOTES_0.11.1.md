# loop-apidoc 0.11.1 release notes

Release date: 2026-07-17

## Summary

修正 oauth2/openIdConnect security scheme 產出無效 OpenAPI 的問題(缺 flows/openIdConnectUrl 必填子欄位),改走 missing-source placeholder 並將機制保留於描述;mutualTLS 維持原生。

## Changed

- **Fix:** an `oauth2` (or `openIdConnect`) security scheme no longer produces an
  invalid OpenAPI document. A bare `{"type": "oauth2"}` is invalid because
  `flows`/`openIdConnectUrl` are required, and the source-grounded extraction
  contract carries no field for them — previously this made `assemble` fail with
  `OPENAPI_INVALID`. The generator now falls through to the existing
  missing-source `apiKey` placeholder, preserving the scheme identity and details
  in its `description` rather than fabricating a flow/URL.
- `mutualTLS` remains emitted natively (it has no required sub-fields).
- Adds regression tests that validate the emitted document with
  `openapi-spec-validator`.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
