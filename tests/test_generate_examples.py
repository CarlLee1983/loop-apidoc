from loop_apidoc.generate.examples import (
    _placeholder,
    _resolve_value,
    _request_shape,
    _request_signing_schemes,
    _signature_explicit,
)
from loop_apidoc.plan.models import CryptoScheme, CryptoVerify, IntegrationContract, KeySource, NormalizationPlan


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
    # content_type 為 JSON → body 以 JSON 編碼(與 TS/Py 一致),而非表單 k=v
    assert '"Amount": "<amount>"' in out


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


def test_build_examples_emits_three_files_per_operation_and_readme():
    from loop_apidoc.generate.examples import build_examples
    from loop_apidoc.plan.models import NormalizationPlan

    openapi = {
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/pay": {
                "post": {
                    "operationId": "PayOrder",
                    "requestBody": {
                        "content": {"application/json": {"schema": {"type": "object",
                            "properties": {"Amount": {"type": "integer"}}}}}
                    },
                }
            }
        },
    }
    out = build_examples(openapi, NormalizationPlan(notebook_url="x"))
    assert "examples/README.md" in out
    assert "examples/PayOrder/request.sh" in out
    assert "examples/PayOrder/request.ts" in out
    assert "examples/PayOrder/request.py" in out
    assert "POST" in out["examples/PayOrder/request.sh"]


def test_build_examples_empty_when_no_operations():
    from loop_apidoc.generate.examples import build_examples
    from loop_apidoc.plan.models import NormalizationPlan

    assert build_examples({"paths": {}}, NormalizationPlan(notebook_url="x")) == {}


def test_build_examples_webhook_uses_receiver_placeholder():
    from loop_apidoc.generate.examples import build_examples
    from loop_apidoc.plan.models import NormalizationPlan

    openapi = {"webhooks": {"Notify": {"post": {"operationId": "Notify"}}}}
    out = build_examples(openapi, NormalizationPlan(notebook_url="x"))
    assert "<your_receiver_url>" in out["examples/Notify/request.sh"]


def test_build_examples_readme_lists_signing_schemes():
    from loop_apidoc.generate.examples import build_examples, HEADER_NOTE
    from loop_apidoc.plan.models import (
        CryptoScheme, IntegrationContract, NormalizationPlan
    )

    openapi = {
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/pay": {
                "post": {
                    "operationId": "PayOrder",
                    "requestBody": {
                        "content": {"application/json": {"schema": {"type": "object",
                            "properties": {"Amount": {"type": "integer"}}}}}
                    },
                }
            }
        },
    }
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            crypto=[
                CryptoScheme(
                    status="supported", name="CheckValue", algorithm="AES-256-CBC",
                    purpose="request"
                ),
            ]
        ),
    )
    out = build_examples(openapi, plan)
    readme = out["examples/README.md"]

    # Verify HEADER_NOTE marker is present
    assert HEADER_NOTE in readme
    # Verify section heading for signing schemes
    assert "## 通用簽章機制" in readme
    # Verify scheme name is listed
    assert "CheckValue" in readme


def test_render_py_non_cbc_mode_falls_to_gap():
    """Test that explicit scheme with non-CBC mode (e.g., GCM) emits gap, not runnable code.

    This enforces the no-fabrication invariant: we must NOT emit AES.MODE_CBC
    when the source states a different mode.
    """
    from loop_apidoc.generate.examples import _render_py
    from loop_apidoc.plan.models import CryptoScheme, KeySource

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json", "security": [],
    }
    # Explicit scheme: has algorithm and payload_assembly, but mode is NOT CBC
    explicit_non_cbc = CryptoScheme(
        status="supported", name="Sig", algorithm="AES-256-GCM", mode="GCM",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "encrypt with GCM"}],
    )
    out = _render_py(shape, [explicit_non_cbc])

    # Should emit gap, not runnable code
    assert "# gap:" in out, "Non-CBC explicit scheme should emit gap comment"
    assert "NotImplementedError" in out, "Gap should raise NotImplementedError"
    assert "AES.new(" not in out, "Should not emit AES.new() for non-CBC mode"
    assert "AES.MODE_CBC" not in out, "Should not emit MODE_CBC for non-CBC mode"


