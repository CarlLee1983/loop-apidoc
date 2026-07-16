# rsg-game-transfer-wallet

## Source

- Official URL: https://docs.rsg-games.com/transfer/zh-tw/#api
- Downloaded at: 2026-07-16
- Document version: 1.27.0
- Source format: public HTML snapshot → Markdown

## Scope

- Included: transfer-wallet API request/response envelope, DES-CBC encryption,
  MD5 signature headers, 12 representative endpoints, and the section 8-1
  error-code table.
- Excluded: the remaining documented endpoints not extracted in this focused
  regression case, FTP details, and game/currency/language catalogues.

## Expected Coverage

- Base URL: one documented server placeholder.
- Critical endpoints: member creation, deposit, withdrawal, transaction-result lookup.
- Auth/signing: `X-API-ClientID`, `X-API-Signature` (MD5),
  `X-API-Timestamp`; DES-CBC body encryption.
- Error codes: all 15 entries in section 8-1, with source citations and any
  explicitly documented operation applicability.

## Run Log

- Source capture: URL corpus snapshot from the official RSG documentation.
- Extracted: inventory + integration + 12 endpoint detail files.
- Assemble: PASS (11 warnings, no errors).
- Validate: OpenAPI 3.1 valid.

## Result

- Status: **PASS**.
- The official table currently contains **15**, not 17, concrete error-code
  rows: `0`, `1001`, `1002`, `2001`, `2002`, `3005`, `3006`, `3008`, `3010`,
  `3011`, `3012`, `3014`, `3015`, `3016`, and `3018`.
- This case guards Issue #13: `ErrorCode` must retain the source-grounded
  code-to-message mapping in `x-loop-error-code-map`; application values remain
  separate from HTTP response status codes.
- 11 endpoint warnings are faithful missing examples, not validation errors.

## Follow-up

- If RSG publishes additional concrete code rows, refresh extraction and raise
  `error_codes_min` with the source revision.
- Expand the endpoint subset only after extracting each request/response example
  with its source citation.
