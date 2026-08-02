from __future__ import annotations

import json
from html import escape
from pathlib import Path

from loop_apidoc.domain.conformance import (
    CompatibilityAmendmentProposal,
    EffectiveContract,
    FeedbackAssessment,
    NormativeRelease,
    ObservationBundle,
)
from loop_apidoc.feedback.erratum import ProviderErratumHandoff
from loop_apidoc.privacy import redact_sensitive


def render_markdown(
    report: FeedbackAssessment,
    *,
    release: NormativeRelease | None = None,
    bundle: ObservationBundle | None = None,
) -> str:
    lines = [
        "# 實作回饋評估",
        "",
        f"- 評估：`{_safe_text(report.assessment_id)}`",
        f"- 規範資產：`{_safe_text(report.base.asset_id)}`",
        f"- 適用範圍：`{_safe_text(report.applicability.environment)}` / "
        f"`{_safe_text(report.applicability.endpoint_identity)}`",
        f"- 處置路徑：`{report.route.value}`",
        f"- 建議處置：`{report.route.value}`",
        f"- 未解差異：`{report.open_discrepancy_count}`",
        "",
        "## 適用範圍",
        "",
        *_scope_lines(report),
        f"- 產生者：`{_safe_text(report.producer.id)}` / `{_safe_text(report.producer.version)}`",
        f"- 執行者：`{_safe_text(report.runner.id)}` / `{_safe_text(report.runner.version)}`",
        "",
        "| 觀測項目 | 宣告路徑 | 關係 |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| `{_safe_text(item.observation_id)}` | "
        f"`{_safe_text(item.claim_identity + item.claim_path)}` | "
        f"`{item.relationship.value}` |"
        for item in report.relationships
    )
    if release is not None and bundle is not None:
        fragments = {fragment.id: fragment for fragment in release.fragments}
        observations = {item.id: item for item in bundle.observations}
        lines.extend(["", "## 審閱項目", ""])
        for relationship in report.relationships:
            observation = observations[relationship.observation_id]
            lines.extend(
                [
                    f"### {_safe_text(relationship.observation_id)}",
                    "",
                    f"- 目標：`{_safe_text(relationship.claim_identity + relationship.claim_path)}`",
                    f"- 預期值：`{_safe_json_inline(relationship.normative_value)}`",
                    f"- 觀測值：`{_safe_json_inline(relationship.observed_value)}`",
                    f"- 探針摘要：`{observation.probe_digest}`",
                    f"- 測試資料摘要：`{observation.fixture_digest}`",
                    f"- 觀測沿革：`{observation.lineage.value}`",
                    f"- 嘗試次數：`{len(observation.attempts)}`",
                    f"- 重播執行者：`{_safe_text(observation.replay.executor)}`",
                    "- 重播步驟：",
                    *(
                        f"  {index}. `{_safe_text(step)}`"
                        for index, step in enumerate(observation.replay.steps, start=1)
                    ),
                    "",
                    "嘗試紀錄：",
                    "",
                    *(
                        f"- `{_safe_text(attempt.id)}` — {attempt.outcome.value} @ "
                        f"`{attempt.observed_at.isoformat()}`"
                        for attempt in observation.attempts
                    ),
                    "",
                    "規範供應商證據：",
                    "",
                ]
            )
            for fragment_id in relationship.normative_evidence_refs:
                fragment = fragments.get(fragment_id)
                excerpt = (
                    fragment.normalized_excerpt
                    if fragment is not None and fragment.normalized_excerpt is not None
                    else "[reconstruct from the immutable evidence reference]"
                )
                if fragment is None:
                    lines.extend(
                        [
                            f"- 規範片段：`{_safe_text(fragment_id)}`",
                            f"  - 宣告：`{_safe_text(relationship.claim_identity + relationship.claim_path)}`",
                            f"<pre>{escape(_safe_text(excerpt))}</pre>",
                            "",
                        ]
                    )
                    continue
                lines.extend(
                    [
                        f"- 規範片段：`{_safe_text(fragment.id)}`",
                        f"  - 片段摘要：`{fragment.fragment_digest}`",
                        f"  - 定位資訊：`{_safe_json_inline(fragment.locator.model_dump(mode='json'))}`",
                        f"  - 宣告：`{_safe_text(relationship.claim_identity + relationship.claim_path)}`",
                        f"<pre>{escape(_safe_text(excerpt))}</pre>",
                        "",
                    ]
                )
            lines.extend(["已遮罩的實作證據：", ""])
            for item in observation.evidence:
                facts = [fact.model_dump(mode="json") for fact in item.sanitized_facts]
                lines.extend(
                    [
                        f"- 實作片段：`{_safe_text(item.fragment_id)}`",
                        f"  - 片段摘要：`{item.digest}`",
                        f"  - 媒體類型：`{item.media_type}`",
                        f"  - 位元組數：`{item.size_bytes}`",
                        f"  - 宣告：`{_safe_text(relationship.claim_identity + relationship.claim_path)}`",
                        f"  - 已遮罩事實：`{_safe_json_inline(facts)}`",
                    ]
                )
            lines.append("")
    lines.extend(
        [
            "",
            "文件來源支持與實作符合性是兩條獨立的權威軸線。",
            "本報告不會變更或發布規範契約。",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(
    report: FeedbackAssessment,
    output_dir: Path,
    *,
    release: NormativeRelease | None = None,
    bundle: ObservationBundle | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    payload = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    (output_dir / "feedback-assessment.json").write_text(payload, encoding="utf-8")
    (output_dir / "feedback-assessment.md").write_text(
        render_markdown(report, release=release, bundle=bundle), encoding="utf-8"
    )


def write_proposal_reports(
    proposals: tuple[CompatibilityAmendmentProposal, ...], output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    payload = [proposal.model_dump(mode="json") for proposal in proposals]
    (output_dir / "amendment-proposals.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# 相容性修訂提案",
        "",
        f"- 提案數量：`{len(proposals)}`",
        "- 需要人工審閱：`true`",
        "",
    ]
    for proposal in proposals:
        filename = f"{proposal.proposal_id}.json"
        (output_dir / filename).write_text(
            proposal.model_dump_json(indent=2), encoding="utf-8"
        )
        lines.extend(
            [
                f"## {proposal.proposal_id}",
                "",
                f"- 目標：`{proposal.target.claim_identity}{proposal.target.claim_path}`",
                f"- 規範值：`{_safe_json_inline(proposal.normative_value)}`",
                f"- 建議值：`{_safe_json_inline(proposal.proposed_value)}`",
                f"- 成品：`{filename}`",
                "",
            ]
        )
    lines.extend(
        [
            "提案僅供審閱，不構成權威；必須由具名且獨立的人員針對完全相同的範圍核准後才會生效。",
            "",
        ]
    )
    (output_dir / "amendment-proposals.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def write_effective_contract_report(
    contract: EffectiveContract, output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "effective-contract.json").write_text(
        contract.model_dump_json(indent=2), encoding="utf-8"
    )
    lines = [
        "# 有效契約組合",
        "",
        f"- 有效契約：`{contract.effective_contract_id}`",
        f"- 基礎資產：`{contract.base.asset_id}`",
        f"- 目標：`{contract.target.environment}` / `{contract.target.endpoint_identity}`",
        f"- 已套用修訂：`{len(contract.applied_amendment_ids)}`",
        f"- 已取代修訂：`{len(contract.superseded_amendment_ids)}`",
        f"- 已過期修訂：`{len(contract.expired_amendment_ids)}`",
        f"- 不適用修訂：`{len(contract.inapplicable_amendment_ids)}`",
        f"- 已失效修訂：`{len(contract.stale_amendment_ids)}`",
        f"- 未測試重大宣告：`{contract.untested_material_claim_count}`",
        f"- 未解矛盾：`{contract.unresolved_contradiction_count}`",
        f"- 未解差異：`{contract.open_discrepancy_count}`",
        "",
        "本次乾跑不會發布有效契約或變更規範契約。",
        "",
    ]
    (output_dir / "effective-contract.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def write_provider_erratum_handoff(
    handoff: ProviderErratumHandoff, output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "provider-erratum-handoff.json").write_text(
        handoff.model_dump_json(indent=2), encoding="utf-8"
    )
    lines = [
        "# 供應商勘誤交接",
        "",
        f"- 勘誤：`{handoff.erratum.erratum_id}`",
        f"- 成品摘要：`{handoff.verified_artifact_digest}`",
        "- 來源角色：`supplemental`",
        "- 立即變更或發布：`none`",
        "",
        "## 處理流程",
        "",
    ]
    lines.extend(
        f"{step.order}. **{step.stage}** — {step.action}"
        for step in handoff.pipeline
    )
    lines.append("")
    (output_dir / "provider-erratum-handoff.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def _json_inline(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).replace("`", "\\u0060")


def _scope_lines(report: FeedbackAssessment) -> list[str]:
    scope = report.applicability
    values = (
        ("供應商", scope.provider),
        ("產品", scope.product),
        ("API 版本", scope.api_version),
        ("環境", scope.environment),
        ("區域", scope.region),
        ("端點識別", scope.endpoint_identity),
        ("帳戶類別", scope.account_class),
        ("功能旗標", scope.feature_flags),
        ("驗證角色", scope.authentication_role),
        ("用戶端版本", scope.client_version),
        ("測試框架版本", scope.harness_version),
        ("測試資料類別", scope.test_data_class),
        ("觀測開始", scope.observed_from.isoformat()),
        ("觀測結束", scope.observed_until.isoformat()),
    )
    return [f"- {label}: `{_safe_json_inline(value)}`" for label, value in values]


def _safe_json_inline(value: object) -> str:
    return _json_inline(redact_sensitive(value))


def _safe_text(value: str) -> str:
    redacted = redact_sensitive(value)
    assert isinstance(redacted, str)
    return redacted.replace("`", "\\u0060").replace("\r", " ").replace("\n", " ")
