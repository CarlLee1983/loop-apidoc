from loop_apidoc.generate.models import GenerateResult, ProvenanceDocument
from loop_apidoc.plan.models import (
    CryptoScheme,
    ContractTestCase,
    IntegrationContract,
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


def test_no_mechanics_no_signal_is_clean():
    plan = NormalizationPlan(notebook_url="x")
    assert check_integration(plan, _result({})) == []
