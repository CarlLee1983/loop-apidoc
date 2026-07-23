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
