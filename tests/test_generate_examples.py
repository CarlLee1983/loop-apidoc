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


def test_render_curl_has_header_note_url_and_signature_comment():
    from loop_apidoc.generate.examples import _render_curl
    from loop_apidoc.plan.models import CryptoScheme

    shape = {
        "method": "POST",
        "url": "https://api.example.com/pay",
        "query": [],
        "header": [],
        "path": [],
        "body": [("MerchantID", "placeholder", "<merchant_id>"), ("Version", "source", "2.0")],
        "content_type": "application/x-www-form-urlencoded",
        "security": [],
    }
    scheme = CryptoScheme(
        status="supported", name="CheckValue", algorithm="AES-256-CBC",
        payload_assembly=[{"step": 1, "desc": "排序欄位後組字串"}],
    )
    out = _render_curl(shape, [scheme])
    assert out.startswith("# Derived from openapi.yaml")
    assert "https://api.example.com/pay" in out
    assert "MerchantID=<merchant_id>" in out
    assert "Version=2.0" in out
    # curl 簽章一律註解步驟，且指向 script
    assert "# 簽章步驟" in out
    assert "request.py" in out


def test_render_curl_no_dangling_backslash_when_no_data():
    from loop_apidoc.generate.examples import _render_curl

    # GET request with no body and no query params
    shape = {
        "method": "GET",
        "url": "https://api.example.com/status",
        "query": [],
        "header": [("Authorization", "source", "Bearer token123")],
        "path": [],
        "body": [],
        "content_type": None,
        "security": [],
    }
    out = _render_curl(shape, [])
    curl_lines = out.split("\n")
    # Find non-empty lines in the curl command block
    curl_block = []
    for line in curl_lines:
        if line.startswith("curl") or line.startswith("  "):
            curl_block.append(line)
        elif line and not line.startswith("#"):
            break
    # The last line of curl block should NOT end with backslash
    if curl_block:
        last_line = curl_block[-1].rstrip()
        assert not last_line.endswith("\\"), f"Last curl line has dangling backslash: {last_line}"


def test_render_curl_no_signature_block_when_no_schemes():
    from loop_apidoc.generate.examples import _render_curl

    shape = {
        "method": "POST",
        "url": "https://api.example.com/pay",
        "query": [],
        "header": [],
        "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json",
        "security": [],
    }
    # Empty schemes list
    out = _render_curl(shape, [])
    # Signature comment should NOT appear
    assert "# 簽章步驟" not in out
    # But the curl command and data should still render
    assert "curl -X POST" in out
    assert "https://api.example.com/pay" in out
    assert "Amount=<amount>" in out


def test_render_ts_runnable_signature_when_explicit():
    from loop_apidoc.generate.examples import _render_ts
    from loop_apidoc.plan.models import CryptoScheme, KeySource

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json", "security": [],
    }
    explicit = CryptoScheme(
        status="supported", name="CheckValue", algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "組字串"}],
    )
    out = _render_ts(shape, [explicit])
    assert out.startswith("// Derived from openapi.yaml")
    assert "createCipheriv" in out  # 可跑簽章函式
    assert "amount" in out  # body 佔位變數


def test_render_ts_skeleton_with_gap_when_not_explicit():
    from loop_apidoc.generate.examples import _render_ts
    from loop_apidoc.plan.models import CryptoScheme

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [], "body": [],
        "content_type": "application/json", "security": [],
    }
    partial = CryptoScheme(status="supported", name="Sig", algorithm="AES-256-CBC")
    out = _render_ts(shape, [partial])
    assert "createCipheriv" not in out
    assert "// gap:" in out


def test_render_ts_multiple_explicit_schemes_valid():
    """Test that multiple explicit schemes produce valid TypeScript (no duplicate imports/declarations)."""
    from loop_apidoc.generate.examples import _render_ts, _ts_signature
    from loop_apidoc.plan.models import CryptoScheme, KeySource

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json", "security": [],
    }
    # Two explicit schemes (both with algorithm + payload_assembly)
    scheme1 = CryptoScheme(
        status="supported", name="CheckValue", algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "組字串"}],
    )
    scheme2 = CryptoScheme(
        status="supported", name="SecondSig", algorithm="SHA256", mode="HMAC",
        key_source=KeySource(key="SecondKey", iv="SecondIV"),
        payload_assembly=[{"step": 1, "desc": "加密"}],
    )

    # Get just the signature block first
    sig_out = _ts_signature([scheme1, scheme2])

    # Assert exactly one import line
    import_count = sig_out.count("import { createCipheriv")
    assert import_count == 1, f"Expected 1 import, got {import_count}"

    # Assert no duplicate function declarations
    assert sig_out.count("function sign(payload: string)") == 0, "function sign() should not appear (non-unique)"

    # Assert two distinct function names (should use sign_checkvalue, sign_second_sig or similar)
    assert "function sign_" in sig_out, "Expected unique function names like sign_checkvalue"
    lines = sig_out.split("\n")
    func_decls = [line for line in lines if line.startswith("function sign_")]
    assert len(func_decls) == 2, f"Expected 2 unique function declarations, got {len(func_decls)}: {func_decls}"

    # Full render should also be valid TypeScript
    out = _render_ts(shape, [scheme1, scheme2])
    assert out.count("import { createCipheriv") == 1, "Full render should have exactly 1 import"
    assert out.startswith("// Derived from openapi.yaml")
    assert "function sign_" in out


