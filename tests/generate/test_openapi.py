from __future__ import annotations

from loop_apidoc.generate.openapi import (
    MISSING_STATUS,
    X_LOOP_STATUS,
    build_openapi,
)
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    NormalizationPlan,
    PlanItemStatus,
    SchemaEntry,
    SecuritySchemeEntry,
    SystemGroup,
)


def _plan(**kw) -> NormalizationPlan:
    return NormalizationPlan(notebook_url="https://nb/x", **kw)


def test_openapi_version_and_empty_paths():
    doc = build_openapi(_plan())
    assert doc["openapi"] == "3.1.0"
    assert doc["paths"] == {}


def test_info_uses_system_group_title_and_env_version():
    plan = _plan(
        system_groups=[SystemGroup(name="Loop Payments API")],
        environments=[
            EnvironmentEntry(status=PlanItemStatus.SUPPORTED, version="2024-01")
        ],
    )
    info = build_openapi(plan)["info"]
    assert info["title"] == "Loop Payments API"
    assert info["version"] == "2024-01"
    assert X_LOOP_STATUS not in info


def test_info_uses_document_version_over_env_version():
    plan = _plan(
        system_groups=[SystemGroup(name="藍新金流手冊", version="NDNF-1.2.2")],
        environments=[
            EnvironmentEntry(status=PlanItemStatus.SUPPORTED, version="2.3")
        ],
    )
    info = build_openapi(plan)["info"]
    assert info["title"] == "藍新金流手冊"
    assert info["version"] == "NDNF-1.2.2"
    assert X_LOOP_STATUS not in info


def test_info_marks_missing_when_no_source():
    info = build_openapi(_plan())["info"]
    assert info["title"] == "Untitled API"
    assert info["version"] == "0.0.0"
    assert info[X_LOOP_STATUS] == MISSING_STATUS


def test_servers_only_from_base_url():
    plan = _plan(
        environments=[
            EnvironmentEntry(
                status=PlanItemStatus.SUPPORTED, name="prod",
                base_url="https://api.example.com",
            ),
            EnvironmentEntry(status=PlanItemStatus.MISSING, name="staging"),
        ]
    )
    doc = build_openapi(plan)
    assert doc["servers"] == [
        {"url": "https://api.example.com", "description": "prod"}
    ]


def test_no_servers_key_when_none_have_base_url():
    doc = build_openapi(_plan(environments=[
        EnvironmentEntry(status=PlanItemStatus.MISSING, name="prod")
    ]))
    assert "servers" not in doc


def test_security_scheme_known_apikey():
    plan = _plan(security_schemes=[
        SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth",
            type="apiKey", location="header", details="X-API-Key",
        )
    ])
    schemes = build_openapi(plan)["components"]["securitySchemes"]
    assert schemes["ApiKeyAuth"] == {
        "type": "apiKey", "in": "header", "name": "X-API-Key"
    }


def test_security_scheme_unknown_type_is_placeholder():
    plan = _plan(security_schemes=[
        SecuritySchemeEntry(
            status=PlanItemStatus.UNVERIFIED, name="WeirdAuth",
            type="hmac-signature", location="header", details="X-Sig",
        )
    ])
    scheme = build_openapi(plan)["components"]["securitySchemes"]["WeirdAuth"]
    assert scheme["type"] == "apiKey"
    assert scheme[X_LOOP_STATUS] == MISSING_STATUS
    # the procedure text/details are NOT fabricated into the apiKey `name`
    assert scheme["name"] == "unknown"
    # identity, kind and details are all preserved in the description
    assert "WeirdAuth" in scheme["description"]
    assert "hmac-signature" in scheme["description"]
    assert "X-Sig" in scheme["description"]


