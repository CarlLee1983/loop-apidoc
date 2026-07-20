from datetime import datetime, timezone

from loop_apidoc.generate.models import GenerateResult, ProvenanceDocument
from loop_apidoc.manifest.models import LocalSource, Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.plan.integration import build_integration_contract
from loop_apidoc.plan.models import (
    CryptoScheme,
    ContractTestCase,
    CryptoVerify,
    IntegrationContract,
    KeySource,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SourceCitation,
)
from loop_apidoc.validate.integration import check_integration
from loop_apidoc.validate.models import IssueCode


def _result(openapi: dict) -> GenerateResult:
    return GenerateResult(openapi=openapi, markdown="", provenance=ProvenanceDocument(notebook_url="x"))


def _cited(**kw):
    return dict(status=PlanItemStatus.SUPPORTED, citations=[SourceCitation(query_id="i", answer_path="i")], **kw)


def test_uncited_crypto_is_unsupported_assertion():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[CryptoScheme(status=PlanItemStatus.UNVERIFIED, name="c")]),
    )
    codes = [i.code for i in check_integration(plan, _result({}))]
    assert IssueCode.UNSUPPORTED_ASSERTION in codes


def test_dangling_operation_ref_is_output_mismatch():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            test_cases=[ContractTestCase(**_cited(name="t", operation_ref="paths./ghost.post"))]
        ),
    )
    codes = [i.code for i in check_integration(plan, _result({"paths": {}}))]
    assert IssueCode.OUTPUT_MISMATCH in codes


def test_resolvable_operation_ref_ok():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            test_cases=[ContractTestCase(**_cited(name="t", operation_ref="paths./mpg.post"))]
        ),
    )
    openapi = {"paths": {"/mpg": {"post": {}}}}
    codes = [i.code for i in check_integration(plan, _result(openapi))]
    assert IssueCode.OUTPUT_MISMATCH not in codes


def test_signal_word_without_crypto_is_required_info_missing():
    plan = NormalizationPlan(
        notebook_url="x",
        operational=[OperationalEntry(status=PlanItemStatus.SUPPORTED, topic="安全", detail="請以 AES 加密 TradeInfo")],
        integration=IntegrationContract(),
    )
    codes = [i.code for i in check_integration(plan, _result({}))]
    assert IssueCode.REQUIRED_INFO_MISSING in codes


def test_signal_gap_routes_to_integration_crypto():
    plan = NormalizationPlan(
        notebook_url="x",
        operational=[OperationalEntry(status=PlanItemStatus.SUPPORTED, topic="安全", detail="請以 AES 加密 TradeInfo")],
        integration=IntegrationContract(),
    )
    issue = next(i for i in check_integration(plan, _result({}))
                 if i.code is IssueCode.REQUIRED_INFO_MISSING)
    assert issue.target_file == "integration.json"
    assert issue.field_path == "crypto"
    assert issue.requery_scope


def test_dangling_operation_ref_routes_to_test_case_field():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            test_cases=[ContractTestCase(**_cited(name="t", operation_ref="paths./ghost.post"))]
        ),
    )
    issue = next(i for i in check_integration(plan, _result({"paths": {}}))
                 if i.code is IssueCode.OUTPUT_MISMATCH)
    assert issue.target_file == "integration.json"
    assert issue.field_path == "test_cases.t.operation_ref"


def test_dangling_payload_ref_routes_to_callback_field():
    from loop_apidoc.plan.models import Callback
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            callbacks=[Callback(**_cited(name="cb", payload_ref="schemas.Ghost Schema"))]
        ),
    )
    openapi = {"components": {"schemas": {}}, "paths": {}}
    issue = next(i for i in check_integration(plan, _result(openapi))
                 if i.code is IssueCode.OUTPUT_MISMATCH)
    assert issue.target_file == "integration.json"
    assert issue.field_path == "callbacks.cb.payload_ref"


def test_no_mechanics_no_signal_is_clean():
    plan = NormalizationPlan(notebook_url="x")
    assert check_integration(plan, _result({})) == []


# ---------------------------------------------------------------------------
# Fix 1 — fail-closed on UNVERIFIED integration entries (multi-source run)
# ---------------------------------------------------------------------------

def _two_source_manifest() -> Manifest:
    def _src(path: str, sha: str) -> LocalSource:
        return LocalSource(
            relative_path=path,
            mime_type="application/pdf",
            source_format=SourceFormat.PDF,
            size_bytes=1024,
            sha256=sha,
            scanned_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
            supported=True,
            status=ProcessingStatus.PENDING,
        )
    return Manifest(
        sources_root=".",
        generated_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
        local_sources=[_src("source_a.pdf", "aaa"), _src("source_b.pdf", "bbb")],
    )


def test_unverified_crypto_source_is_source_unverified():
    """In a multi-source run, a crypto entry whose source matches no manifest
    source must produce SOURCE_UNVERIFIED (not be silently passed through)."""
    manifest = _two_source_manifest()
    integration_json = {
        "crypto": [
            {
                "name": "TestCrypto",
                "algorithm": "AES",
                "source": "unknown_source.pdf p.5",  # matches neither manifest source
            }
        ]
    }
    plan = NormalizationPlan(notebook_url="x")
    contract = build_integration_contract(integration_json, plan, manifest)
    plan = plan.model_copy(update={"integration": contract})
    codes = [i.code for i in check_integration(plan, _result({}))]
    assert IssueCode.SOURCE_UNVERIFIED in codes


