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
        "# Implementation Feedback Assessment",
        "",
        f"- Assessment: `{_safe_text(report.assessment_id)}`",
        f"- Normative asset: `{_safe_text(report.base.asset_id)}`",
        f"- Applicability: `{_safe_text(report.applicability.environment)}` / "
        f"`{_safe_text(report.applicability.endpoint_identity)}`",
        f"- Route: `{report.route.value}`",
        f"- Proposed disposition: `{report.route.value}`",
        f"- Open discrepancies: `{report.open_discrepancy_count}`",
        "",
        "## Applicability scope",
        "",
        *_scope_lines(report),
        f"- Producer: `{_safe_text(report.producer.id)}` / `{_safe_text(report.producer.version)}`",
        f"- Runner: `{_safe_text(report.runner.id)}` / `{_safe_text(report.runner.version)}`",
        "",
        "| Observation | Claim path | Relationship |",
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
        lines.extend(["", "## Review subjects", ""])
        for relationship in report.relationships:
            observation = observations[relationship.observation_id]
            lines.extend(
                [
                    f"### {_safe_text(relationship.observation_id)}",
                    "",
                    f"- Target: `{_safe_text(relationship.claim_identity + relationship.claim_path)}`",
                    f"- Expected: `{_safe_json_inline(relationship.normative_value)}`",
                    f"- Observed: `{_safe_json_inline(relationship.observed_value)}`",
                    f"- Probe digest: `{observation.probe_digest}`",
                    f"- Fixture digest: `{observation.fixture_digest}`",
                    f"- Observation lineage: `{observation.lineage.value}`",
                    f"- Attempts: `{len(observation.attempts)}`",
                    f"- Replay executor: `{_safe_text(observation.replay.executor)}`",
                    "- Replay steps:",
                    *(
                        f"  {index}. `{_safe_text(step)}`"
                        for index, step in enumerate(observation.replay.steps, start=1)
                    ),
                    "",
                    "Attempts:",
                    "",
                    *(
                        f"- `{_safe_text(attempt.id)}` — {attempt.outcome.value} @ "
                        f"`{attempt.observed_at.isoformat()}`"
                        for attempt in observation.attempts
                    ),
                    "",
                    "Normative supplier evidence:",
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
                            f"- Normative fragment: `{_safe_text(fragment_id)}`",
                            f"  - Claim: `{_safe_text(relationship.claim_identity + relationship.claim_path)}`",
                            f"<pre>{escape(_safe_text(excerpt))}</pre>",
                            "",
                        ]
                    )
                    continue
                lines.extend(
                    [
                        f"- Normative fragment: `{_safe_text(fragment.id)}`",
                        f"  - Fragment digest: `{fragment.fragment_digest}`",
                        f"  - Locator: `{_safe_json_inline(fragment.locator.model_dump(mode='json'))}`",
                        f"  - Claim: `{_safe_text(relationship.claim_identity + relationship.claim_path)}`",
                        f"<pre>{escape(_safe_text(excerpt))}</pre>",
                        "",
                    ]
                )
            lines.extend(["Sanitized implementation evidence:", ""])
            for item in observation.evidence:
                facts = [fact.model_dump(mode="json") for fact in item.sanitized_facts]
                lines.extend(
                    [
                        f"- Implementation fragment: `{_safe_text(item.fragment_id)}`",
                        f"  - Fragment digest: `{item.digest}`",
                        f"  - Media type: `{item.media_type}`",
                        f"  - Size bytes: `{item.size_bytes}`",
                        f"  - Claim: `{_safe_text(relationship.claim_identity + relationship.claim_path)}`",
                        f"  - Sanitized facts: `{_safe_json_inline(facts)}`",
                    ]
                )
            lines.append("")
    lines.extend(
        [
            "",
            "Documentary source support and implementation conformance are separate authority axes.",
            "This report does not mutate or publish the Normative Contract.",
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
        "# Compatibility Amendment Proposals",
        "",
        f"- Proposal count: `{len(proposals)}`",
        "- Human review required: `true`",
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
                f"- Target: `{proposal.target.claim_identity}{proposal.target.claim_path}`",
                f"- Normative: `{_json_inline(proposal.normative_value)}`",
                f"- Proposed: `{_json_inline(proposal.proposed_value)}`",
                f"- Artifact: `{filename}`",
                "",
            ]
        )
    lines.extend(
        [
            "A proposal is a review subject, not authority. It has no effect until an independent named human approves it for the exact scope.",
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
        "# Effective Contract Composition",
        "",
        f"- Effective contract: `{contract.effective_contract_id}`",
        f"- Base asset: `{contract.base.asset_id}`",
        f"- Target: `{contract.target.environment}` / `{contract.target.endpoint_identity}`",
        f"- Applied amendments: `{len(contract.applied_amendment_ids)}`",
        f"- Superseded amendments: `{len(contract.superseded_amendment_ids)}`",
        f"- Expired amendments: `{len(contract.expired_amendment_ids)}`",
        f"- Inapplicable amendments: `{len(contract.inapplicable_amendment_ids)}`",
        f"- Stale amendments: `{len(contract.stale_amendment_ids)}`",
        f"- Untested material claims: `{contract.untested_material_claim_count}`",
        f"- Unresolved contradictions: `{contract.unresolved_contradiction_count}`",
        f"- Open discrepancies: `{contract.open_discrepancy_count}`",
        "",
        "This dry-run does not publish an Effective Contract or change the Normative Contract.",
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
        "# Provider Erratum Handoff",
        "",
        f"- Erratum: `{handoff.erratum.erratum_id}`",
        f"- Artifact digest: `{handoff.verified_artifact_digest}`",
        "- Source role: `supplemental`",
        "- Immediate mutation or publication: `none`",
        "",
        "## Ordered pipeline",
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
        ("Provider", scope.provider),
        ("Product", scope.product),
        ("API version", scope.api_version),
        ("Environment", scope.environment),
        ("Region", scope.region),
        ("Endpoint identity", scope.endpoint_identity),
        ("Account class", scope.account_class),
        ("Feature flags", scope.feature_flags),
        ("Authentication role", scope.authentication_role),
        ("Client version", scope.client_version),
        ("Harness version", scope.harness_version),
        ("Test data class", scope.test_data_class),
        ("Observed from", scope.observed_from.isoformat()),
        ("Observed until", scope.observed_until.isoformat()),
    )
    return [f"- {label}: `{_safe_json_inline(value)}`" for label, value in values]


def _safe_json_inline(value: object) -> str:
    return _json_inline(redact_sensitive(value))


def _safe_text(value: str) -> str:
    redacted = redact_sensitive(value)
    assert isinstance(redacted, str)
    return redacted.replace("`", "\\u0060").replace("\r", " ").replace("\n", " ")