def test_render_ts_non_cbc_mode_falls_to_gap():
    """Explicit scheme with non-CBC mode (e.g. GCM) must emit gap, not runnable TS.

    Mirrors the Python fail-closed path: createCipheriv('aes-256-gcm', …) without
    auth-tag/AAD handling looks runnable but is silently wrong, which violates the
    no-fabrication invariant. GCM-only schemes must NOT pull in the crypto import.
    """
    from loop_apidoc.generate.examples import _render_ts
    from loop_apidoc.plan.models import CryptoScheme, KeySource

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json", "security": [],
    }
    explicit_non_cbc = CryptoScheme(
        status="supported", name="Sig", algorithm="AES-256-GCM", mode="GCM",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "encrypt with GCM"}],
    )
    out = _render_ts(shape, [explicit_non_cbc])

    assert "// gap:" in out, "Non-CBC explicit scheme should emit gap comment"
    assert "createCipheriv(" not in out, "Should not emit createCipheriv() for non-CBC mode"
    assert "import { createCipheriv" not in out, "GCM-only should not pull crypto import"
    assert "throw new Error" in out, "Gap should throw"


def _shape(**over):
    base = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [], "content_type": None, "security": [],
    }
    base.update(over)
    return base


# --- #1 三語 body 編碼一致 ---

def test_encoding_consistent_json_across_languages():
    from loop_apidoc.generate.examples import _render_curl, _render_py, _render_ts

    shape = _shape(
        body=[("Amount", "placeholder", "<amount>")],
        content_type="application/json",
    )
    sh = _render_curl(shape, [])
    ts = _render_ts(shape, [])
    py = _render_py(shape, [])
    # curl 用 --data 帶 JSON,而非 --data-urlencode 表單
    assert "--data '" in sh
    assert '"Amount": "<amount>"' in sh
    assert "--data-urlencode" not in sh
    # TS 用 JSON.stringify
    assert "JSON.stringify(body)" in ts
    # Py 用 json=payload
    assert "json=payload" in py


def test_encoding_consistent_form_across_languages():
    from loop_apidoc.generate.examples import _render_curl, _render_py, _render_ts

    shape = _shape(
        body=[("Amount", "placeholder", "<amount>")],
        content_type="application/x-www-form-urlencoded",
    )
    sh = _render_curl(shape, [])
    ts = _render_ts(shape, [])
    py = _render_py(shape, [])
    assert "--data-urlencode 'Amount=<amount>'" in sh
    assert "new URLSearchParams(body)" in ts
    assert "JSON.stringify" not in ts
    assert "data=payload" in py
    assert "json=payload" not in py


# --- #3 header / path 參數不再被三語丟掉 ---

def test_header_params_rendered_in_all_languages():
    from loop_apidoc.generate.examples import _render_curl, _render_py, _render_ts

    shape = _shape(
        header=[("X-Api-Key", "placeholder", "<x_api_key>")],
        body=[("Amount", "placeholder", "<amount>")],
        content_type="application/json",
    )
    sh = _render_curl(shape, [])
    ts = _render_ts(shape, [])
    py = _render_py(shape, [])
    assert "-H 'X-Api-Key: <x_api_key>'" in sh
    assert "X-Api-Key" in ts and "headers" in ts
    assert "X-Api-Key" in py and "headers=headers" in py


def test_path_params_interpolated_no_literal_braces():
    from loop_apidoc.generate.examples import _render_curl, _render_py, _render_ts

    shape = _shape(
        url="https://api.example.com/orders/{orderId}",
        path=[("orderId", "placeholder", "<order_id>")],
    )
    for out in (
        _render_curl(shape, []),
        _render_ts(shape, []),
        _render_py(shape, []),
    ):
        assert "{orderId}" not in out
        assert "<order_id>" in out


def test_query_params_go_to_url_not_body():
    from loop_apidoc.generate.examples import _render_curl, _render_py, _render_ts

    shape = _shape(query=[("Page", "placeholder", "<page>")])
    sh = _render_curl(shape, [])
    ts = _render_ts(shape, [])
    py = _render_py(shape, [])
    # query 進 URL / params,不再被塞進 body
    assert "?Page=<page>" in sh
    assert "--data" not in sh
    assert "URLSearchParams" in ts
    assert "params=params" in py


# --- minor 修正 ---

def test_ts_body_preserves_original_field_name():
    from loop_apidoc.generate.examples import _render_ts

    shape = _shape(
        body=[("MerchantID", "placeholder", "<merchant_id>")],
        content_type="application/json",
    )
    out = _render_ts(shape, [])
    # 必須保留原欄位名(送上線的 key),不可 snake 化成 merchant_id
    assert '"MerchantID":' in out
    assert "merchant_id:" not in out