def test_signing_scheme_keeps_algorithm_in_description_not_name():
    # NewebPay's "schemes" are request-signing/body-encryption procedures, not
    # apiKey auth. The algorithm must live in `description`, never in `name`, and
    # the body-param location (illegal for apiKey) must not be asserted as real.
    plan = _plan(security_schemes=[
        SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED,
            name="SHA256 檢查碼（TradeSha / HashData_）",
            type="雜湊", location="請求/回應 body 參數",
            details="於 AES 加密字串前加 HashKey=...，整串 SHA256 後轉大寫",
        )
    ])
    schemes = build_openapi(plan)["components"]["securitySchemes"]
    scheme = next(iter(schemes.values()))
    assert scheme["type"] == "apiKey"
    assert scheme[X_LOOP_STATUS] == MISSING_STATUS
    assert scheme["name"] == "unknown"
    assert "SHA256 後轉大寫" not in scheme["name"]
    assert "於 AES 加密字串前加" in scheme["description"]
    assert "SHA256 檢查碼" in scheme["description"]
    assert "雜湊" in scheme["description"]
    # "body 參數" is not a legal apiKey location → placeholder header, flagged missing
    assert scheme["in"] == "header"


def test_endpoint_becomes_path_operation():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List users",
            parameters=[{"name": "limit", "in": "query", "type": "integer"}],
            responses=[{"status": "200", "description": "ok", "schema": {"type": "array"}}],
        )
    ])
    op = build_openapi(plan)["paths"]["/users"]["get"]
    assert op["summary"] == "List users"
    assert op["parameters"] == [
        {"name": "limit", "in": "query", "schema": {"type": "integer"}}
    ]
    assert op["responses"]["200"]["description"] == "ok"
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {"type": "array"}


def test_path_parameter_forced_required():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="get", path="/users/{id}",
            parameters=[{"name": "id", "in": "path", "type": "string"}],
            responses=[{"status": "200", "description": "ok"}],
        )
    ])
    param = build_openapi(plan)["paths"]["/users/{id}"]["get"]["parameters"][0]
    assert param["required"] is True


def test_request_body_mapped():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/users",
            request={"schema": {"type": "object"}, "required": True},
            responses=[{"status": "201", "description": "created"}],
        )
    ])
    body = build_openapi(plan)["paths"]["/users"]["post"]["requestBody"]
    assert body["required"] is True
    assert body["content"]["application/json"]["schema"] == {"type": "object"}


def test_missing_responses_get_default_placeholder():
    plan = _plan(endpoints=[
        EndpointEntry(status=PlanItemStatus.SUPPORTED, method="GET", path="/ping")
    ])
    responses = build_openapi(plan)["paths"]["/ping"]["get"]["responses"]
    assert responses["default"][X_LOOP_STATUS] == MISSING_STATUS


def test_endpoint_without_path_or_method_skipped():
    plan = _plan(endpoints=[
        EndpointEntry(status=PlanItemStatus.MISSING, method=None, path="/x"),
        EndpointEntry(status=PlanItemStatus.MISSING, method="GET", path=None),
    ])
    assert build_openapi(plan)["paths"] == {}


def test_schema_object_with_required_and_enum_field():
    plan = _plan(schemas=[
        SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="User",
            fields=[
                {"name": "id", "type": "string", "required": True},
                {"name": "role", "type": "string", "enum": ["admin", "user"]},
            ],
            constraints="id 為 UUID v4",
        )
    ])
    schemas = build_openapi(plan)["components"]["schemas"]
    user = schemas["User"]
    assert user["type"] == "object"
    assert user["properties"]["id"] == {"type": "string"}
    assert user["properties"]["role"]["enum"] == ["admin", "user"]
    assert user["required"] == ["id"]
    assert user["description"] == "id 為 UUID v4"


def test_string_enums_emitted_as_x_enum_values_on_parent():
    # Per the SKILL contract, schemas[].enums may be a list of freeform strings
    # ("Field: value=meaning"). These are not cleanly machine-parseable, so they
    # are preserved faithfully on the parent object schema as x-enum-values
    # rather than invented into structured enum components.
    plan = _plan(schemas=[
        SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="PaymentType",
            fields=[],
            enums=["CREDIT=信用卡", "VACC=ATM 轉帳"],
        )
    ])
    schemas = build_openapi(plan)["components"]["schemas"]
    pt = schemas["PaymentType"]
    assert pt["type"] == "object"
    assert pt["x-enum-values"] == ["CREDIT=信用卡", "VACC=ATM 轉帳"]


