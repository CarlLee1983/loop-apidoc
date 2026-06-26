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
