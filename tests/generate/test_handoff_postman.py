from __future__ import annotations

import json

from loop_apidoc.generate.handoff import build_handoff
from loop_apidoc.plan.models import NormalizationPlan


def _plan() -> NormalizationPlan:
    return NormalizationPlan(notebook_url="n/a")


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Pay API", "version": "1.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/payments": {
                "post": {
                    "operationId": "createPayment",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {
                                        "amount": {"type": "integer"},
                                        "currency": {"type": "string", "enum": ["TWD"]},
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
    }


def _collection() -> dict:
    out = build_handoff(_openapi(), _plan(), None)
    return json.loads(out["handoff/postman_collection.json"])


def test_postman_v21_top_level_shape():
    c = _collection()
    assert c["info"]["name"] == "Pay API"
    assert c["info"]["schema"] == (
        "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    )
    assert isinstance(c["item"], list)
    base = next(v for v in c["variable"] if v["key"] == "base_url")
    assert base["value"] == "https://api.example.com"


def test_postman_url_uses_base_url_variable():
    c = _collection()
    item = c["item"][0]
    assert "{{base_url}}" in item["request"]["url"]["raw"]


def test_postman_description_has_openapi_pointer():
    c = _collection()
    item = c["item"][0]
    assert "../openapi.yaml#/paths/~1payments/post" in item["description"]


def test_postman_missing_values_are_placeholders_not_samples():
    c = _collection()
    body_raw = c["item"][0]["request"]["body"]["raw"]
    parsed = json.loads(body_raw)
    assert parsed["amount"] == "<amount>"        # no guessed integer 0
    assert parsed["currency"] == "TWD"           # single-enum is source-stated
    assert "string" not in body_raw              # no fabricated "string" sample
    assert ": 0" not in body_raw and "true" not in body_raw


def test_postman_no_prerequest_script():
    c = _collection()
    assert "event" not in c["item"][0]


def test_postman_title_fallback_when_missing():
    op = _openapi()
    op["info"] = {}
    out = build_handoff(op, _plan(), None)
    c = json.loads(out["handoff/postman_collection.json"])
    assert c["info"]["name"] == "Untitled API"


def _form_openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Form API", "version": "1.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/pay": {
                "post": {
                    "operationId": "submitPayment",
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "properties": {
                                        "MerchantID": {"type": "string"},
                                        "TradeAmt": {"type": "integer"},
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
    }


def test_postman_form_encoded_body():
    out = build_handoff(_form_openapi(), _plan(), None)
    c = json.loads(out["handoff/postman_collection.json"])
    item = c["item"][0]
    body = item["request"]["body"]
    # form-encoded → urlencoded mode, not raw
    assert body["mode"] == "urlencoded"
    assert "urlencoded" in body
    keys = {entry["key"] for entry in body["urlencoded"]}
    assert "MerchantID" in keys
    assert "TradeAmt" in keys
    # values must be placeholders (no source example given)
    values = {entry["key"]: entry["value"] for entry in body["urlencoded"]}
    assert values["MerchantID"] == "<merchant_id>"
    assert values["TradeAmt"] == "<trade_amt>"
    # Content-Type header must be set
    headers = {h["key"]: h["value"] for h in item["request"]["header"]}
    assert headers.get("Content-Type") == "application/x-www-form-urlencoded"