def test_render_py_runnable_signature_when_explicit():
    from loop_apidoc.generate.examples import _render_py
    from loop_apidoc.plan.models import CryptoScheme, KeySource

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json", "security": [],
    }
    explicit = CryptoScheme(
        status="supported", name="CheckValue", algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "組字串"}],
    )
    out = _render_py(shape, [explicit])
    assert out.startswith("# Derived from openapi.yaml")
    assert "import httpx" in out
    assert "AES" in out and "def sign" in out


def test_render_py_skeleton_with_gap_when_not_explicit():
    from loop_apidoc.generate.examples import _render_py
    from loop_apidoc.plan.models import CryptoScheme

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [], "body": [],
        "content_type": "application/json", "security": [],
    }
    out = _render_py(shape, [CryptoScheme(status="supported", name="Sig")])
    assert "# gap:" in out
    assert "def sign" in out
    assert "NotImplementedError" in out


def test_render_py_multiple_explicit_schemes_unique_functions():
    """Test that multiple explicit schemes produce unique function names and avoid duplicate imports."""
    from loop_apidoc.generate.examples import _render_py, _py_signature
    from loop_apidoc.plan.models import CryptoScheme, KeySource

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json", "security": [],
    }
    # Two explicit schemes
    scheme1 = CryptoScheme(
        status="supported", name="CheckValue", algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "組字串"}],
    )
    scheme2 = CryptoScheme(
        status="supported", name="SecondSig", algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="SecondKey", iv="SecondIV"),
        payload_assembly=[{"step": 1, "desc": "加密"}],
    )

    # Get just the signature block
    sig_out = _py_signature([scheme1, scheme2])

    # Assert exactly one import line for pycryptodome
    import_count = sig_out.count("from Crypto.Cipher import AES")
    assert import_count == 1, f"Expected 1 pycryptodome import, got {import_count}"

    # Assert no duplicate 'def sign(' (should use def sign_* instead)
    assert sig_out.count("def sign(") == 0, "def sign() should not appear when multiple schemes (non-unique)"

    # Assert two distinct function names
    assert "def sign_" in sig_out
    lines = sig_out.split("\n")
    func_decls = [line for line in lines if line.startswith("def sign_")]
    assert len(func_decls) == 2, f"Expected 2 unique function declarations, got {len(func_decls)}: {func_decls}"

    # Full render should also have exactly 1 import
    out = _render_py(shape, [scheme1, scheme2])
    assert out.count("from Crypto.Cipher import AES") == 1, "Full render should have exactly 1 pycryptodome import"
    assert out.startswith("# Derived from openapi.yaml")
    assert "def sign_" in out


def test_render_py_explicit_scheme_without_key_source_valid_env_names():
    """Test explicit CryptoScheme (algorithm + payload_assembly present) but key_source=None.

    Verify that env-var names are valid (uppercase, no angle brackets).
    The _snake function should strip angle brackets from <hash_key>/<hash_iv> fallbacks,
    producing HASH_KEY/HASH_IV for os.environ.get() env-var names.
    """
    from loop_apidoc.generate.examples import _render_py, _py_signature
    from loop_apidoc.plan.models import CryptoScheme
    import re

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json", "security": [],
    }
    # Explicit scheme (algorithm + payload_assembly present) but no key_source
    explicit_no_key_source = CryptoScheme(
        status="supported", name="CheckValue", algorithm="AES-256-CBC", mode="CBC",
        key_source=None,
        payload_assembly=[{"step": 1, "desc": "組字串"}],
    )
    out = _render_py(shape, [explicit_no_key_source])

    # Should render a runnable signature (not a gap)
    assert "def sign" in out
    assert "# gap:" not in out, "Should not be a gap when algorithm + payload_assembly are present"
    assert "AES" in out

    # Env-var names should be valid uppercase: HASH_KEY, HASH_IV
    assert "HASH_KEY" in out, "Expected HASH_KEY in generated code"
    assert "HASH_IV" in out, "Expected HASH_IV in generated code"

    # The env-var names should NOT contain angle brackets or invalid chars.
    # Extract env-var names from os.environ.get() calls.
    # Pattern: os.environ.get('<env_var_name>', ...)
    env_var_matches = re.findall(r"os\.environ\.get\('([^']+)'", out)
    assert len(env_var_matches) >= 2, f"Expected at least 2 os.environ.get() calls, got {len(env_var_matches)}"
    for var_name in env_var_matches:
        assert not var_name.startswith("<"), f"Env-var name should not start with '<': {var_name}"
        assert not var_name.endswith(">"), f"Env-var name should not end with '>': {var_name}"
        assert var_name.isupper() or "_" in var_name, f"Env-var name should be uppercase/snake: {var_name}"

    # Also test _py_signature directly to isolate the signature block
    sig_out = _py_signature([explicit_no_key_source])
    assert "HASH_KEY" in sig_out
    assert "HASH_IV" in sig_out
    sig_env_var_matches = re.findall(r"os\.environ\.get\('([^']+)'", sig_out)
    for var_name in sig_env_var_matches:
        assert not var_name.startswith("<"), f"Env-var name should not start with '<': {var_name}"
        assert not var_name.endswith(">"), f"Env-var name should not end with '>': {var_name}"