def test_resolve_value_reads_schema_level_example():
    node = {"schema": {"type": "string", "example": "ABC"}}
    assert _resolve_value("Code", node) == ("source", "ABC")


def test_py_signature_gcm_only_omits_pycryptodome_import():
    from loop_apidoc.generate.examples import _py_signature
    from loop_apidoc.plan.models import CryptoScheme

    gcm = CryptoScheme(
        status="supported", name="Sig", algorithm="AES-256-GCM", mode="GCM",
        payload_assembly=[{"step": 1, "desc": "encrypt with GCM"}],
    )
    sig = _py_signature([gcm])
    # GCM-only → gap,不該 emit 用不到的 pycryptodome / hashlib import
    assert "from Crypto.Cipher import AES" not in sig
    assert "import hashlib" not in sig
    assert "NotImplementedError" in sig


# --- 簽章接回 request 欄位 ---


def _runnable_scheme(target="CheckMacValue", fields=("MerchantID", "Amount")):
    return CryptoScheme(
        status="supported", name="CheckValue", purpose="request",
        algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "排序欄位後加密", "fields": list(fields)}],
        verify=CryptoVerify(field=target, method="AES", desc="比對簽章"),
    )


def _sig_shape():
    return _shape(
        body=[
            ("MerchantID", "placeholder", "<merchant_id>"),
            ("Amount", "placeholder", "<amount>"),
            ("CheckMacValue", "placeholder", "<check_mac_value>"),
        ],
        content_type="application/x-www-form-urlencoded",
    )


def test_wire_target_resolves_body_field():
    from loop_apidoc.generate.examples import _wire_target
    assert _wire_target(_runnable_scheme(), _sig_shape()) == ("body", "CheckMacValue")


def test_wire_target_none_when_field_absent_in_request():
    from loop_apidoc.generate.examples import _wire_target
    assert _wire_target(_runnable_scheme(target="NotThere"), _sig_shape()) is None


def test_wire_target_none_when_no_verify_field():
    from loop_apidoc.generate.examples import _wire_target
    s = _runnable_scheme()
    s = s.model_copy(update={"verify": None})
    assert _wire_target(s, _sig_shape()) is None


def test_wire_target_none_when_not_runnable():
    from loop_apidoc.generate.examples import _wire_target
    s = CryptoScheme(status="supported", name="x", verify=CryptoVerify(field="CheckMacValue"))
    assert _wire_target(s, _sig_shape()) is None


def test_payload_field_names_keeps_source_fields_excluding_target():
    from loop_apidoc.generate.examples import _payload_field_names
    s = _runnable_scheme(fields=("MerchantID", "Amount", "CheckMacValue", "Ghost"))
    names = _payload_field_names(s, "CheckMacValue")
    # 來源明列的簽章欄位全保留(去掉 target);內層欄位如 Ghost 不再被 body 交集濾掉
    assert names == ["MerchantID", "Amount", "Ghost"]


def test_render_ts_wires_signature_into_body():
    from loop_apidoc.generate.examples import _render_ts
    out = _render_ts(_sig_shape(), [_runnable_scheme()])
    assert "createCipheriv" in out
    assert "請依 payload_assembly 核對" in out
    # body 欄位以實際值入簽章字串(per-field,非 [k] 迴圈)
    assert 'String((body as any)["MerchantID"])' in out
    assert 'String((body as any)["Amount"])' in out
    assert "[\"CheckMacValue\"] = sign(payload)" in out


def test_render_py_wires_signature_into_body():
    from loop_apidoc.generate.examples import _render_py
    out = _render_py(_sig_shape(), [_runnable_scheme()])
    assert "def sign" in out
    assert "sig_payload = " in out
    assert 'payload["CheckMacValue"] = sign(sig_payload)' in out


def test_render_py_wiring_empty_fields_uses_placeholder_but_still_wires():
    from loop_apidoc.generate.examples import _render_py
    s = _runnable_scheme(fields=())
    out = _render_py(_sig_shape(), [s])
    assert "來源未列出簽章欄位" in out
    assert 'payload["CheckMacValue"] = sign(sig_payload)' in out


def test_render_curl_notes_target_field_but_does_not_wire():
    from loop_apidoc.generate.examples import _render_curl
    out = _render_curl(_sig_shape(), [_runnable_scheme()])
    assert "簽章值請填回欄位：CheckMacValue" in out
    assert "= sign(" not in out  # curl 不接回