def test_named_enum_becomes_component():
    plan = _plan(schemas=[
        SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="Order",
            fields=[{"name": "status", "type": "string"}],
            enums=[{"name": "OrderStatus", "values": ["new", "paid"]}],
        )
    ])
    schemas = build_openapi(plan)["components"]["schemas"]
    assert schemas["OrderStatus"] == {"type": "string", "enum": ["new", "paid"]}


def test_method_only_endpoint_becomes_webhook_not_path():
    # An endpoint with a method but no path is an async callback → OpenAPI 3.1
    # top-level `webhooks`, keyed by the summary's leading label, never `paths`.
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path=None,
            summary="付款結果通知（綠界 POST 至商店 ReturnURL）",
            parameters=[{"name": "RtnCode", "in": "query"}],
            responses=[{"status": "200", "description": "1|OK"}],
        ),
    ])
    doc = build_openapi(plan)
    assert doc["paths"] == {}
    assert "付款結果通知" in doc["webhooks"]
    op = doc["webhooks"]["付款結果通知"]["post"]
    assert {p["name"] for p in op["parameters"]} == {"RtnCode"}
    assert "200" in op["responses"]


def test_paths_and_webhooks_coexist():
    plan = _plan(endpoints=[
        EndpointEntry(status=PlanItemStatus.SUPPORTED, method="POST", path="/q",
                      summary="query", responses=[{"status": "200"}]),
        EndpointEntry(status=PlanItemStatus.SUPPORTED, method="POST", path=None,
                      summary="notify", responses=[{"status": "200"}]),
    ])
    doc = build_openapi(plan)
    assert "/q" in doc["paths"]
    assert "notify" in doc.get("webhooks", {})


def test_duplicate_path_method_operations_are_merged():
    # Two source endpoints can share one method+path (e.g. ECPay's 全方位金流
    # and ATM both POST /Cashier/AioCheckOut/V5, distinguished by a parameter).
    # OpenAPI allows only one operation per path+method, so they must be MERGED
    # (params/responses unioned) rather than the second silently overwriting the
    # first and wiping its content.
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/checkout",
            summary="all-in-one",
            parameters=[{"name": "A", "in": "query"}],
            responses=[],  # this product documents no synchronous response
        ),
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/checkout",
            summary="atm",
            parameters=[{"name": "B", "in": "query"}],
            responses=[{"status": "200", "description": "ok"}],
        ),
    ])
    ops = build_openapi(plan)["paths"]["/checkout"]
    assert set(ops.keys()) == {"post"}
    op = ops["post"]
    assert {p["name"] for p in op["parameters"]} == {"A", "B"}
    # the real response from the second endpoint must survive the merge
    assert "200" in op["responses"]
    # both summaries preserved
    assert "all-in-one" in op["summary"] and "atm" in op["summary"]


def test_non_ascii_schema_name_preserved_as_title():
    # A purely CJK name can't form a valid OpenAPI component key, so the key
    # falls back to schema<idx>; the human-readable name must survive in `title`
    # rather than vanishing from the spec.
    plan = _plan(schemas=[
        SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="旅遊地區代號對照表",
            fields=[], enums=["001=台北市"],
        )
    ])
    schemas = build_openapi(plan)["components"]["schemas"]
    assert "schema0" in schemas
    assert schemas["schema0"]["title"] == "旅遊地區代號對照表"


def test_sanitized_schema_name_preserved_as_title():
    # Slashes/spaces get rewritten in the key; keep the original via title.
    plan = _plan(schemas=[
        SchemaEntry(
            status=PlanItemStatus.SUPPORTED,
            name="TradeStatus / CloseStatus",
            fields=[{"name": "x", "type": "string"}],
        )
    ])
    schemas = build_openapi(plan)["components"]["schemas"]
    assert schemas["TradeStatus_CloseStatus"]["title"] == "TradeStatus / CloseStatus"


