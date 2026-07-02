from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loop_apidoc.diff.compare import build_diff_report, _looks_like_object
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

    findings = _findings(base, head)
    hits = [
        f for f in findings
        if f.location == "POST /payments responses.200.application/json.id"
        and f.summary == "schema changed"
    ]
    assert len(hits) == 1
    assert hits[0].impact is DiffImpact.BREAKING


def test_object_to_scalar_schema_change_reports_only_schema_change():
    base = _doc()
    head = _doc()
    head["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "string"
    }

    findings = _findings(base, head)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.summary == "schema changed"
    assert finding.location == "POST /payments responses.200.application/json"
    assert finding.impact is DiffImpact.BREAKING
    assert not any(
        f.summary == "property removed"
        and f.location.startswith("POST /payments responses.200.application/json.")
        for f in findings
    )


def test_implicit_object_to_scalar_schema_change_reports_only_parent_change():
    base = _doc()
    head = _doc()
    base["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "properties": {"id": {"type": "string"}}
    }
    head["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "string"
    }

    findings = _findings(base, head)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.summary == "schema changed"
    assert finding.location == "POST /payments responses.200.application/json"
    assert finding.impact is DiffImpact.BREAKING
    assert not any(
        f.summary == "property removed"
        and f.location.startswith("POST /payments responses.200.application/json.")
        for f in findings
    )


def test_explicit_scalar_with_properties_to_object_reports_only_parent_change():
    base = _doc()
    head = _doc()
    base["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "string",
        "properties": {"bogus": {"type": "string"}},
    }
    head["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "object",
        "properties": {"actual": {"type": "integer"}},
    }

    findings = _findings(base, head)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.summary == "schema changed"
    assert finding.location == "POST /payments responses.200.application/json"
    assert finding.impact is DiffImpact.BREAKING
    assert not any(
        f.location.startswith("POST /payments responses.200.application/json.")
        for f in findings
    )


def test_explicit_to_implicit_object_schema_change_still_reports_nested_diff():
    base = _doc()
    head = _doc()
    base["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "object",
        "properties": {"id": {"type": "string"}},
    }
    head["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "properties": {"id": {"type": "integer"}}
    }

    findings = _findings(base, head)

    assert any(
        f.summary == "schema changed"
        and f.location == "POST /payments responses.200.application/json.id"
        and f.impact is DiffImpact.BREAKING
        for f in findings
    )


def test_explicit_and_implicit_object_schemas_with_identical_properties_do_not_change():
    base = _doc()
    head = _doc()
    base["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "object",
        "properties": {"id": {"type": "string"}},
    }
    head["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "properties": {"id": {"type": "string"}}
    }

    location = "POST /payments responses.200.application/json"
    findings = [
        f
        for f in _findings(base, head)
        if f.location == location or f.location.startswith(f"{location}.")
    ]

    assert findings == []


def test_implicit_and_explicit_object_schemas_with_identical_properties_do_not_change():
    base = _doc()
    head = _doc()
    base["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "properties": {"id": {"type": "string"}}
    }
    head["paths"]["/payments"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "object",
        "properties": {"id": {"type": "string"}},
    }

    location = "POST /payments responses.200.application/json"
    findings = [
        f
        for f in _findings(base, head)
        if f.location == location or f.location.startswith(f"{location}.")
    ]

    assert findings == []


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


def _doc_with_webhook() -> dict:
    doc = _doc()
    doc["webhooks"] = {
        "Notify": {
            "post": {
                "summary": "Payment notification",
                "responses": {"200": {"description": "ok"}},
            }
        }
    }
    return doc


def test_webhook_addition_is_additive():
    base = _doc()
    head = _doc_with_webhook()

    finding = _by_summary(base, head, "operation added")[0]
    assert finding.impact is DiffImpact.ADDITIVE
    assert finding.location == "POST webhooks:Notify"


def test_webhook_removal_is_breaking():
    base = _doc_with_webhook()
    head = _doc()

    finding = _by_summary(base, head, "operation removed")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "POST webhooks:Notify"


