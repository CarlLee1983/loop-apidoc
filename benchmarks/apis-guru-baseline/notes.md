# apis-guru-baseline

## Source

- Official URL: https://raw.githubusercontent.com/APIs-guru/openapi-directory/main/APIs/apis.guru/2.2.0/openapi.yaml
- Downloaded at: 2026-06-28
- Document version: APIs.guru 2.2.0(OpenAPI 3.0.0)
- Source format: OpenAPI(machine-readable;與 NewebPay PDF 形成兩極對照)
- Source restoration (2026-07-23): the file last changed at commit
  `fa500d341c242326279e64402a547ff7c0717e0d` (2023-04-05). A snapshot from that
  immutable commit was written to the ignored
  `sources/apis-guru-2.2.0.openapi.yaml`; SHA-256
  `dee46291d885be9ed36daabdb050e988afc5e8337760c36ad059fc440be5abb2`.
  It is byte-identical to the previously recorded `main` URL, and its acquisition
  is recorded in `url_sources/coverage.json`.

## Scope

- Included: APIs.guru 目錄查詢 API 全部 7 個 GET endpoint、4 個 schema(API/APIs/ApiVersion/Metrics)
- Excluded: 無(整份 spec 已涵蓋)

## Expected Coverage

- Base URLs: https://api.apis.guru/v2
- Critical endpoints: GET /list.json、GET /specs/{provider}/{api}.json
- Auth/signing: 無(root `security: []`,公開 API)— 正是本 case 的測試重點
- Callback/webhook: 無
- Error codes: 無(spec 僅文件化 200)

## Run Log

- preprocess: 不需要(來源已是 OpenAPI yaml,subagent 直接讀)
- 擷取: 1×inventory + 1×endpoints(7 GET,陣列)。無 integration.json(無加解密/callback)。
- assemble: 初跑 FAIL(1 error + 7 warning,揭 no-auth 誤判)→ **修 _has_auth_marker 後重跑 PASS**(7 warning)
- validate: OpenAPI 3.1 **VALID**;provenance 38 entries
- run_dir: `output/20260628T141216Z`(PASS;gitignore)

## Result

- Status: **PASS**(初跑 FAIL 揭 1 項 pipeline gap → 修復後重跑 PASS)
- 產物達成度:7 paths(GET + path 參數 required)、4 components.schemas、$ref 正確連結、servers/info 正確、7×三語 examples、provenance 38、OpenAPI 3.1 valid。
- Issues(8):
  - 1× **REQUIRED_INFO_MISSING/error** @ components.securitySchemes:「無 security scheme,且來源未明確標示未提供 authentication」— **誤判**(見 Findings)。
  - 7× warning:各 endpoint 缺 examples(GET 且 spec 無 example;產出仍含 curl/ts/py,faithful)。
- Missing source info(faithful):無錯誤碼文件、providers/services 回傳 inline 匿名物件(非 named schema)、path 參數無 description — 皆正確進 missing。
- False positives:1×(no-auth error,見下)。
- False negatives:無。

## Findings(本 case 揭出的 pipeline gap)

1. ✅ **[strictness/false-positive] 公開(no-auth)API 被誤判為缺 authentication**:來源明示 `security: []` 且無 securitySchemes(= 公開,非缺漏)。`validate/completeness.py` 的 `_has_auth_marker` 只掃 `missing_items` 找 area 含 auth/security 的項目;本 case 把「公開無需驗證」記在 `operational`(topic=Authentication)→ 不被認可 → 硬 ERROR。
   - 根因:pipeline 把「auth 未文件化(gap)」與「auth 明示為無(public)」混為一談。
   - **修**:`_has_auth_marker` 同時認可 `operational` 中 topic 含 authentication/security 的項目(來源已明確交代 auth)。含 RED→GREEN 測試;baseline 重跑 PASS。

## Follow-up

- Validator changes:`_has_auth_marker` 認可 operational 的 authentication 註記(讓公開 API 能 PASS)。
- 其餘:warning 級 examples 屬來源缺漏,無需處理。

## Exact-evidence parity (2026-10-07)

以 `uv run loop-apidoc snapshot-openapi-url --url https://raw.githubusercontent.com/APIs-guru/openapi-directory/fa500d341c242326279e64402a547ff7c0717e0d/APIs/apis.guru/2.2.0/openapi.yaml --filename apis-guru-2.2.0.openapi.yaml --confirmed-by-user`
重新取得 `sources/apis-guru-2.2.0.openapi.yaml`,SHA-256 與上方紀錄相同(`dee46291…`),產出的 coverage 與已入庫 `url_sources/coverage.json` 相同。

- 每個 material claim 都以 v1 `evidence[]` 綁定 exact JSON Pointer:7 個 operation(method/path/summary/response)、path 參數(`$ref` 者指向 `components.parameters`,inline `service` 指向 operation 參數)、4 個 schema 與其欄位(含巢狀 `thisWeek.*`)、server。
- `APIs` schema 的 example 含未加引號的 YAML 時間戳;需 #184(bridge 改用 domain serializer)才能完成 shadow replay。
- Shadow replay:legacy `passed` / Core `accept`,12/12 Core claims supported、0 unverified。本 case 已列入 `EXACT_EVIDENCE_PARITY_BENCHMARK_CASES`。
- 值校正(非綁定,經核准;理由皆為「來源未逐字陳述此值」):
  1. environment `name` `"default"` → `null`:來源 `servers` 只有 `url`。
  2. `GET /providers.json`、`GET /{provider}/services.json` 的 response description → 來源的 `OK`;原本附帶的 inline schema 說明已在 `missing`。
  3. 移除 5 筆 `operational`(Authentication / Path parameters / License / Contact / External documentation):topic 非來源字串,detail 為改寫或多值拼接。公開 API 的驗證事實改記於 inventory `missing`(文字含 authentication),`_has_auth_marker` 仍成立。
  4. `Metrics.datasets` → `datasets[]`:來源為 `type: array`,與 Core 推導的結構名稱一致。
  5. 移除 `APIs.{*}` 與 `API.versions.{*}`,改記於各自 schema 的 `missing`:兩者代表 `additionalProperties` map,目前的擷取契約無法表示;舊產出把它們輸出成名為 `{*}` 的屬性。
- 因此 legacy warning 由 9 增為 12(`expected/validation.expect.json` 已同步):`operational` 為空 1 筆,`GET /list.json` 與 `GET /{provider}.json` 的成功 response schema `APIs` 已無可表示欄位 2 筆。