# --- 範例簽章接回驗證 ---


def _runnable_crypto(field):
    return CryptoScheme(
        status=PlanItemStatus.SUPPORTED,
        citations=[SourceCitation(query_id="i", answer_path="i")],
        name="CheckValue", purpose="request",
        algorithm="AES-256-CBC", mode="CBC",
        key_source=KeySource(key="HashKey", iv="HashIV"),
        payload_assembly=[{"step": 1, "desc": "組字串", "fields": ["Amount"]}],
        verify=CryptoVerify(field=field) if field else None,
    )


def _result_with_examples(examples: dict) -> GenerateResult:
    return GenerateResult(
        openapi={}, markdown="",
        provenance=ProvenanceDocument(notebook_url="x"),
        examples=examples,
    )


def test_runnable_without_verify_field_is_required_info_missing():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[_runnable_crypto(field=None)]),
    )
    codes = [i.code for i in check_integration(plan, _result_with_examples({}))]
    assert IssueCode.REQUIRED_INFO_MISSING in codes


def test_example_uses_target_but_not_wired_is_output_mismatch():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[_runnable_crypto(field="CheckMacValue")]),
    )
    # 範例含目標欄位作為 body key,但沒有 = sign(...) 接回 → 生成器漏接
    examples = {"examples/Pay/request.py": 'payload = {\n    "CheckMacValue": "<x>",\n}\n'}
    issues = check_integration(plan, _result_with_examples(examples))
    mism = [i for i in issues if i.code is IssueCode.OUTPUT_MISMATCH]
    assert mism and mism[0].location == "examples/Pay/request.py"


def test_unsupported_des_cbc_does_not_require_request_wiring():
    des = _runnable_crypto(field="Msg").model_copy(
        update={"algorithm": "DES", "name": "DES Encryption"}
    )
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[des]),
    )
    examples = {
        "examples/Deposit/request.py": 'payload = {\n    "Msg": "<msg>",\n}\n'
    }

    codes = [
        issue.code
        for issue in check_integration(plan, _result_with_examples(examples))
    ]

    assert IssueCode.OUTPUT_MISMATCH not in codes


def test_example_properly_wired_is_clean():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[_runnable_crypto(field="CheckMacValue")]),
    )
    examples = {
        "examples/Pay/request.py": (
            'payload = {\n    "CheckMacValue": "<x>",\n}\n'
            'sig_payload = "&".join(...)\n'
            'payload["CheckMacValue"] = sign(sig_payload)\n'
        )
    }
    codes = [i.code for i in check_integration(plan, _result_with_examples(examples))]
    assert IssueCode.OUTPUT_MISMATCH not in codes


def test_multi_scheme_sign_name_wiring_is_clean():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[_runnable_crypto(field="CheckMacValue")]),
    )
    examples = {
        "examples/Pay/request.py": (
            'payload = {\n    "CheckMacValue": "<x>",\n}\n'
            'sig_payload = "&".join(...)\n'
            'payload["CheckMacValue"] = sign_checkvalue(sig_payload)\n'
        )
    }
    codes = [i.code for i in check_integration(plan, _result_with_examples(examples))]
    assert IssueCode.OUTPUT_MISMATCH not in codes


def test_curl_not_checked_for_wiring():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[_runnable_crypto(field="CheckMacValue")]),
    )
    # 只有 curl 用到欄位且不接回 → 不應報 OUTPUT_MISMATCH
    examples = {"examples/Pay/request.sh": "curl ... CheckMacValue=<x>"}
    codes = [i.code for i in check_integration(plan, _result_with_examples(examples))]
    assert IssueCode.OUTPUT_MISMATCH not in codes


def test_target_only_in_comment_is_not_output_mismatch():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(crypto=[_runnable_crypto(field="CheckMacValue")]),
    )
    # 目標欄位只出現在簽章 helper 註解,且此 endpoint body 並不攜帶該欄位 → 不應誤報
    examples = {"examples/Other/request.py": (
        "# 簽章 CheckMacValue：AES-256\n"
        "def sign_checkmacvalue(payload):\n    ...\n"
        'payload = {\n    "PostData_": "<x>",\n}\n'
    )}
    codes = [i.code for i in check_integration(plan, _result_with_examples(examples))]
    assert IssueCode.OUTPUT_MISMATCH not in codes


def test_callback_payload_ref_resolves_via_sanitized_schema_key():
    # payload_ref names the inventory schema ("Backend Notify Body"); the OpenAPI
    # component key is sanitized ("Backend_Notify_Body"). The check must resolve
    # via the same sanitization the generator uses, not a raw-name compare.
    from loop_apidoc.plan.models import Callback
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            callbacks=[Callback(**_cited(name="Backend Notify", payload_ref="schemas.Backend Notify Body"))]
        ),
    )
    openapi = {"components": {"schemas": {"Backend_Notify_Body": {}}}, "paths": {}}
    codes = [i.code for i in check_integration(plan, _result(openapi))]
    assert IssueCode.OUTPUT_MISMATCH not in codes


def test_callback_payload_ref_truly_missing_is_output_mismatch():
    from loop_apidoc.plan.models import Callback
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            callbacks=[Callback(**_cited(name="cb", payload_ref="schemas.Ghost Schema"))]
        ),
    )
    openapi = {"components": {"schemas": {"Backend_Notify_Body": {}}}, "paths": {}}
    codes = [i.code for i in check_integration(plan, _result(openapi))]
    assert IssueCode.OUTPUT_MISMATCH in codes