def test_ascii_schema_name_has_no_redundant_title():
    plan = _plan(schemas=[
        SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="User",
            fields=[{"name": "id", "type": "string"}],
        )
    ])
    user = build_openapi(plan)["components"]["schemas"]["User"]
    assert "title" not in user


def test_schema_without_name_skipped():
    plan = _plan(schemas=[SchemaEntry(status=PlanItemStatus.MISSING)])
    doc = build_openapi(plan)
    assert "schemas" not in doc.get("components", {})


def test_build_openapi_does_not_mutate_plan_schema_dicts():
    """build_openapi must not mutate the caller's schema field dicts (Fix 1+2)."""
    id_schema = {"type": "string"}
    role_field = {"name": "role", "schema": {"type": "string"}, "enum": ["admin", "user"]}
    plan = _plan(schemas=[
        SchemaEntry(
            status=PlanItemStatus.SUPPORTED,
            name="User",
            fields=[
                {"name": "id", "schema": id_schema, "description": "the id"},
                role_field,
            ],
        )
    ])
    plan_before = plan.model_copy(deep=True)

    result = build_openapi(plan)

    # The plan must not have been mutated
    assert plan == plan_before

    # The returned schema fragment for the "id" field must be a distinct object
    result_id_prop = result["components"]["schemas"]["User"]["properties"]["id"]
    assert result_id_prop is not id_schema


def test_responses_fold_business_status_into_single_200():
    from loop_apidoc.generate.openapi import _build_responses
    out = _build_responses([
        {"status": "SUCCESS", "description": "ok"},
        {"status": "錯誤代碼 (參考 5.)", "description": "fail"},
    ])
    assert set(out) == {"200"}
    assert "SUCCESS" in out["200"]["description"]
    assert "錯誤代碼" in out["200"]["description"]


def test_responses_keep_valid_codes_and_fold_business_status():
    from loop_apidoc.generate.openapi import _build_responses
    out = _build_responses([
        {"status": "201", "description": "created"},
        {"status": "SUCCESS", "description": "ok"},
    ])
    assert "201" in out          # valid HTTP code kept
    assert "200" in out          # business status folded under 200


def test_body_params_become_request_body_not_parameters():
    # OpenAPI 3.x abolished `in: body`. Source fields tagged `in: "body"` are
    # form/JSON body fields and MUST populate requestBody's object schema —
    # never be emitted as (and silently coerced to) query parameters.
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
            parameters=[
                {"name": "MerchantID", "in": "body", "type": "String(15)",
                 "required": True, "description": "商店代號"},
                {"name": "Amt", "in": "body", "type": "Int(10)", "required": True},
                {"name": "LangType", "in": "body", "type": "String(5)"},
            ],
            responses=[{"status": "200", "description": "ok"}],
        )
    ])
    op = build_openapi(plan)["paths"]["/pay"]["post"]
    assert "parameters" not in op  # nothing leaks into query params
    body = op["requestBody"]
    assert body["required"] is True  # a body with required fields is required
    schema = body["content"]["application/json"]["schema"]
    assert schema["type"] == "object"
    # field description wins over the raw type hint (mirrors _build_object_schema)
    assert schema["properties"]["MerchantID"] == {"type": "string", "description": "商店代號"}
    # no field description -> raw type kept as description
    assert schema["properties"]["Amt"] == {"type": "integer", "description": "Int(10)"}
    assert schema["properties"]["LangType"] == {"type": "string", "description": "String(5)"}
    assert schema["required"] == ["MerchantID", "Amt"]