def test_webhook_response_removal_is_breaking():
    base = _doc_with_webhook()
    head = _doc_with_webhook()
    head["webhooks"]["Notify"]["post"]["responses"]["200"] = {"description": "changed"}
    del head["webhooks"]["Notify"]["post"]["responses"]["200"]
    head["webhooks"]["Notify"]["post"]["responses"]["201"] = {"description": "ok"}

    removed = _by_summary(base, head, "response removed")
    assert any(f.location == "POST webhooks:Notify responses.200" for f in removed)


def test_array_item_type_change_is_breaking():
    base = _doc()
    head = _doc()
    schema = base["paths"]["/payments"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    schema["properties"]["tags"] = {"type": "array", "items": {"type": "string"}}
    head_schema = head["paths"]["/payments"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    head_schema["properties"]["tags"] = {"type": "array", "items": {"type": "integer"}}

    findings = _by_summary(base, head, "schema changed")
    assert any("tags[]" in f.location and f.impact is DiffImpact.BREAKING for f in findings)


def test_request_body_becoming_required_is_breaking():
    base = _doc()
    head = _doc()
    base["paths"]["/payments"]["post"]["requestBody"]["required"] = False
    head["paths"]["/payments"]["post"]["requestBody"]["required"] = True

    finding = _by_summary(base, head, "request body became required")[0]
    assert finding.impact is DiffImpact.BREAKING
    assert finding.location == "POST /payments requestBody.required"


def test_request_body_no_longer_required_is_changed():
    base = _doc()
    head = _doc()
    base["paths"]["/payments"]["post"]["requestBody"]["required"] = True
    head["paths"]["/payments"]["post"]["requestBody"]["required"] = False

    finding = _by_summary(base, head, "request body no longer required")[0]
    assert finding.impact is DiffImpact.CHANGED


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


def test_object_typed_parameter_property_removal_is_reported():
    base = _doc()
    head = _doc()
    obj_param = {
        "name": "filter",
        "in": "query",
        "schema": {
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        },
    }
    base["paths"]["/payments"]["post"]["parameters"].append(obj_param)
    head_param = {
        "name": "filter",
        "in": "query",
        "schema": {"type": "object", "properties": {"a": {"type": "string"}}},
    }
    head["paths"]["/payments"]["post"]["parameters"].append(head_param)

    findings = _findings(base, head)
    removed = [
        f for f in findings
        if f.summary == "property removed"
        and f.location == "POST /payments parameters.query.filter.b"
    ]
    assert len(removed) == 1
    assert removed[0].impact is DiffImpact.CHANGED


def test_looks_like_object_predicate():
    assert _looks_like_object({"type": "object"}) is True
    assert _looks_like_object({"properties": {"a": {"type": "string"}}}) is True
    assert _looks_like_object({"type": "string", "properties": {"a": {}}}) is False
    assert _looks_like_object({"type": "string"}) is False
    assert _looks_like_object("nope") is False
    assert _looks_like_object({}) is False


def test_info_title_change_is_changed():
    base = _doc()
    head = _doc()
    head["info"]["title"] = "Renamed API"
    findings = _findings(base, head)
    hits = [f for f in findings if f.location == "openapi.info.title"]
    assert len(hits) == 1
    assert hits[0].impact is DiffImpact.CHANGED


def test_property_no_longer_required_is_changed():
    base = _doc()
    head = _doc()
    schema = head["paths"]["/payments"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    schema["required"] = []
    findings = _findings(base, head)
    hits = [f for f in findings if f.summary == "property no longer required"]
    assert len(hits) == 1
    assert hits[0].impact is DiffImpact.CHANGED


def test_removed_component_schema_is_changed():
    base = _doc()
    base.setdefault("components", {}).setdefault("schemas", {})["Money"] = {
        "type": "object"
    }
    head = _doc()
    findings = _findings(base, head)
    hits = [
        f for f in findings
        if f.location == "components.schemas.Money" and f.summary == "schema removed"
    ]
    assert len(hits) == 1
    assert hits[0].impact is DiffImpact.CHANGED
