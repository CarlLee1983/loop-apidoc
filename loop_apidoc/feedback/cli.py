from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer
from pydantic import TypeAdapter, ValidationError

from loop_apidoc.core.conformance import (
    ConformanceInputError,
    ContractConformance,
    canonical_digest,
)
from loop_apidoc.domain.conformance import (
    AmendmentApproval,
    CompatibilityAmendment,
    FeedbackRoute,
    IdentityVersion,
)
from loop_apidoc.feedback.erratum import (
    build_provider_erratum_handoff,
)
from loop_apidoc.feedback.loader import (
    FeedbackInputError,
    load_amendment_proposal,
    load_applicability_envelope,
    load_approved_contract,
    load_compatibility_amendment,
    load_current_scope_amendments,
    load_feedback_assessment,
    load_feedback_review_decision,
    load_observation_bundle,
    load_provider_erratum_inputs,
)
from loop_apidoc.feedback.report import (
    write_effective_contract_report,
    write_proposal_reports,
    write_provider_erratum_handoff,
    write_reports,
)
from loop_apidoc.foundry import feedback as foundry_feedback
from loop_apidoc.foundry import paths, query, store
from loop_apidoc.foundry.models import FeedbackReviewDecision, FoundryInputError


feedback_app = typer.Typer(
    help="Govern implementation observations separately from normative source support.",
    no_args_is_help=True,
)


@feedback_app.command("assess")
def assess_feedback(
    project: Path = typer.Option(..., "--project", exists=True, file_okay=False),
    docset: str = typer.Option(..., "--docset"),
    asset: str = typer.Option(..., "--asset"),
    bundle: Path = typer.Option(..., "--bundle", exists=True, readable=True),
    output: Path = typer.Option(..., "--output"),
) -> None:
    """Compare passive implementation evidence with an approved Normative Contract."""
    try:
        _require_safe_identifier(docset, "docset id")
        _require_safe_identifier(asset, "asset id")
        _require_ungoverned_output(project, output)
        base_asset, release = load_approved_contract(project, docset, asset)
        observation_bundle = load_observation_bundle(bundle)
        if observation_bundle.base.asset_id != base_asset.asset_id:
            raise FeedbackInputError(
                "observation bundle asset does not match the requested base release"
            )
        docset_record = store.load_docset(project, docset)
        report = ContractConformance().assess(
            release,
            observation_bundle,
            provider=docset_record.provider,
            product=docset_record.product,
        )
        write_reports(
            report,
            output,
            release=release,
            bundle=observation_bundle,
        )
    except (
        FeedbackInputError,
        FoundryInputError,
        ConformanceInputError,
        OSError,
    ) as exc:
        typer.echo(f"feedback assess error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"assessment written to {output}; route={report.route.value}; "
        f"open_discrepancies={report.open_discrepancy_count}"
    )
    if report.open_discrepancy_count:
        raise typer.Exit(code=1)


@feedback_app.command("propose")
def propose_feedback(
    assessment: Path = typer.Option(..., "--assessment", exists=True, readable=True),
    at: str = typer.Option(..., "--at"),
    output: Path = typer.Option(..., "--output"),
) -> None:
    """Create deterministic human-review subjects from a validated assessment."""
    try:
        _require_not_foundry_path(output)
        report = load_feedback_assessment(assessment)
        proposals = ContractConformance().propose(report, now=_parse_time(at, "--at"))
        write_proposal_reports(proposals, output)
    except (FeedbackInputError, ConformanceInputError, OSError, ValidationError) as exc:
        _input_error("propose", exc)
    typer.echo(f"proposals written to {output}; count={len(proposals)}")
    if not proposals:
        raise typer.Exit(code=1)


