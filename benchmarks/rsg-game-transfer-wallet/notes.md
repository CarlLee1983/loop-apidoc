# rsg-game-transfer-wallet

## Source

- Official URL: https://docs.rsg-games.com/transfer/zh-tw/#api
- Downloaded at: 2026-08-17（rebind，見下節）
- Document version: 1.28.0
- Source format: public HTML snapshot → `normalize-html-snapshot` → Markdown
- Raw snapshot: `raw/docs.rsg-games.com-transfer-zh-tw.html`，SHA-256
  `665669f9c4aeaea547278f73d47621a55de327f42f75f435c691f723f5b33da9`（與 sources/ 同為
  gitignored；`.source.json` sidecar 綁定這份 raw 的 digest 與正規化時間）
- 第二份來源 `rsg-game-transfer-wallet.zh-TW.md` 是 2026-07-16 的 WebFetch 純文字傾印
  （1.27.0，單行、無 sidecar），**刻意保留**：它是本案 `SOURCE_UNVERIFIED` 與
  `SOURCE_FACTS_UNSCANNED` 兩個 warning 的來源，也是「語料裡混有零引用來源」這個形狀的
  fixture。它不被任何主張引用，288 筆引用全部指向正規化後的 1.28.0 快照。

## Rebind 2026-08-17（issue #110）

原始 raw HTML 落在一個已消失的暫存路徑（舊 sidecar 的 `raw_file` 指向
`/var/folders/.../tmp.CWTTjSgzOl/`），所以 2026-07-23 那份正規化產出**無法重新導出**，
改動前後的差異只能整體記錄、不能逐項歸因。這次重新取源並把 raw 收進 case，之後就能。

以 1.27.0 舊產出對照今天的 1.28.0 產出（1,918 → 1,805 行，711 → 704 個表格列，687 列完全
相同），差異分三類：

1. **正規化行為**：行內連結現在保留成 `[代碼表](#b)`，舊產出剝成純文字「請參照 代碼表」。
   受影響的引用區間有 12 個，主張本身不變。
2. **文件內容（1.27.1、1.28.0 兩筆版本變更）**：5-2 存入點數與 5-3 取出點數的「特定回傳
   錯訊代碼一覽」新增 `3020 Deny deposit and withdraw for player.`；多個章節新增
   「傳入參數說明」「回傳資訊說明」標籤列。
3. **行號位移**：新產出的目錄區塊多出約 99 行，其餘章節整體下移。

17 個被引用的區間全部重新錨定到新快照的章節邊界並重算 `fragment_digest`；主張內容一字未
改，只搬位置。`sanitized_sources/` 與 `sanitized-fixture.json` 依新的行座標重新產生。

**未納入的新事實**：`3020` 位於各端點自己的「特定回傳錯訊代碼一覽」，不在 8-1 錯誤代碼表
裡。本案的 scope 從一開始就只收 8-1（見下節），端點層的特定錯誤碼表 1.27.0 時也沒有擷取，
所以這不是本次 rebind 造成的漏擷。要收它需要先擴張 scope，屬於另一次改動。

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
  `X-API-Timestamp`; DES-CBC body encryption. This scheme was named
  `RSG Signature` until commit `123083e` (2026-07-24) renamed it to the
  documented header, leaving `details` untouched — one scheme throughout, never
  two. The archived run under `output/20260716T072005.471369Z/` therefore emits
  the old key `RSG_Signature`, and `expected/minimum.json` kept naming the old
  label until #137 rewrote the declaration as the emitted key. A `RSG_Signature`
  found in an old artifact is that rename, not a missing scheme.
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

- If RSG publishes additional concrete code rows, refresh extraction and re-record
  `counts.error_codes` with the source revision — the snapshot moves in either
  direction, and the diff is where the reason gets stated.
- Expand the endpoint subset only after extracting each request/response example
  with its source citation.
