from __future__ import annotations

from loop_apidoc.plan.models import (
    CryptoScheme,
    EndpointEntry,
    IntegrationContract,
    MissingItem,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SecuritySchemeEntry,
    SourceConflict,
    UnverifiedItem,
)
from loop_apidoc.validate.completeness import check_completeness
from loop_apidoc.validate.models import IssueCode, Severity


def _endpoint(**kw) -> EndpointEntry:
    base = dict(status=PlanItemStatus.SUPPORTED, method="GET", path="/u",
                summary="s", responses=[{"status": "200"}],
                examples=[{"body": "x"}])
    base.update(kw)
    return EndpointEntry(**base)


def _plan(**kw) -> NormalizationPlan:
    base = dict(
        notebook_url="https://nb/x",
        endpoints=[_endpoint()],
        security_schemes=[SecuritySchemeEntry(status=PlanItemStatus.SUPPORTED, name="A")],
        operational=[OperationalEntry(status=PlanItemStatus.SUPPORTED, topic="rate")],
    )
    base.update(kw)
    return NormalizationPlan(**base)


def _codes(issues, severity):
    return [i.code for i in issues if i.severity is severity]


def test_complete_plan_has_no_errors():
    issues = check_completeness(_plan())
    assert _codes(issues, Severity.ERROR) == []


def test_path_operations_without_base_url_report_server_warning():
    plan = _plan(environments=[])
    issue = next(i for i in check_completeness(plan) if i.location == "servers")
    assert issue.severity is Severity.WARNING
    assert issue.code is IssueCode.REQUIRED_INFO_MISSING


def test_webhooks_without_base_url_do_not_report_server_warning():
    plan = _plan(environments=[], endpoints=[_endpoint(path=None, method="POST")])
    assert not any(i.location == "servers" for i in check_completeness(plan))


def test_missing_method_is_error():
    issues = check_completeness(_plan(endpoints=[_endpoint(method=None)]))
    assert IssueCode.REQUIRED_INFO_MISSING in _codes(issues, Severity.ERROR)


def test_webhook_endpoint_method_without_path_is_not_missing_path_error():
    # A method-only endpoint is a valid OpenAPI 3.1 webhook (async callback),
    # so it must not be flagged for a missing path.
    issues = check_completeness(_plan(endpoints=[
        _endpoint(method="POST", path=None, summary="付款結果通知"),
    ]))
    assert _codes(issues, Severity.ERROR) == []


def test_path_without_method_is_still_error():
    issues = check_completeness(_plan(endpoints=[_endpoint(method=None, path="/u")]))
    assert IssueCode.REQUIRED_INFO_MISSING in _codes(issues, Severity.ERROR)


def test_no_responses_is_error():
    issues = check_completeness(_plan(endpoints=[_endpoint(responses=[])]))
    assert IssueCode.REQUIRED_INFO_MISSING in _codes(issues, Severity.ERROR)


def test_missing_endpoint_detail_routes_to_endpoint_dir_and_path():
    # 缺 responses 的 endpoint → 結構化提示帶 field_path=responses、以 endpoints/ 為
    # 目標目錄,並以該 endpoint 的 path.method 作為(可證、唯一)重讀範圍。
    # 注意:不指向特定 ep<N>.json — plan 順序經 dedup/字典序 glob 後不保證等於檔名編號。
    issues = check_completeness(_plan(endpoints=[
        _endpoint(),
        _endpoint(path="/orders", responses=[]),
    ]))
    routed = [i for i in issues if i.field_path == "responses"]
    assert routed, "缺 responses 的 endpoint 應帶 field_path=responses"
    issue = routed[0]
    assert issue.target_file == "endpoints/"
    assert issue.requery_scope == issue.location == "paths./orders.get"


def test_missing_summary_is_warning_only():
    issues = check_completeness(_plan(endpoints=[_endpoint(summary=None)]))
    assert _codes(issues, Severity.ERROR) == []
    assert IssueCode.REQUIRED_INFO_MISSING in _codes(issues, Severity.WARNING)


def test_no_security_and_no_marker_is_error():
    issues = check_completeness(_plan(security_schemes=[]))
    assert IssueCode.REQUIRED_INFO_MISSING in _codes(issues, Severity.ERROR)


def test_no_security_but_marked_missing_is_ok():
    plan = _plan(security_schemes=[],
                 missing_items=[MissingItem(area="authentication", detail="來源未提供")])
    assert _codes(check_completeness(plan), Severity.ERROR) == []


def test_unverified_item_is_error():
    plan = _plan(unverified_items=[UnverifiedItem(area="sources", detail="無法確認")])
    issues = check_completeness(plan)
    assert IssueCode.SOURCE_UNVERIFIED in _codes(issues, Severity.ERROR)


def test_source_conflict_is_error():
    plan = _plan(source_conflicts=[SourceConflict(area="base_url", detail="兩來源不一致")])
    issues = check_completeness(plan)
    assert IssueCode.SOURCE_CONFLICT in _codes(issues, Severity.ERROR)


def test_webhook_without_responses_is_warning_not_error():
    # path-less webhook(async callback)無接收端回應定義時,降為 WARNING 而非硬 ERROR。
    issues = check_completeness(_plan(endpoints=[
        _endpoint(method="POST", path=None, summary="付款結果通知", responses=[]),
    ]))
    assert IssueCode.REQUIRED_INFO_MISSING not in _codes(issues, Severity.ERROR)
    assert IssueCode.REQUIRED_INFO_MISSING in _codes(issues, Severity.WARNING)


def test_no_security_scheme_but_integration_crypto_is_ok():
    # A payment API whose only authentication is a documented request-signing
    # scheme (e.g. ECPay CheckMacValue / a HMAC signature) carries no OpenAPI
    # securityScheme — the signature lives in integration.crypto. The source DID
    # address authenticity, so this must NOT trip the "no auth" gap.
    plan = _plan(
        security_schemes=[],
        integration=IntegrationContract(crypto=[
            CryptoScheme(status=PlanItemStatus.SUPPORTED, name="CheckMacValue",
                         purpose="signature", algorithm="SHA256")]),
    )
    assert _codes(check_completeness(plan), Severity.ERROR) == []


def test_no_security_but_public_marked_in_operational_is_ok():
    # 來源明示公開無需驗證(記在 operational,topic=Authentication)→ 不應 ERROR
    plan = _plan(
        security_schemes=[],
        operational=[OperationalEntry(
            status=PlanItemStatus.SUPPORTED, topic="Authentication",
            detail="來源明示 root security: [] 公開無需驗證")],
    )
    assert _codes(check_completeness(plan), Severity.ERROR) == []
