from __future__ import annotations

from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.models import Issue, IssueCode, Severity


def _issue(code: IssueCode, severity: Severity, location: str,
           evidence: str, fix: str, *, target_file: str | None = None,
           field_path: str | None = None,
           requery_scope: str | None = None) -> Issue:
    return Issue(code=code, severity=severity, location=location,
                 evidence=evidence, suggested_fix=fix, target_file=target_file,
                 field_path=field_path, requery_scope=requery_scope)


def _endpoint_location(endpoint, index: int) -> str:
    if endpoint.method and endpoint.path:
        return f"paths.{endpoint.path}.{endpoint.method.lower()}"
    return f"endpoints[{index}]"


def _has_auth_marker(plan: NormalizationPlan) -> bool:
    for item in plan.missing_items:
        # Stage-specific extraction gaps can name the area (for example
        # ``authentication``), while agent-native inventory gaps are collected
        # once under stage ``10`` and carry the topic in ``detail``.
        marker = " ".join((item.area or "", item.detail or "")).lower()
        if "auth" in marker or "security" in marker:
            return True
    # An explicit "no auth / public" statement recorded as an operational note
    # (topic naming authentication/security) also counts: the source addressed
    # auth — a public API (e.g. OpenAPI root `security: []`) is not a silent gap.
    for op in plan.operational:
        topic = (op.topic or "").lower()
        if "auth" in topic or "security" in topic:
            return True
    # A documented request-signing / encryption scheme (integration.crypto) is the
    # API's authentication mechanism even when it is not an OpenAPI securityScheme
    # — e.g. a payment gateway secured only by a CheckMacValue / HMAC signature.
    # The source addressed authenticity, so this is not a silent auth gap.
    if plan.integration and plan.integration.crypto:
        return True
    return False


def _has_path_operation(plan: NormalizationPlan) -> bool:
    return any(endpoint.path for endpoint in plan.endpoints)


def _has_base_url(plan: NormalizationPlan) -> bool:
    return any((environment.base_url or "").strip()
               for environment in plan.environments)


def check_completeness(plan: NormalizationPlan) -> list[Issue]:
    issues: list[Issue] = []
    for index, endpoint in enumerate(plan.endpoints):
        location = _endpoint_location(endpoint, index)
        # Route every endpoint-level gap to the endpoints/ dir + the offending
        # field, and reread only that endpoint's source section (its path.method).
        # We deliberately do NOT name a specific ep<N>.json: the plan index is not
        # a reliable filename — _dedupe_endpoints collapses duplicate method+path
        # (shifting indices) and the assemble loader reads endpoints/*.json in
        # lexicographic glob order (ep10 before ep2 at 11+ files). The agent maps
        # the file by requery_scope (path.method), which is unambiguous.
        target_file = "endpoints/"
        # An endpoint with a method but no path is a valid OpenAPI 3.1 webhook
        # (an async callback delivered to a caller-defined URL), so only a
        # missing method — or a path with no method — is incomplete.
        if not endpoint.method:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.ERROR, location,
                "endpoint 缺少 HTTP method 或 path", "由來源補上 method 與 path",
                target_file=target_file, field_path="method",
                requery_scope=location))
        if not endpoint.responses:
            # A path-less webhook (async callback) often has no source-defined
            # receiver-response; require responses strictly only for real paths,
            # and surface a webhook's absence as a non-blocking WARNING.
            severity = Severity.ERROR if endpoint.path else Severity.WARNING
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, severity, location,
                "endpoint 沒有可轉為 OpenAPI 的 response 定義",
                "記錄來源的 response envelope；若來源未指定 HTTP status，使用 status: default（不是要求臆測 HTTP status）",
                target_file=target_file, field_path="responses",
                requery_scope=location))
        if not endpoint.summary:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, location,
                "endpoint 缺少 operation 說明", "由來源補上 operation 說明",
                target_file=target_file, field_path="summary",
                requery_scope=location))
        if not endpoint.examples:
            issues.append(_issue(
                IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, location,
                "endpoint 缺少 request/response 範例", "由來源補上範例",
                target_file=target_file, field_path="examples",
                requery_scope=location))

    if _has_path_operation(plan) and not _has_base_url(plan):
        issues.append(_issue(
            IssueCode.REQUIRED_INFO_MISSING, Severity.WARNING, "servers",
            "來源未提供可供 path operation 使用的 concrete server URL",
            "由來源補上 environment base_url；不可臆測 server URL"))

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