def test_render_ts_wires_into_header_when_target_is_header():
    from loop_apidoc.generate.examples import _render_ts
    shape = _shape(
        header=[("X-Signature", "placeholder", "<x_signature>")],
        body=[("Amount", "placeholder", "<amount>")],
        content_type="application/json",
    )
    s = _runnable_scheme(target="X-Signature", fields=("Amount",))
    out = _render_ts(shape, [s])
    # assignment target must be headers
    assert "(headers as any)[\"X-Signature\"] = sign(payload)" in out
    # payload-construction must read field values from body, not from headers
    assert 'String((body as any)["Amount"])' in out, "payload fields must be read from body"
    assert "String((headers" not in out, "payload construction must NOT read from headers"


def test_render_py_wires_into_header_when_target_is_header():
    from loop_apidoc.generate.examples import _render_py
    shape = _shape(
        header=[("X-Signature", "placeholder", "<x_signature>")],
        body=[("Amount", "placeholder", "<amount>")],
        content_type="application/json",
    )
    s = _runnable_scheme(target="X-Signature", fields=("Amount",))
    out = _render_py(shape, [s])
    # assignment target must be headers
    assert 'headers["X-Signature"] = sign(sig_payload)' in out
    # payload-construction must read field values from payload (body dict), not headers
    assert 'str(payload["Amount"])' in out, "payload fields must be read from payload (body dict)"
    assert 'str(headers[' not in out, "payload construction must NOT read from headers"


def test_no_wiring_when_scheme_has_no_verify_field():
    # 既有行為回歸:無 verify.field 的可跑 scheme 不接回(只渲染 sign 函式)
    from loop_apidoc.generate.examples import _render_py
    s = _runnable_scheme().model_copy(update={"verify": None})
    out = _render_py(_sig_shape(), [s])
    assert "def sign" in out
    assert "= sign(sig_payload)" not in out


def test_render_py_cbc_via_algorithm_string_is_runnable():
    """Test that scheme with algorithm='AES-256-CBC' (no explicit mode field) is runnable.

    If algorithm string contains CBC, it should render as runnable code.
    """
    from loop_apidoc.generate.examples import _render_py
    from loop_apidoc.plan.models import CryptoScheme, KeySource

    shape = {
        "method": "POST", "url": "https://api.example.com/pay",
        "query": [], "header": [], "path": [],
        "body": [("Amount", "placeholder", "<amount>")],
        "content_type": "application/json", "security": [],
    }
    # Explicit scheme: algorithm contains CBC, but mode field is None/unset
    explicit_cbc_via_algo = CryptoScheme(
        status="supported", name="CheckValue", algorithm="AES-256-CBC", mode=None,
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "組字串"}],
    )
    out = _render_py(shape, [explicit_cbc_via_algo])

    # Should render runnable code, not gap
    assert "def sign" in out, "Should emit function definition"
    assert "# gap:" not in out, "Should NOT be a gap when algorithm contains CBC"
    assert "AES.new(" in out, "Should emit AES.new() for CBC"
    assert "AES.MODE_CBC" in out, "Should emit MODE_CBC for CBC"


def test_aes_cbc_encryption_signature_returns_hex_not_sha256():
    from loop_apidoc.generate.examples import _py_signature, _ts_signature
    s = CryptoScheme(
        status="supported", name="TradeInfo", purpose="request",
        algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "enc", "fields": ["Amt"]}],
    )
    py = _py_signature([s])
    assert "AES.new" in py and "MODE_CBC" in py
    assert "hashlib.sha256" not in py  # AES 加密輸出為 hex,不應接 SHA256
    ts = _ts_signature([s])
    assert "createCipheriv" in ts
    assert "createHash('sha256')" not in ts


def test_signed_payload_uses_source_fields_even_when_not_in_body():
    from loop_apidoc.generate.examples import _py_wiring
    s = CryptoScheme(
        status="supported", name="TradeInfo", purpose="request",
        algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "組字串", "fields": ["RespondType", "Amt"]}],
        verify=CryptoVerify(field="TradeInfo"),
    )
    # body 只攜帶加密後目標欄位 TradeInfo;簽章明文欄位 RespondType/Amt 為內層(加密前)參數
    shape = {"method": "POST", "url": "u", "query": [], "header": [], "path": [],
             "body": [("TradeInfo", "placeholder", "<trade_info>")],
             "content_type": "application/x-www-form-urlencoded", "security": []}
    out = "\n".join(_py_wiring(shape, [s]))
    assert "RespondType" in out and "Amt" in out  # 來源明列欄位不應被 body 交集濾掉