@feedback_app.command("submit")
def submit_feedback(
    project: Path = typer.Option(..., "--project", exists=True, file_okay=False),
    docset: str = typer.Option(..., "--docset"),
    bundle: Path = typer.Option(..., "--bundle", exists=True, readable=True),
    assessment: Path = typer.Option(..., "--assessment", exists=True, readable=True),
    proposal: Path | None = typer.Option(None, "--proposal", exists=True, readable=True),
) -> None:
    """Persist one immutable, digest-bound feedback case without changing current."""
    try:
        _require_safe_identifier(docset, "docset id")
        observation_bundle = load_observation_bundle(bundle)
        assessment_report = load_feedback_assessment(assessment)
        _, release = load_approved_contract(
            project, docset, observation_bundle.base.asset_id
        )
        docset_record = store.load_docset(project, docset)
        deterministic_assessment = ContractConformance().assess(
            release,
            observation_bundle,
            provider=docset_record.provider,
            product=docset_record.product,
        )
        if assessment_report != deterministic_assessment:
            raise FeedbackInputError(
                "submitted assessment does not match deterministic reassessment"
            )
        amendment_proposal = (
            load_amendment_proposal(proposal) if proposal is not None else None
        )
        if amendment_proposal is not None:
            deterministic_proposals = ContractConformance().propose(
                assessment_report, now=amendment_proposal.created_at
            )
            if amendment_proposal not in deterministic_proposals:
                raise FeedbackInputError(
                    "submitted amendment does not match deterministic proposal"
                )
        case = foundry_feedback.persist_feedback_case(
            project,
            docset,
            observation_bundle,
            assessment_report,
            amendment_proposal,
        )
    except (
        FeedbackInputError,
        FoundryInputError,
        ConformanceInputError,
        OSError,
        ValidationError,
    ) as exc:
        _input_error("submit", exc)
    typer.echo(f"feedback case persisted: {case.case_id}")


@feedback_app.command("approve")
def approve_feedback(
    project: Path = typer.Option(..., "--project", exists=True, file_okay=False),
    docset: str = typer.Option(..., "--docset"),
    case_id: str = typer.Option(..., "--case"),
    approved_by: str = typer.Option(..., "--approved-by"),
    approver_version: str = typer.Option(..., "--approver-version"),
    at: str = typer.Option(..., "--at"),
    expires_at: str = typer.Option(..., "--expires-at"),
    rationale: str | None = typer.Option(None, "--rationale"),
    revalidation_trigger: list[str] | None = typer.Option(
        None, "--revalidation-trigger"
    ),
    supersedes_amendment: str | None = typer.Option(
        None, "--supersedes-amendment"
    ),
) -> None:
    """Record an independent human approval and publish one exact-scope view."""
    try:
        _require_safe_identifier(docset, "docset id")
        _require_safe_identifier(case_id, "case id")
        decided_at = _parse_time(at, "--at")
        expiry = _parse_time(expires_at, "--expires-at")
        case = store.load_feedback_case(project, docset, case_id)
        case_dir = paths.feedback_case_dir(project, docset, case_id)
        bundle = load_observation_bundle(case_dir / "observation-bundle.json")
        assessment = load_feedback_assessment(case_dir / "feedback-assessment.json")
        proposal = load_amendment_proposal(case_dir / "amendment-proposal.json")
        if case.proposal_digest is None:
            raise FeedbackInputError("feedback case has no amendment proposal")
        _, release = load_approved_contract(project, docset, case.base_asset_id)
        docset_record = store.load_docset(project, docset)
        deterministic_assessment = ContractConformance().assess(
            release,
            bundle,
            provider=docset_record.provider,
            product=docset_record.product,
        )
        if assessment != deterministic_assessment:
            raise FeedbackInputError(
                "persisted assessment does not match deterministic reassessment"
            )
        if proposal not in ContractConformance().propose(
            assessment, now=proposal.created_at
        ):
            raise FeedbackInputError(
                "persisted amendment does not match deterministic proposal"
            )
        actor = IdentityVersion(id=approved_by, version=approver_version)
        decision = FeedbackReviewDecision(
            case_id=case.case_id,
            disposition="approved",
            approved_by=actor,
            decided_at=decided_at,
            expires_at=expiry,
            base_asset_id=case.base_asset_id,
            base_contract_digest=case.base_contract_digest,
            bundle_id=case.bundle_id,
            bundle_digest=case.bundle_digest,
            redaction_policy_version=case.redaction_policy_version,
            policy_version=case.policy_version,
            assessment_id=case.assessment_id,
            assessment_digest=case.assessment_digest,
            proposal_id=proposal.proposal_id,
            proposal_digest=case.proposal_digest,
            rationale=rationale,
        )
        approval_id = "approval-" + canonical_digest(
            {
                "case_id": case.case_id,
                "proposal_digest": case.proposal_digest,
                "approved_by": actor,
                "approved_at": decided_at,
            }
        )[:20]
        revalidation_triggers = tuple(sorted(set(revalidation_trigger or ())))
        amendment_id = "amendment-" + canonical_digest(
            {
                "approval_id": approval_id,
                "proposal_digest": case.proposal_digest,
                "expires_at": expiry,
                "revalidation_triggers": revalidation_triggers,
                "supersedes": supersedes_amendment,
            }
        )[:20]
        amendment = CompatibilityAmendment(
            amendment_id=amendment_id,
            proposal=proposal,
            approval=AmendmentApproval(
                approval_id=approval_id,
                approved_by=actor,
                approved_at=decided_at,
                base_asset_id=case.base_asset_id,
                assessment_id=case.assessment_id,
                observation_bundle_id=case.bundle_id,
                proposal_digest=case.proposal_digest,
                assessment_digest=case.assessment_digest,
                observation_bundle_digest=case.bundle_digest,
                base_contract_digest=case.base_contract_digest,
                policy_version=case.policy_version,
                redaction_policy_version=case.redaction_policy_version,
            ),
            expires_at=expiry,
            revalidation_triggers=revalidation_triggers,
            supersedes=supersedes_amendment,
        )
        prior_amendments = load_current_scope_amendments(
            project, docset, proposal.scope
        )
        prior_by_id = {
            prior.amendment_id: prior for prior in prior_amendments
        }
        if amendment.amendment_id in prior_by_id:
            if prior_by_id[amendment.amendment_id] != amendment:
                raise FeedbackInputError(
                    "current scope contains a different amendment with the same id"
                )
            composition_amendments = prior_amendments
        else:
            composition_amendments = (*prior_amendments, amendment)
        effective = ContractConformance().compose(
            release,
            composition_amendments,
            target=proposal.scope,
            now=decided_at,
        )
        # Validate all pure artifacts before the first governed write.
        if assessment.producer != bundle.producer or assessment.runner != bundle.runner:
            raise FeedbackInputError("feedback assessment actor binding is stale")
        decision_path = case_dir / "review" / "decision.json"
        if decision_path.exists():
            if load_feedback_review_decision(decision_path) != decision:
                raise FeedbackInputError(
                    "feedback review already exists with a different decision"
                )
        else:
            foundry_feedback.record_feedback_review(
                project, docset, case_id, decision
            )
        asset = foundry_feedback.approve_feedback_case(
            project,
            docset,
            case_id,
            amendment,
            effective,
            release=release,
            composition_amendments=composition_amendments,
        )
    except (
        FeedbackInputError,
        FoundryInputError,
        ConformanceInputError,
        OSError,
        ValidationError,
    ) as exc:
        _input_error("approve", exc)
    typer.echo(
        f"effective contract approved: {asset.effective_asset_id}; "
        f"scope={asset.scope_digest}"
    )


