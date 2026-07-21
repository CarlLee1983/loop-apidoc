# 來源品質報告

結論：**pass**

## SQ-001：missing-base-url

- 等級：warning
- 證據：vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md entire file (lines 1-51); same gap confirmed across all 40 pages including vg-wen-dang.md, dan-yi-qian-bao/api.md, zhuan-zhang-qian-bao/jia-mi-shuo-ming.md, and both fu-lu/* trees — Every endpoint page documents only a root-relative path (e.g. POST /bet, POST /vg/sign-in, POST /vgtransfer/points). No page in the 40-file set states a scheme+host, a sandbox endpoint, or a production endpoint. A package-wide search for base url/host/server/domain/sandbox/production/环境 returns no matches outside GitBook documentation-site URLs, which are doc links rather than API endpoints.
- 請補：Provider must supply the actual scheme+host (and any sandbox vs production distinction) that these relative paths are mounted under, so an OpenAPI servers block carries a grounded value instead of a placeholder.
- 驗收：At least one page in the source package states a concrete base URL, or explicitly documents multiple environment URLs, that every relative path in the package is appended to.

## SQ-002：error-codes-not-enumerated

- 等級：warning
- 證據：vg-wen-dang/dan-yi-qian-bao/fu-lu/xiang-ying-dai-ma.md lines 7-33 (full response-code table) — The 单一钱包 wallet endpoints under api/qian-bao/* (tou-zhu, qu-xiao-tou-zhu-jie-suan, pai-cai, chong-xin-pai-cai, yuecha-xun) use a distinct envelope {"code": 0, "balance": ...} on success, different from the {"code": 1000, "message": ..., "data": ..., "TraceId": ...} envelope used elsewhere. Only success examples are shown for those five endpoints. The only response-code appendix enumerates 1000, 1001, 1002 and 5000-5043, none of which is 0, and it does not state which endpoint family it applies to.
- 請補：Provider must supply the non-zero code values and meanings returnable by /bet, /cancel, /win, /resettle and /balance, or confirm that they reuse the 1000/5000-series table with 0 substituted for success.
- 驗收：A response-code table or explicit statement covering the code:0 envelope wallet endpoints' failure codes exists in the source package.

## SQ-003：signing-algorithm-underspecified

- 等級：warning
- 證據：vg-wen-dang/dan-yi-qian-bao/jia-mi-shuo-ming.md hint block line 8 and JS/Python examples lines 11-50 — The signing rule states only: sort parameter keys, concatenate their values, append API_KEY, then MD5. The worked example uses two required string fields with no optional and no numeric fields. Signed endpoints such as 登入游戏 (optional rid, betlimit) and 游戏结果 (optional roundid, betid, status) and tou-zhu.md (numeric amount) are not covered: the source never states whether an absent optional field is omitted or concatenated as an empty string, nor how numeric values are stringified. The identical gap exists in zhuan-zhang-qian-bao/jia-mi-shuo-ming.md.
- 請補：Provider must clarify the sign-string construction for absent optional parameters and for non-string values, with a worked example covering both.
- 驗收：The encryption page explicitly states the treatment of absent optional parameters and non-string values in the sign concatenation, with an example covering both cases.

## SQ-004：malformed-request-table

- 等級：warning
- 證據：vg-wen-dang/dan-yi-qian-bao/api/you-xi/you-xi-jie-guo.md lines 19-31 (Body parameter table, broken by blank line 23) — The request-parameter table for 游戏结果 (POST /vg/bet/users) is broken by a blank line inside the starttime row, terminating the GFM table at line 22. Rows for endtime, roundid, betid, page_num, page_size, status and sign fall outside any parseable table even though the prose is present; markdown-api-facts.json captured only agent plus a type-less starttime and recorded omitted_tables: 3. The identical malformed table exists in zhuan-zhang-qian-bao/api/you-xi/you-xi-jie-guo.md.
- 請補：The parameter table must be re-read from the raw prose during extraction so endtime, roundid, betid, page_num, page_size, status and sign are not silently dropped by table parsing.
- 驗收：The 游戏结果 request-parameter table in both products parses as one well-formed Markdown table covering all documented fields with type/required/description intact.
