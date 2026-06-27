from loop_apidoc.generate.examples import (
    _placeholder,
    _resolve_value,
    _request_shape,
    _request_signing_schemes,
    _signature_explicit,
)
from loop_apidoc.plan.models import CryptoScheme, IntegrationContract, NormalizationPlan


def test_placeholder_is_snake_angle_bracketed():
    assert _placeholder("MerchantID") == "<merchant_id>"
    assert _placeholder("Amt") == "<amt>"


def test_resolve_value_prefers_source_example():
    assert _resolve_value("Version", {"example": "2.0"}) == ("source", "2.0")


def test_resolve_value_single_enum_is_source():
    node = {"schema": {"enum": ["S"]}}
    assert _resolve_value("Action", node) == ("source", "S")


def test_resolve_value_missing_falls_to_placeholder_not_type_sample():
    kind, value = _resolve_value("Amount", {"schema": {"type": "integer"}})
    assert kind == "placeholder"
    assert value == "<amount>"
    # 不臆測回歸鎖：絕不依型別塞樣本
    assert value not in (0, "string", "0", True)


def test_request_shape_uses_server_url_and_partitions_fields():
    op = {
        "operationId": "PayOrder",
        "parameters": [
            {"name": "MerchantID", "in": "query", "schema": {"type": "string"}},
            {"name": "Version", "in": "query", "example": "2.0"},
        ],
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"type": "object", "properties": {"Amount": {"type": "integer"}}}
                }
            }
        },
        "security": [{"NewebpayAuth": []}],
    }
    shape = _request_shape(op, [{"url": "https://api.example.com"}], "/pay", "POST")
    assert shape["method"] == "POST"
    assert shape["url"] == "https://api.example.com/pay"
    assert ("Version", "source", "2.0") in shape["query"]
    assert ("MerchantID", "placeholder", "<merchant_id>") in shape["query"]
    assert ("Amount", "placeholder", "<amount>") in shape["body"]
    assert shape["content_type"] == "application/json"
    assert shape["security"] == ["NewebpayAuth"]


def test_request_shape_webhook_url_placeholder():
    shape = _request_shape({"operationId": "Notify"}, [], None)
    assert shape["url"] == "<your_receiver_url>"


def test_request_shape_missing_server_url_placeholder():
    shape = _request_shape({"operationId": "X"}, [], "/p")
    assert shape["url"] == "<base_url>/p"


def test_signature_explicit_requires_algorithm_and_steps():
    full = CryptoScheme(
        status="supported", name="sig", algorithm="AES-256-CBC", mode="CBC",
        payload_assembly=[{"step": 1, "desc": "join", "fields": ["A", "B"]}],
    )
    assert _signature_explicit(full) is True
    partial = CryptoScheme(status="supported", name="sig", algorithm="AES-256-CBC")
    assert _signature_explicit(partial) is False


def test_request_signing_schemes_filters_callback_only():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            crypto=[
                CryptoScheme(status="supported", name="req", purpose="request"),
                CryptoScheme(status="supported", name="cb", purpose="callback"),
                CryptoScheme(status="supported", name="any", purpose=None),
            ]
        ),
    )
    names = [s.name for s in _request_signing_schemes(plan)]
    assert names == ["req", "any"]