def test_mixed_body_and_path_query_params_split_correctly():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/users/{id}/pay",
            parameters=[
                {"name": "id", "in": "path", "type": "string"},
                {"name": "token", "in": "query", "type": "string"},
                {"name": "Amt", "in": "body", "type": "integer", "required": True},
            ],
            responses=[{"status": "200", "description": "ok"}],
        )
    ])
    op = build_openapi(plan)["paths"]["/users/{id}/pay"]["post"]
    assert {p["name"] for p in op["parameters"]} == {"id", "token"}
    props = op["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert set(props) == {"Amt"}


def test_body_params_with_request_prose_preserved():
    # When both `in:body` fields AND a prose `request` blob exist, the structured
    # fields drive properties; the prose schema/description text is preserved
    # (non-speculative) rather than discarded.
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
            parameters=[{"name": "Foo", "in": "body", "type": "string"}],
            request={
                "content_type": "application/x-www-form-urlencoded",
                "schema": "以 HTML Form Post 提交",
                "required": True,
                "description": "submit form",
            },
            responses=[{"status": "200", "description": "ok"}],
        )
    ])
    body = build_openapi(plan)["paths"]["/pay"]["post"]["requestBody"]
    assert body["required"] is True
    assert body["description"] == "submit form"
    schema = body["content"]["application/x-www-form-urlencoded"]["schema"]
    assert "Foo" in schema["properties"]
    assert schema["description"] == "以 HTML Form Post 提交"