@feedback_app.command("review")
def review_feedback(
    project: Path = typer.Option(..., "--project", exists=True, file_okay=False),
    docset: str = typer.Option(..., "--docset"),
    case_id: str = typer.Option(..., "--case"),
    reviewed_by: str = typer.Option(..., "--reviewed-by"),
    reviewer_version: str = typer.Option(..., "--reviewer-version"),
    at: str = typer.Option(..., "--at"),
    disposition: str = typer.Option(..., "--disposition"),
    requested_route: str = typer.Option(..., "--route"),
    rationale: str | None = typer.Option(None, "--rationale"),
) -> None:
    """Record a write-once non-approval review and requested corrective route."""
    try:
        _require_safe_identifier(docset, "docset id")
        _require_safe_identifier(case_id, "case id")
        if disposition not in {"rejected", "needs_evidence"}:
            raise FeedbackInputError(
                "--disposition must be rejected or needs_evidence"
            )
        try:
            route = FeedbackRoute(requested_route)
        except ValueError as exc:
            raise FeedbackInputError("--route is not a supported feedback route") from exc
        case = store.load_feedback_case(project, docset, case_id)
        case_dir = paths.feedback_case_dir(project, docset, case_id)
        bundle = load_observation_bundle(case_dir / "observation-bundle.json")
        assessment = load_feedback_assessment(case_dir / "feedback-assessment.json")
        proposal = (
            load_amendment_proposal(case_dir / "amendment-proposal.json")
            if case.proposal_digest is not None
            else None
        )
        _, release = load_approved_contract(project, docset, case.base_asset_id)
        docset_record = store.load_docset(project, docset)
        deterministic = ContractConformance().assess(
            release,
            bundle,
            provider=docset_record.provider,
            product=docset_record.product,
        )
        if assessment != deterministic:
            raise FeedbackInputError(
                "persisted assessment does not match deterministic reassessment"
            )
        decision = FeedbackReviewDecision(
            case_id=case.case_id,
            disposition=disposition,
            approved_by=IdentityVersion(id=reviewed_by, version=reviewer_version),
            decided_at=_parse_time(at, "--at"),
            base_asset_id=case.base_asset_id,
            base_contract_digest=case.base_contract_digest,
            bundle_id=case.bundle_id,
            bundle_digest=case.bundle_digest,
            redaction_policy_version=case.redaction_policy_version,
            policy_version=case.policy_version,
            assessment_id=case.assessment_id,
            assessment_digest=case.assessment_digest,
            proposal_id=proposal.proposal_id if proposal is not None else None,
            proposal_digest=case.proposal_digest,
            requested_route=route,
            rationale=rationale,
        )
        foundry_feedback.record_feedback_review(
            project, docset, case_id, decision
        )
    except (
        FeedbackInputError,
        FoundryInputError,
        ConformanceInputError,
        OSError,
        ValidationError,
    ) as exc:
        _input_error("review", exc)
    typer.echo(
        f"feedback review recorded: {case_id}; disposition={disposition}; "
        f"route={route.value}"
    )


