from __future__ import annotations

from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.models import Issue, IssueCode, Severity


def _issue(code: IssueCode, severity: Severity, location: str,
           evidence: str, fix: str) -> Issue:
    return Issue(code=code, severity=severity, location=location,
                 evidence=evidence, suggested_fix=fix)


def _endpoint_location(endpoint, index: int) -> str:
    if endpoint.method and endpoint.path:
        return f"paths.{endpoint.path}.{endpoint.method.lower()}"
    return f"endpoints[{index}]"


def _has_auth_marker(plan: NormalizationPlan) -> bool:
    for item in plan.missing_items:
        area = (item.area or "").lower()
        if "auth" in area or "security" in area:
            return True
    return False


def check_completeness(plan: NormalizationPlan) -> list[Issue]:
    issues: list[Issue] = []
    for index, endpoint in enumerate(plan.endpoints):
        location = _endpoint_location(endpoint, index)
        if not endpoint.method or not endpoint.path:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR, location,
                "endpoint 缺少 HTTP method 或 path", "由來源補上 method 與 path"))
        if not endpoint.responses:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR, location,
                "endpoint 沒有任何 response 定義", "由來源補上 response status 與 schema"))
        if not endpoint.summary:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, location,
                "endpoint 缺少 operation 說明", "由來源補上 operation 說明"))
        if not endpoint.examples:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, location,
                "endpoint 缺少 request/response 範例", "由來源補上範例"))

    if not plan.security_schemes and not _has_auth_marker(plan):
        issues.append(_issue(
            IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR,
            "components.securitySchemes",
            "無 security scheme，且來源未明確標示未提供 authentication",
            "由來源補上 authentication，或記錄為來源未提供"))

    if not plan.operational:
        issues.append(_issue(
            IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, "operational",
            "缺少 rate limit/timeout/retry 等 operational 資訊", "由來源補上 operational 資訊"))

    for item in plan.unverified_items:
        issues.append(_issue(
            IssueCode.SOURCE_UNVERIFIED, Severity.ERROR, f"unverified.{item.area}",
            item.detail, "確認來源以解除 unverified 狀態"))
    for item in plan.source_conflicts:
        issues.append(_issue(
            IssueCode.SOURCE_CONFLICT, Severity.ERROR, f"conflict.{item.area}",
            item.detail, "揭露並由來源澄清衝突，不可任選其一"))

    return issues