def test_body_params_unioned_across_merged_operations():
    # Two source endpoints sharing one method+path: their body fields union into
    # one requestBody (first occurrence wins on name collision), mirroring how
    # query parameters are merged.
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/checkout",
            parameters=[{"name": "A", "in": "body", "type": "string"}],
            responses=[],
        ),
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/checkout",
            parameters=[{"name": "B", "in": "body", "type": "string"}],
            responses=[{"status": "200", "description": "ok"}],
        ),
    ])
    op = build_openapi(plan)["paths"]["/checkout"]["post"]
    props = op["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert set(props) == {"A", "B"}


def test_bracket_named_body_fields_nest_into_array_items():
    # The source documents OrderDetail as a JSON array of objects; the extraction
    # encodes that via the `Parent[].Child` naming convention. The generator must
    # reconstruct array `items` rather than emit flat bracket-named properties.
    plan = _plan(endpoints=[EndpointEntry(
        status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
        parameters=[
            {"name": "MerchantID", "in": "body", "type": "string", "required": True},
            {"name": "OrderDetail", "in": "body", "type": "array", "description": "訂單細項"},
            {"name": "OrderDetail[].ItemName", "in": "body", "type": "String(20)",
             "required": True, "description": "品名"},
            {"name": "OrderDetail[].ItemAmt", "in": "body", "type": "Int(10)", "required": True},
        ],
        responses=[{"status": "200", "description": "ok"}],
    )])
    schema = (build_openapi(plan)["paths"]["/pay"]["post"]["requestBody"]
              ["content"]["application/json"]["schema"])
    assert "OrderDetail[].ItemName" not in schema["properties"]  # no flat leak
    od = schema["properties"]["OrderDetail"]
    assert od["type"] == "array"
    assert od["description"] == "訂單細項"
    items = od["items"]
    assert items["type"] == "object"
    assert items["properties"]["ItemName"]["type"] == "string"
    assert items["properties"]["ItemAmt"]["type"] == "integer"
    assert items["required"] == ["ItemName", "ItemAmt"]
    # the array itself is optional at top level (its standalone field set no required)
    assert schema["required"] == ["MerchantID"]


def test_dotted_body_fields_nest_into_object():
    plan = _plan(endpoints=[EndpointEntry(
        status=PlanItemStatus.SUPPORTED, method="POST", path="/x",
        parameters=[
            {"name": "Payer.Name", "in": "body", "type": "string", "required": True},
            {"name": "Payer.Email", "in": "body", "type": "string"},
        ],
        responses=[{"status": "200", "description": "ok"}],
    )])
    schema = (build_openapi(plan)["paths"]["/x"]["post"]["requestBody"]
              ["content"]["application/json"]["schema"])
    payer = schema["properties"]["Payer"]
    assert payer["type"] == "object"
    assert set(payer["properties"]) == {"Name", "Email"}
    assert payer["required"] == ["Name"]


def test_object_schema_fields_nest_too():
    plan = _plan(schemas=[SchemaEntry(
        status=PlanItemStatus.SUPPORTED, name="Order",
        fields=[
            {"name": "Items[].Sku", "type": "string", "required": True},
            {"name": "Items[].Qty", "type": "integer"},
        ],
    )])
    order = build_openapi(plan)["components"]["schemas"]["Order"]
    assert "Items[].Sku" not in order["properties"]
    items = order["properties"]["Items"]
    assert items["type"] == "array"
    assert items["items"]["properties"]["Sku"]["type"] == "string"
    assert items["items"]["required"] == ["Sku"]


def test_operation_id_from_summary_code():
    # The doc's own operation code ("[NPA-F01]") is a source-stated identifier —
    # use it as operationId so codegen produces meaningful method names.
    plan = _plan(endpoints=[EndpointEntry(
        status=PlanItemStatus.SUPPORTED, method="POST", path="/MPG/mpg_gateway",
        summary="MPG 交易 [NPA-F01]：商店向藍新金流發動交易",
        responses=[{"status": "200", "description": "ok"}],
    )])
    op = build_openapi(plan)["paths"]["/MPG/mpg_gateway"]["post"]
    assert op["operationId"] == "NPA_F01"


def test_operation_id_fallback_from_method_path():
    plan = _plan(endpoints=[EndpointEntry(
        status=PlanItemStatus.SUPPORTED, method="GET", path="/users/{id}",
        responses=[{"status": "200", "description": "ok"}],
    )])
    op = build_openapi(plan)["paths"]["/users/{id}"]["get"]
    assert op["operationId"] == "get_users_id"


def test_operation_ids_are_unique():
    plan = _plan(endpoints=[
        EndpointEntry(status=PlanItemStatus.SUPPORTED, method="POST", path="/a",
                      summary="x [DUP]", responses=[{"status": "200"}]),
        EndpointEntry(status=PlanItemStatus.SUPPORTED, method="POST", path="/b",
                      summary="y [DUP]", responses=[{"status": "200"}]),
    ])
    doc = build_openapi(plan)
    ids = {doc["paths"]["/a"]["post"]["operationId"],
           doc["paths"]["/b"]["post"]["operationId"]}
    assert ids == {"DUP", "DUP_2"}


def test_endpoint_tags_rendered_and_collected_at_root():
    plan = _plan(endpoints=[
        EndpointEntry(status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
                      tags=["Payment"], responses=[{"status": "200"}]),
        EndpointEntry(status=PlanItemStatus.SUPPORTED, method="POST", path="/refund",
                      tags=["Payment", "Refund"], responses=[{"status": "200"}]),
    ])
    doc = build_openapi(plan)
    assert doc["paths"]["/pay"]["post"]["tags"] == ["Payment"]
    # root tag declarations are unique and source-ordered
    assert [t["name"] for t in doc["tags"]] == ["Payment", "Refund"]


def test_merged_operation_unions_tags():
    plan = _plan(endpoints=[
        EndpointEntry(status=PlanItemStatus.SUPPORTED, method="POST", path="/c",
                      tags=["A"], responses=[]),
        EndpointEntry(status=PlanItemStatus.SUPPORTED, method="POST", path="/c",
                      tags=["A", "B"], responses=[{"status": "200"}]),
    ])
    assert build_openapi(plan)["paths"]["/c"]["post"]["tags"] == ["A", "B"]


def test_endpoint_security_references_scheme_by_name():
    plan = _plan(
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="AES256 (TradeInfo)",
            type="apiKey", location="header", details="X")],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
            security=["AES256 (TradeInfo)"], responses=[{"status": "200"}])],
    )
    doc = build_openapi(plan)
    key = next(iter(doc["components"]["securitySchemes"]))  # sanitized key
    assert doc["paths"]["/pay"]["post"]["security"] == [{key: []}]


def test_unresolvable_security_name_is_dropped():
    plan = _plan(endpoints=[EndpointEntry(
        status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
        security=["NopeScheme"], responses=[{"status": "200"}])])
    assert "security" not in build_openapi(plan)["paths"]["/pay"]["post"]


