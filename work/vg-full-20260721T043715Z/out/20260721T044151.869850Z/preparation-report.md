# Preparation Readiness Report

Overall status: `needs_attention`

## Summary

| Phase status | Count |
| --- | ---: |
| blocked | 0 |
| needs_attention | 4 |
| ready | 1 |

## Sources

Status: `ready`

| Metric | Value |
| --- | ---: |
| local_sources | 80 |
| successful_urls | 1 |
| supported_local_sources | 40 |
| unreadable_sources | 0 |
| unsupported_sources | 0 |

No findings.

## Extraction

Status: `needs_attention`

| Metric | Value |
| --- | ---: |
| endpoint_detail_files | 20 |
| endpoint_missing_items | 64 |
| inventory_endpoints | 20 |
| inventory_missing_items | 4 |

| Severity | Finding | Target | Suggested action |
| --- | --- | --- | --- |
| warning | inventory missing item: API base URL not stated in sources | `inventory.json/missing/0` | re-read source material and fill or justify this inventory gap. |
| warning | inventory missing item: Document/API version not stated | `inventory.json/missing/1` | re-read source material and fill or justify this inventory gap. |
| warning | inventory missing item: Error HTTP status mapping not stated | `inventory.json/missing/2` | re-read source material and fill or justify this inventory gap. |
| warning | inventory missing item: Error code applicable endpoints not stated | `inventory.json/missing/3` | re-read source material and fill or justify this inventory gap. |
| warning | endpoint missing item: HTTP status code not documented | `endpoints/ep0.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: body field required flags not documented | `endpoints/ep0.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: failure/error response body not documented | `endpoints/ep0.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: HTTP status code not documented | `endpoints/ep1.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: required flags not documented for agent, language, loginname, return_url, token, sign | `endpoints/ep1.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: failure/error response body not documented | `endpoints/ep1.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: HTTP status code not documented | `endpoints/ep2.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: failure/error response body not documented | `endpoints/ep2.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: conditional required semantics for starttime/endtime when roundid or betid is provided not fully specified | `endpoints/ep2.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: HTTP status code not documented | `endpoints/ep3.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: body field required flags not documented | `endpoints/ep3.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: failure/error response body not documented | `endpoints/ep3.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: HTTP status code not documented | `endpoints/ep4.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: body field required flags not documented | `endpoints/ep4.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: failure/error response body not documented | `endpoints/ep4.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: complete list of limit codes not documented (only example codes A and A1 shown) | `endpoints/ep4.json/missing/3` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: HTTP status code not documented | `endpoints/ep5.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: body field required flags not documented | `endpoints/ep5.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: failure/error response body not documented | `endpoints/ep5.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: response field meanings documented only via JSON example, not prose | `endpoints/ep5.json/missing/3` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: detail sub-fields have no field-description table (types inferred from Body params JSON example only) | `endpoints/ep6.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for the response | `endpoints/ep6.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no failure-response body documented | `endpoints/ep6.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: required/optional not stated for Header or Body fields | `endpoints/ep6.json/missing/3` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: detail sub-fields have no field-description table (types inferred from Body params JSON example only) | `endpoints/ep7.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: detail.settletime, detail.percentage, detail.fanshui, detail.detail have null in example so type unknown | `endpoints/ep7.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for the response | `endpoints/ep7.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no failure-response body documented | `endpoints/ep7.json/missing/3` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: required/optional not stated for Header or Body fields | `endpoints/ep7.json/missing/4` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: detail sub-fields have no field-description table (types inferred from Body params JSON example only) | `endpoints/ep8.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: detail.settletime, detail.percentage, detail.fanshui, detail.detail have null in example so type unknown | `endpoints/ep8.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for the response | `endpoints/ep8.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no failure-response body documented | `endpoints/ep8.json/missing/3` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: required/optional not stated for Header or Body fields | `endpoints/ep8.json/missing/4` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no Body params JSON request example on this page | `endpoints/ep9.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: detail field structure not documented beyond type object | `endpoints/ep9.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for the response | `endpoints/ep9.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no failure-response body documented | `endpoints/ep9.json/missing/3` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: required/optional not stated for Header or Body fields | `endpoints/ep9.json/missing/4` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no request-body JSON example on this page | `endpoints/ep10.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for the response | `endpoints/ep10.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no failure-response body documented | `endpoints/ep10.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: required/optional not stated for Header or Body fields | `endpoints/ep10.json/missing/3` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no request-body JSON example on this page | `endpoints/ep11.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for the response | `endpoints/ep11.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no failure-response body documented | `endpoints/ep11.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: required/optional not stated for Header or Body fields | `endpoints/ep11.json/missing/3` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for Success response | `endpoints/ep12.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no error response documented | `endpoints/ep12.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for Success response | `endpoints/ep13.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no error response documented | `endpoints/ep13.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for Success response | `endpoints/ep14.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no error response documented | `endpoints/ep14.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for Success response | `endpoints/ep15.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no error response documented | `endpoints/ep15.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for Success response | `endpoints/ep16.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no error response documented | `endpoints/ep16.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: starttime and endtime requiredness is conditional on roundid/betid usage | `endpoints/ep16.json/missing/2` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for Success response | `endpoints/ep17.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no error response documented | `endpoints/ep17.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for Success response | `endpoints/ep18.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no error response documented | `endpoints/ep18.json/missing/1` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no HTTP status code documented for Success response | `endpoints/ep19.json/missing/0` | re-read source material for this endpoint and fill the missing field. |
| warning | endpoint missing item: no error response documented | `endpoints/ep19.json/missing/1` | re-read source material for this endpoint and fill the missing field. |

## Normalization Plan

Status: `needs_attention`

| Metric | Value |
| --- | ---: |
| missing_items | 68 |
| source_conflicts | 0 |
| unverified_items | 0 |

| Severity | Finding | Target | Suggested action |
| --- | --- | --- | --- |
| warning | plan missing item: 10: API base URL not stated in sources | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 10: Document/API version not stated | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 10: Error HTTP status mapping not stated | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 10: Error code applicable endpoints not stated | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: HTTP status code not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: body field required flags not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: failure/error response body not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: HTTP status code not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: required flags not documented for agent, language, loginname, return_url, token, sign | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: failure/error response body not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: HTTP status code not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: failure/error response body not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: conditional required semantics for starttime/endtime when roundid or betid is provided not fully specified | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: HTTP status code not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: body field required flags not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: failure/error response body not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: HTTP status code not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: body field required flags not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: failure/error response body not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: complete list of limit codes not documented (only example codes A and A1 shown) | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: HTTP status code not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: body field required flags not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: failure/error response body not documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: response field meanings documented only via JSON example, not prose | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: detail sub-fields have no field-description table (types inferred from Body params JSON example only) | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for the response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no failure-response body documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: required/optional not stated for Header or Body fields | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: detail sub-fields have no field-description table (types inferred from Body params JSON example only) | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: detail.settletime, detail.percentage, detail.fanshui, detail.detail have null in example so type unknown | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for the response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no failure-response body documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: required/optional not stated for Header or Body fields | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: detail sub-fields have no field-description table (types inferred from Body params JSON example only) | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: detail.settletime, detail.percentage, detail.fanshui, detail.detail have null in example so type unknown | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for the response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no failure-response body documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: required/optional not stated for Header or Body fields | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no Body params JSON request example on this page | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: detail field structure not documented beyond type object | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for the response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no failure-response body documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: required/optional not stated for Header or Body fields | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no request-body JSON example on this page | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for the response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no failure-response body documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: required/optional not stated for Header or Body fields | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no request-body JSON example on this page | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for the response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no failure-response body documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: required/optional not stated for Header or Body fields | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for Success response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no error response documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for Success response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no error response documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for Success response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no error response documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for Success response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no error response documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for Success response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no error response documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: starttime and endtime requiredness is conditional on roundid/betid usage | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for Success response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no error response documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for Success response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no error response documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no HTTP status code documented for Success response | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |
| warning | plan missing item: 06: no error response documented | `inventory.json` | re-read source material and update the extracted answer that feeds this plan field. |

## Integration Contract

Status: `needs_attention`

| Metric | Value |
| --- | ---: |
| callbacks | 5 |
| crypto | 2 |
| field_conditions | 6 |
| missing_items | 4 |
| test_cases | 2 |

| Severity | Finding | Target | Suggested action |
| --- | --- | --- | --- |
| warning | integration contract missing item: callbacks.base_url: 来源将钱包页标为「商户接口」，但未给出商户托管回调的 base URL / host | `integration.json/missing/0` | re-read source material and complete integration.json or record why it is absent. |
| warning | integration contract missing item: callbacks.trigger: 未说明各商户接口何时由平台发起 | `integration.json/missing/1` | re-read source material and complete integration.json or record why it is absent. |
| warning | integration contract missing item: crypto.optional_params: 可选参数缺席时是否省略于签名串，来源未另述 | `integration.json/missing/2` | re-read source material and complete integration.json or record why it is absent. |
| warning | integration contract missing item: crypto.numeric_stringification: 数值栏位串接前如何转成字串未说明 | `integration.json/missing/3` | re-read source material and complete integration.json or record why it is absent. |

## URL Coverage

Status: `needs_attention`

| Metric | Value |
| --- | ---: |
| auth_required | 0 |
| empty_suspect | 0 |
| expected | 40 |
| fetch_failed | 0 |
| fetched | 40 |
| not_fetched | 0 |
| url_sources | 1 |

| Severity | Finding | Target | Suggested action |
| --- | --- | --- | --- |
| warning | expected URL list was not confirmed by a human | `url_sources/coverage.json/confirmed_by_user` | Review the discovered page list with the user, or accept it as machine-discovered only. |
