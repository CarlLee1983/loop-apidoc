from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer
from pydantic import TypeAdapter, ValidationError

from loop_apidoc.core.conformance import ConformanceInputError
from loop_apidoc.domain.conformance import FeedbackRoute, IdentityVersion
from loop_apidoc.feedback.errors import FeedbackInputError
from loop_apidoc.feedback.identifiers import require_safe_identifier
from loop_apidoc.feedback.loader import (
    load_amendment_proposal,
    load_applicability_envelope,
    load_compatibility_amendment,
    load_feedback_assessment,
    load_observation_bundle,
    load_provider_erratum_inputs,
)
from loop_apidoc.feedback.report import (
    write_effective_contract_report,
    write_proposal_reports,
    write_provider_erratum_handoff,
    write_reports,
)
from loop_apidoc.feedback.workflow import (
    ApproveFeedbackCommand,
    AssessFeedbackCommand,
    ComposeFeedbackCommand,
    CurrentFeedbackCommand,
    FeedbackWorkflow,
    ProposeFeedbackCommand,
    ProviderErratumCommand,
    ReviewFeedbackCommand,
    SubmitFeedbackCommand,
)
from loop_apidoc.foundry.models import FoundryInputError, FoundryPublicationError


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
        require_safe_identifier(docset, "docset id")
        require_safe_identifier(asset, "asset id")
        _require_ungoverned_output(project, output)
        result = FeedbackWorkflow().assess(
            AssessFeedbackCommand(
                project_root=project,
                docset_id=docset,
                asset_id=asset,
                bundle=load_observation_bundle(bundle),
            )
        )
        write_reports(
            result.assessment,
            output,
            release=result.release,
            bundle=result.bundle,
        )
    except (
        FeedbackInputError,
        FoundryInputError,
        FoundryPublicationError,
        ConformanceInputError,
        OSError,
    ) as exc:
        _input_error("assess", exc)
    typer.echo(
        f"assessment written to {output}; route={result.assessment.route.value}; "
        f"open_discrepancies={result.assessment.open_discrepancy_count}"
    )
    if result.assessment.open_discrepancy_count:
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
        result = FeedbackWorkflow().propose(
            ProposeFeedbackCommand(
                assessment=load_feedback_assessment(assessment),
                at=_parse_time(at, "--at"),
            )
        )
        write_proposal_reports(result.proposals, output)
    except (FeedbackInputError, ConformanceInputError, OSError, ValidationError) as exc:
        _input_error("propose", exc)
    typer.echo(f"proposals written to {output}; count={len(result.proposals)}")
    if not result.proposals:
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
        require_safe_identifier(docset, "docset id")
        result = FeedbackWorkflow().submit(
            SubmitFeedbackCommand(
                project_root=project,
                docset_id=docset,
                bundle=load_observation_bundle(bundle),
                assessment=load_feedback_assessment(assessment),
                proposal=(load_amendment_proposal(proposal) if proposal is not None else None),
            )
        )
    except (
        FeedbackInputError,
        FoundryInputError,
        FoundryPublicationError,
        ConformanceInputError,
        OSError,
        ValidationError,
    ) as exc:
        _input_error("submit", exc)
    typer.echo(f"feedback case persisted: {result.case.case_id}")


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
        require_safe_identifier(docset, "docset id")
        require_safe_identifier(case_id, "case id")
        result = FeedbackWorkflow().approve(
            ApproveFeedbackCommand(
                project_root=project,
                docset_id=docset,
                case_id=case_id,
                approver=IdentityVersion(id=approved_by, version=approver_version),
                decided_at=_parse_time(at, "--at"),
                expires_at=_parse_time(expires_at, "--expires-at"),
                rationale=rationale,
                revalidation_triggers=tuple(revalidation_trigger or ()),
                supersedes_amendment=supersedes_amendment,
            )
        )
    except (
        FeedbackInputError,
        FoundryInputError,
        FoundryPublicationError,
        ConformanceInputError,
        OSError,
        ValidationError,
    ) as exc:
        _input_error("approve", exc)
    typer.echo(
        f"effective contract approved: {result.asset.effective_asset_id}; "
        f"scope={result.asset.scope_digest}"
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
        require_safe_identifier(docset, "docset id")
        require_safe_identifier(case_id, "case id")
        if disposition not in {"rejected", "needs_evidence"}:
            raise FeedbackInputError("--disposition must be rejected or needs_evidence")
        try:
            route = FeedbackRoute(requested_route)
        except ValueError as exc:
            raise FeedbackInputError(
                "--route is not a supported feedback route"
            ) from exc
        FeedbackWorkflow().review(
            ReviewFeedbackCommand(
                project_root=project,
                docset_id=docset,
                case_id=case_id,
                reviewer=IdentityVersion(id=reviewed_by, version=reviewer_version),
                decided_at=_parse_time(at, "--at"),
                disposition=disposition,
                requested_route=route,
                rationale=rationale,
            )
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
        require_safe_identifier(docset, "docset id")
        require_safe_identifier(asset, "asset id")
        _require_ungoverned_output(project, output)
        result = FeedbackWorkflow().compose(
            ComposeFeedbackCommand(
                project_root=project,
                docset_id=docset,
                asset_id=asset,
                target=load_applicability_envelope(target),
                amendments=tuple(
                    load_compatibility_amendment(path) for path in amendment
                ),
                at=_parse_time(at, "--at"),
            )
        )
        write_effective_contract_report(result.effective, output)
    except (
        FeedbackInputError,
        FoundryInputError,
        ConformanceInputError,
        OSError,
        ValidationError,
    ) as exc:
        _input_error("compose", exc)
    typer.echo(
        f"composition written to {output}; "
        f"applied={len(result.effective.applied_amendment_ids)}"
    )
    if result.effective.open_discrepancy_count:
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
        require_safe_identifier(docset, "docset id")
        result = FeedbackWorkflow().current(
            CurrentFeedbackCommand(
                project_root=project,
                docset_id=docset,
                target=load_applicability_envelope(target),
                at=_parse_time(at, "--at"),
            )
        )
    except (FeedbackInputError, FoundryInputError, OSError, ValidationError) as exc:
        _input_error("current", exc)
    typer.echo(
        json.dumps(
            result.asset.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
        )
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
        metadata_value, digest = load_provider_erratum_inputs(metadata, artifact)
        result = FeedbackWorkflow().provider_erratum(
            ProviderErratumCommand(
                metadata=metadata_value,
                artifact_digest=digest,
            )
        )
        write_provider_erratum_handoff(result.handoff, output)
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