@feedback_app.command("compose")
def compose_feedback(
    project: Path = typer.Option(..., "--project", exists=True, file_okay=False),
    docset: str = typer.Option(..., "--docset"),
    asset: str = typer.Option(..., "--asset"),
    target: Path = typer.Option(..., "--target", exists=True, readable=True),
    amendment: list[Path] = typer.Option(..., "--amendment", exists=True, readable=True),
    at: str = typer.Option(..., "--at"),
    output: Path = typer.Option(..., "--output"),
) -> None:
    """Dry-run pure composition for one exact target scope."""
    try:
        _require_safe_identifier(docset, "docset id")
        _require_safe_identifier(asset, "asset id")
        _require_ungoverned_output(project, output)
        _, release = load_approved_contract(project, docset, asset)
        envelope = load_applicability_envelope(target)
        amendments = tuple(load_compatibility_amendment(path) for path in amendment)
        effective = ContractConformance().compose(
            release, amendments, target=envelope, now=_parse_time(at, "--at")
        )
        write_effective_contract_report(effective, output)
    except (
        FeedbackInputError,
        FoundryInputError,
        ConformanceInputError,
        OSError,
        ValidationError,
    ) as exc:
        _input_error("compose", exc)
    typer.echo(
        f"composition written to {output}; applied={len(effective.applied_amendment_ids)}"
    )
    if effective.open_discrepancy_count:
        raise typer.Exit(code=1)


@feedback_app.command("current")
def current_feedback(
    project: Path = typer.Option(..., "--project", exists=True, file_okay=False),
    docset: str = typer.Option(..., "--docset"),
    target: Path = typer.Option(..., "--target", exists=True, readable=True),
    at: str = typer.Option(..., "--at"),
) -> None:
    """Resolve the current Effective Contract only for an exact target scope."""
    try:
        _require_safe_identifier(docset, "docset id")
        envelope = load_applicability_envelope(target)
        asset = query.load_current_effective_asset(
            project, docset, envelope, now=_parse_time(at, "--at")
        )
    except (FeedbackInputError, FoundryInputError, OSError, ValidationError) as exc:
        _input_error("current", exc)
    typer.echo(
        json.dumps(asset.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    )


@feedback_app.command("provider-erratum")
def provider_erratum(
    metadata: Path = typer.Option(..., "--metadata", exists=True, readable=True),
    artifact: Path = typer.Option(..., "--artifact", exists=True, readable=True),
    output: Path = typer.Option(..., "--output"),
) -> None:
    """Verify a local formal erratum and emit a non-mutating source handoff."""
    try:
        _require_not_foundry_path(output)
        erratum, digest = load_provider_erratum_inputs(metadata, artifact)
        handoff = build_provider_erratum_handoff(erratum, digest)
        write_provider_erratum_handoff(handoff, output)
    except (FeedbackInputError, OSError, ValidationError) as exc:
        _input_error("provider-erratum", exc)
    typer.echo(f"provider erratum handoff written to {output}")


def _require_ungoverned_output(project: Path, output: Path) -> None:
    governed_root = (project / ".foundry").resolve()
    resolved_output = output.resolve()
    if resolved_output == governed_root or resolved_output.is_relative_to(governed_root):
        raise FeedbackInputError(
            "passive assessment output must remain outside .foundry governed state"
        )


def _require_not_foundry_path(output: Path) -> None:
    if ".foundry" in output.resolve().parts:
        raise FeedbackInputError("feedback report output must remain outside .foundry")


def _require_safe_identifier(value: str, label: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise FeedbackInputError(f"unsafe {label}")


def _input_error(command: str, exc: Exception) -> None:
    typer.echo(f"feedback {command} error: {exc}", err=True)
    raise typer.Exit(code=2) from exc


def _parse_time(value: str, option: str) -> datetime:
    try:
        parsed = TypeAdapter(datetime).validate_python(value)
    except ValidationError as exc:
        raise FeedbackInputError(f"{option} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FeedbackInputError(f"{option} must include a timezone")
    return parsed
