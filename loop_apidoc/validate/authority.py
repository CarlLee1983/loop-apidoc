"""Name every claim whose only support is a supplementary carrier.

刻意做成逐條而不是 run 層級的單一警告。`SOURCE_FACTS_UNSCANNED` 的前例
已經證明 run 層警告會噪音化 —— 九個 benchmark case 永久帶著它,以致於
需要一整段文件解釋該警告的三種成因如何分辨。「這條規範性主張的唯一依據
是一封信」不該落到同一個下場。

Pure: 讀 plan 與 manifest,不碰檔案系統。
"""

from __future__ import annotations

from collections.abc import Iterator

from loop_apidoc.manifest.models import Manifest, SourceAuthority
from loop_apidoc.plan.models import NormalizationPlan, SourceCitation
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_PLAN_SECTIONS = (
    "environments",
    "security_schemes",
    "endpoints",
    "schemas",
    "errors",
    "operational",
)
_INTEGRATION_SECTIONS = (
    "transport",
    "amount_direction",
    "idempotency",
    "line_currency_policy",
    "crypto",
    "callbacks",
    "field_conditions",
    "test_cases",
)


def _cited_entries(plan: NormalizationPlan) -> Iterator[tuple[str, list[SourceCitation]]]:
    for section in _PLAN_SECTIONS:
        for index, entry in enumerate(getattr(plan, section) or []):
            yield f"{section}[{index}]", entry.citations
    # Schema 母層的 citations 已併入欄位引用,所以一個只有某欄位靠摘錄
    # 成立的 schema,母層不會是子集而被跳過 —— 欄位層必須自己走一遍。
    # 「手冊有 Order schema,信裡才說 notify_url 必填」正是這個形狀。
    for index, schema in enumerate(plan.schemas or []):
        for field in schema.field_evidence or []:
            yield f"schemas[{index}].field_evidence[{field.name}]", field.citations
    integration = plan.integration
    if integration is None:
        return
    for section in _INTEGRATION_SECTIONS:
        for index, entry in enumerate(getattr(integration, section) or []):
            yield f"integration.{section}[{index}]", entry.citations


def check_supplementary_support(
    plan: NormalizationPlan, manifest: Manifest
) -> list[Issue]:
    supplementary = {
        source.relative_path
        for source in manifest.local_sources
        if source.authority is SourceAuthority.SUPPLEMENTARY
    }
    if not supplementary:
        return []

    issues: list[Issue] = []
    for location, citations in _cited_entries(plan):
        named = {
            citation.manifest_source
            for citation in citations
            if citation.manifest_source
        }
        if not named or not named <= supplementary:
            continue
        carriers = "、".join(sorted(named))
        issues.append(
            Issue(
                code=IssueCode.SUPPLEMENTARY_SUPPORT,
                severity=Severity.WARNING,
                location=location,
                evidence=(
                    f"這條主張的唯一依據是次級佐證：{carriers}。"
                    "該載體無法重新取得，內容由摘錄者轉述，"
                    "與正式文件衝突時以正式文件為準。"
                ),
                suggested_fix=(
                    "若供應商已將此資訊寫入正式文件，改引用該文件並移除摘錄；"
                    "若尚未，保留現狀並在審查時確認摘錄內容。"
                ),
            )
        )
    return issues