def test_response_schema_ref_resolves_to_component_ref():
    # The structured response body lives in components.schemas; a response that
    # names it (schema_ref) must link via $ref rather than restating prose.
    plan = _plan(
        schemas=[SchemaEntry(status=PlanItemStatus.SUPPORTED, name="PayResult",
                             fields=[{"name": "Status", "type": "string"}])],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
            responses=[{"status": "200", "description": "ok", "schema_ref": "PayResult"}],
        )],
    )
    resp = build_openapi(plan)["paths"]["/pay"]["post"]["responses"]["200"]
    assert resp["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PayResult"
    }


def test_business_status_response_ref_folds_into_200_with_content():
    # Business-status responses fold under 200 — but their $ref content must
    # survive the fold (previously the schema was dropped entirely).
    plan = _plan(
        schemas=[SchemaEntry(status=PlanItemStatus.SUPPORTED, name="PayResult",
                             fields=[{"name": "Status", "type": "string"}])],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
            responses=[{"status": "SUCCESS", "description": "paid", "schema_ref": "PayResult"}],
        )],
    )
    resp = build_openapi(plan)["paths"]["/pay"]["post"]["responses"]["200"]
    assert "SUCCESS" in resp["description"]
    assert resp["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PayResult"
    }


def test_two_business_responses_fold_into_oneof():
    plan = _plan(
        schemas=[
            SchemaEntry(status=PlanItemStatus.SUPPORTED, name="PayDone",
                        fields=[{"name": "a", "type": "string"}]),
            SchemaEntry(status=PlanItemStatus.SUPPORTED, name="NumDone",
                        fields=[{"name": "b", "type": "string"}]),
        ],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
            responses=[
                {"status": "支付完成", "description": "d1", "schema_ref": "PayDone"},
                {"status": "取號完成", "description": "d2", "schema_ref": "NumDone"},
            ],
        )],
    )
    schema = (build_openapi(plan)["paths"]["/pay"]["post"]["responses"]["200"]
              ["content"]["application/json"]["schema"])
    assert {x["$ref"] for x in schema["oneOf"]} == {
        "#/components/schemas/PayDone", "#/components/schemas/NumDone"
    }


def test_unresolvable_schema_ref_is_ignored_not_fabricated():
    plan = _plan(endpoints=[EndpointEntry(
        status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
        responses=[{"status": "200", "description": "ok", "schema_ref": "NopeMissing"}],
    )])
    resp = build_openapi(plan)["paths"]["/pay"]["post"]["responses"]["200"]
    assert "content" not in resp  # never invent a dangling $ref
    assert resp["description"] == "ok"


def test_colliding_schema_names_get_distinct_keys_and_refs_resolve():
    # Two CJK names both sanitize to "Result"; without dedup one overwrites the
    # other (and breaks provenance alignment). Distinct keys must be kept, and a
    # schema_ref must resolve to the RIGHT one.
    plan = _plan(
        schemas=[
            SchemaEntry(status=PlanItemStatus.SUPPORTED,
                        name="取消授權回應參數（Result）",
                        fields=[{"name": "a", "type": "string"}]),
            SchemaEntry(status=PlanItemStatus.SUPPORTED,
                        name="請退款回應參數（Result）",
                        fields=[{"name": "b", "type": "string"}]),
        ],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/r",
            responses=[{"status": "200", "description": "ok",
                        "schema_ref": "請退款回應參數（Result）"}],
        )],
    )
    doc = build_openapi(plan)
    assert len(doc["components"]["schemas"]) == 2  # no silent overwrite
    ref = (doc["paths"]["/r"]["post"]["responses"]["200"]
           ["content"]["application/json"]["schema"]["$ref"])
    target = ref.rsplit("/", 1)[-1]
    # must point at the 2nd schema (請退款), whose field is "b"
    assert "b" in doc["components"]["schemas"][target]["properties"]


