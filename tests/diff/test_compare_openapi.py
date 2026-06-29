from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.diff.compare import build_diff_report
from loop_apidoc.diff.loader import RunArtifacts
from loop_apidoc.diff.models import DiffImpact
from loop_apidoc.generate.models import ProvenanceDocument
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.validate.models import ValidationReport

_NOW = datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc)


def _doc() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Demo API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/payments": {
                "post": {
                    "summary": "Create payment",
                    "parameters": [
                        {
                            "name": "merchant_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["amount"],
                                    "properties": {
                                        "amount": {"type": "integer"},
                                        "note": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"id": {"type": "string"}},
                                    }
                                }
                            },
                        },
                        "400": {"description": "bad request"},
                    },
                    "security": [{"ApiKeyAuth": []}],
                }
            }
        },
        "components": {
            "schemas": {
                "Payment": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string"}},
                }
            },
            "securitySchemes": {
                "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
            },
        },
    }


def _artifacts(openapi: dict, name: str = "run") -> RunArtifacts:
    return RunArtifacts(
        run_dir=Path(name),
        openapi=openapi,
        integration=None,
        provenance=ProvenanceDocument(notebook_url="", entries=[]),
        validation=ValidationReport(),
        manifest=Manifest(sources_root="./sources", generated_at=_NOW),
    )


def _findings(base: dict, head: dict):
    return build_diff_report(_artifacts(base, "base"), _artifacts(head, "head")).findings


def _by_summary(base: dict, head: dict, text: str):
    return [f for f in _findings(base, head) if text in f.summary]


def test_endpoint_addition_is_additive():
    base = _doc()
    head = _doc()
    head["paths"]["/refunds"] = {"post": {"responses": {"200": {"description": "ok"}}}}

    finding = _by_summary(base, head, "operation added")[0]
    assert finding.impact is DiffImpact.ADDITIVE
    assert finding.location == "POST /refunds"


def test_endpoint_removal_is_breaking():
    base = _doc()
    head = _doc()
    del head["paths"]["/payments"]

    finding = _by_summary(base, head, "operation removed")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "POST /payments"


def test_required_parameter_addition_is_breaking():
    base = _doc()
    head = _doc()
    head["paths"]["/payments"]["post"]["parameters"].append(
        {
            "name": "signature",
            "in": "header",
            "required": True,
            "schema": {"type": "string"},
        }
    )

    finding = _by_summary(base, head, "required parameter added")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "POST /payments parameters.header.signature"


def test_optional_parameter_addition_is_additive():
    base = _doc()
    head = _doc()
    head["paths"]["/payments"]["post"]["parameters"].append(
        {"name": "locale", "in": "query", "schema": {"type": "string"}}
    )

    finding = _by_summary(base, head, "optional parameter added")[0]
    assert finding.impact is DiffImpact.ADDITIVE
    assert finding.location == "POST /payments parameters.query.locale"


def test_parameter_type_change_is_breaking():
    base = _doc()
    head = _doc()
    head["paths"]["/payments"]["post"]["parameters"][0]["schema"] = {"type": "integer"}

    finding = _by_summary(base, head, "parameter schema changed")[0]
    assert finding.impact is DiffImpact.BREAKING


def test_required_request_property_addition_is_breaking():
    base = _doc()
    head = _doc()
    schema = head["paths"]["/payments"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    schema["required"].append("currency")
    schema["properties"]["currency"] = {"type": "string"}

    finding = _by_summary(base, head, "required property added")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "POST /payments requestBody.application/json.currency"


def test_optional_request_property_addition_is_additive():
    base = _doc()
    head = _doc()
    schema = head["paths"]["/payments"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    schema["properties"]["channel"] = {"type": "string"}

    finding = _by_summary(base, head, "optional property added")[0]
    assert finding.impact is DiffImpact.ADDITIVE


def test_response_status_removal_is_breaking():
    base = _doc()
    head = _doc()
    del head["paths"]["/payments"]["post"]["responses"]["400"]

    finding = _by_summary(base, head, "response removed")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "POST /payments responses.400"


def test_response_status_addition_is_additive():
    base = _doc()
    head = _doc()
    head["paths"]["/payments"]["post"]["responses"]["409"] = {"description": "conflict"}

    finding = _by_summary(base, head, "response added")[0]
    assert finding.impact is DiffImpact.ADDITIVE


def test_response_schema_type_change_is_breaking():
    base = _doc()
    head = _doc()
    head_schema = head["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    head_schema["properties"]["id"] = {"type": "integer"}

    finding = _by_summary(base, head, "schema changed")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert "responses.200.application/json.id" in finding.location


def test_info_and_server_changes_are_changed():
    base = _doc()
    head = _doc()
    head["info"]["version"] = "1.1.0"
    head["servers"] = [{"url": "https://sandbox.example.com"}]

    findings = _findings(base, head)
    changed = [f for f in findings if f.impact is DiffImpact.CHANGED]
    assert any(f.location == "openapi.info.version" for f in changed)
    assert any(f.location == "openapi.servers" for f in changed)


def test_security_scheme_change_is_breaking():
    base = _doc()
    head = _doc()
    head["components"]["securitySchemes"]["ApiKeyAuth"]["name"] = "Authorization"

    finding = _by_summary(base, head, "security scheme changed")[0]
    assert finding.impact is DiffImpact.BREAKING


def test_summary_counts_all_impacts():
    base = _doc()
    head = _doc()
    head["info"]["version"] = "1.1.0"
    head["paths"]["/refunds"] = {"post": {"responses": {"200": {"description": "ok"}}}}
    del head["paths"]["/payments"]["post"]["responses"]["400"]

    report = build_diff_report(_artifacts(base, "base"), _artifacts(head, "head"))

    assert report.summary["breaking"] == 1
    assert report.summary["additive"] == 1
    assert report.summary["changed"] == 1
    assert report.summary["source_only"] == 0
