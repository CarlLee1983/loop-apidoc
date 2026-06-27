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
    assert scheme["description"] == "hmac-signature"


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