def test_normalize_media_type_strips_annotation_suffix():
    from loop_apidoc.generate.openapi import _normalize_media_type
    # The source often appends a human note in parentheses; the media-type key
    # must stay valid `type/subtype` (codegen tools reject the noisy form).
    assert (_normalize_media_type("application/x-www-form-urlencoded (HTML Form Post)")
            == "application/x-www-form-urlencoded")
    assert _normalize_media_type("application/json") == "application/json"
    assert _normalize_media_type("multipart/form-data; boundary=x") == "multipart/form-data"


def test_normalize_media_type_falls_back_to_json_when_unparseable():
    from loop_apidoc.generate.openapi import _normalize_media_type
    assert _normalize_media_type("form post") == "application/json"
    assert _normalize_media_type(None) == "application/json"
    assert _normalize_media_type("") == "application/json"


def test_request_body_content_key_is_valid_media_type():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
            parameters=[{"name": "Foo", "in": "body", "type": "string"}],
            request={"content_type": "application/x-www-form-urlencoded (HTML Form Post)"},
            responses=[{"status": "200", "description": "ok"}],
        )
    ])
    content = build_openapi(plan)["paths"]["/pay"]["post"]["requestBody"]["content"]
    assert "application/x-www-form-urlencoded" in content
    assert "application/x-www-form-urlencoded (HTML Form Post)" not in content


def test_response_content_key_is_valid_media_type():
    plan = _plan(endpoints=[
        EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/x",
            responses=[{"status": "200", "description": "ok",
                        "content_type": "application/json (UTF-8)",
                        "schema": {"type": "object"}}],
        )
    ])
    resp = build_openapi(plan)["paths"]["/x"]["get"]["responses"]["200"]
    assert list(resp["content"]) == ["application/json"]


def test_parameter_type_normalized_to_valid_schema():
    from loop_apidoc.generate.openapi import _build_parameter
    p = _build_parameter({"name": "TradeInfo", "in": "query", "required": True,
                          "type": "String(15)", "description": "AES"})
    # "String(15)" -> valid type "string", raw kept as schema description
    assert p["schema"]["type"] == "string"
    assert p["schema"]["description"] == "String(15)"
    assert p["name"] == "TradeInfo" and p["in"] == "query"


def test_unknown_param_type_keeps_raw_as_description_only():
    from loop_apidoc.generate.openapi import _schema_from_type
    assert _schema_from_type("WeirdType") == {"description": "WeirdType"}
    assert "type" not in _schema_from_type("WeirdType")


def test_security_scheme_http_bearer_emits_scheme():
    # OpenAPI `http` type requires a `scheme`; derive bearer/basic from details
    # so a Bearer-auth source (e.g. Stripe) yields valid OpenAPI, not type:http
    # missing the required `scheme` property.
    plan = _plan(security_schemes=[
        SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="bearerAuth",
            type="http", location="header",
            details="HTTP Bearer authentication: Authorization: Bearer <secret API key>.",
        )
    ])
    scheme = build_openapi(plan)["components"]["securitySchemes"]["bearerAuth"]
    assert scheme["type"] == "http"
    assert scheme["scheme"] == "bearer"


def test_security_scheme_http_basic_emits_scheme():
    plan = _plan(security_schemes=[
        SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="basicAuth",
            type="http", location="header",
            details="HTTP Basic authentication: the secret API key as the username.",
        )
    ])
    scheme = build_openapi(plan)["components"]["securitySchemes"]["basicAuth"]
    assert scheme["type"] == "http"
    assert scheme["scheme"] == "basic"


def test_security_scheme_http_without_derivable_scheme_falls_back_to_placeholder():
    # http with no bearer/basic hint cannot be a valid http scheme → placeholder
    plan = _plan(security_schemes=[
        SecuritySchemeEntry(
            status=PlanItemStatus.UNVERIFIED, name="MysteryHttp",
            type="http", location="header", details="some custom token",
        )
    ])
    scheme = build_openapi(plan)["components"]["securitySchemes"]["MysteryHttp"]
    assert scheme["type"] == "apiKey"
    assert scheme[X_LOOP_STATUS] == MISSING_STATUS
