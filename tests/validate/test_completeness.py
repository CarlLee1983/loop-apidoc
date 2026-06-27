from __future__ import annotations

from loop_apidoc.plan.models import (
    EndpointEntry,
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
