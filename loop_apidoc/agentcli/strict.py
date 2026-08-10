"""Blocking Core adapter for the legacy assembly pipeline.

The legacy extractor remains an adapter: this module never approves, publishes,
or changes Foundry.  It materializes a Core candidate only after the legacy
validation gate has passed, preserving exact evidence relationships for a
later, explicit human governance decision.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from loop_apidoc.core.models import PolicyProfile, StrictExecutionSummary
from loop_apidoc.core.verification import verify_claim_support
from loop_apidoc.domain.claim_paths import material_claim_paths
from loop_apidoc.domain.evidence import SupportRelationshipType
from loop_apidoc.domain.identity import canonical_claim_identity
from loop_apidoc.domain.models import ClaimStatus
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.claim_projection import iter_plan_claim_projections
from loop_apidoc.plan.models import NormalizationPlan, PlanItemStatus
from loop_apidoc.run.models import RunStatus
from loop_apidoc.shadow.models import ShadowArtifacts
from loop_apidoc.shadow.runner import ShadowExecutionFailure, execute_shadow
from loop_apidoc.source_facts.models import FactIndex
from loop_apidoc.validate.models import ValidationReport


STRICT_RUNTIME_IDENTITY = "loop-apidoc-legacy-plan-strict"
STRICT_RUNTIME_VERSION = "1"
_SUPPORT_TYPES = frozenset(
    {
        SupportRelationshipType.EXPLICIT_SUPPORT,
        SupportRelationshipType.DERIVED_SUPPORT,
    }
)


def run_strict_core_safely(
    *,
    manifest: Manifest,
    plan: NormalizationPlan,
    facts: FactIndex,
    sources_root: Path,
    legacy_report: ValidationReport,
    generated_at: datetime,
    run_dir: Path,
) -> StrictExecutionSummary:
    """Build one reviewable Core candidate without any approval side effect."""
    core_dir = run_dir / "core"
    try:
        artifacts = execute_shadow(
            manifest=manifest,
            plan=plan,
            facts=facts,
            sources_root=sources_root,
            legacy_report=legacy_report,
            legacy_status=RunStatus.PASSED,
            generated_at=generated_at,
            policy_profile=PolicyProfile(
                name="strict",
                human_review_on_warnings=True,
                allow_waivers=False,
            ),
            runtime_identity=STRICT_RUNTIME_IDENTITY,
            runtime_version=STRICT_RUNTIME_VERSION,
        )
        findings = _grounding_findings(plan, artifacts)
        if findings:
            return _record_grounding_rejection(core_dir, artifacts, findings)
        return _write_strict_artifacts(artifacts, core_dir)
    except ShadowExecutionFailure as failure:
        return _record_error(core_dir, failure.stage.value)
    except Exception:
        return _record_error(core_dir, "service")


def write_strict_blocked_marker(
    *,
    run_dir: Path,
    legacy_status: RunStatus,
) -> StrictExecutionSummary:
    """Persist strict intent when legacy validation blocks Core execution.

    Foundry must not mistake this run for a legacy-only candidate merely because
    Core did not start.
    """
    core_dir = run_dir / "core"
    try:
        _replace_core_directory(
            core_dir,
            (("execution.json", _blocked_execution_payload(legacy_status)),),
        )
    except Exception:
        return _record_error(core_dir, "legacy-validation")
    return StrictExecutionSummary(
        status="blocked",
        core_dir=str(core_dir),
        message="legacy validation must pass before strict Core execution",
    )


def _write_strict_artifacts(
    artifacts: ShadowArtifacts,
    core_dir: Path,
) -> StrictExecutionSummary:
    if artifacts.release is None:
        return _record_error(core_dir, "validation")
    try:
        payloads: tuple[tuple[str, Any], ...] = (
            ("execution.json", _execution_payload(artifacts, candidate_eligible=True)),
            ("source-set.json", artifacts.source_set),
            ("evidence.json", artifacts.evidence),
            ("runtime-result.json", artifacts.runtime_result),
            ("claims.json", artifacts.claims),
            ("relationships.json", artifacts.relationships),
            ("contract.json", artifacts.contract),
            ("decision.json", artifacts.decision),
            ("workflow.json", artifacts.workflow),
            ("events.json", artifacts.events),
            ("release.json", artifacts.release),
        )
        _replace_core_directory(
            core_dir,
            payloads,
            projections=artifacts.projections,
        )
    except Exception:
        return _record_error(core_dir, "report")
    return StrictExecutionSummary(
        status="ok",
        core_dir=str(core_dir),
        candidate_path=str(core_dir / "release.json"),
        decision_verdict=artifacts.decision.verdict,
    )


def _grounding_findings(
    plan: NormalizationPlan,
    artifacts: ShadowArtifacts,
) -> tuple[dict[str, Any], ...]:
    """Require every legacy-supported plan item to prove its own exact paths.

    Claim reconciliation intentionally merges equal claims. Strict mode cannot
    let an exactly-grounded duplicate hide a separate, whole-document legacy
    citation, so this check operates on the individual runtime proposal tagged
    with its plan location as well as on the reconciled claim status.
    """
    proposals_by_location = {
        proposal.runtime_observation: proposal
        for proposal in artifacts.runtime_result.claim_proposals
        if proposal.runtime_observation is not None
    }
    claims_by_identity = {
        claim.canonical_identity: claim for claim in artifacts.claims
    }
    findings: list[dict[str, Any]] = []
    supported_entries = [
        projection
        for projection in iter_plan_claim_projections(plan)
        if projection.entry.status is PlanItemStatus.SUPPORTED
    ]
    for projection in supported_entries:
        identity = canonical_claim_identity(
            projection.claim_kind, projection.subject, "definition"
        )
        proposal = proposals_by_location.get(projection.plan_location)
        claim = claims_by_identity.get(identity)
        missing_paths: list[str] = []
        if proposal is None:
            missing_paths.append("<proposal>")
        else:
            relationships = verify_claim_support(proposal, artifacts.evidence)
            supported_paths = {
                relationship.claim_path
                for relationship in relationships
                if relationship.relationship in _SUPPORT_TYPES
            }
            missing_paths.extend(
                path
                for path in material_claim_paths(proposal.claim_kind, proposal.value)
                if path not in supported_paths
            )
        if claim is None or claim.status is not ClaimStatus.SUPPORTED:
            missing_paths.append("<reconciled-claim>")
        if missing_paths:
            findings.append(
                {
                    "plan_location": projection.plan_location,
                    "claim_identity": identity,
                    "claim_status": claim.status.value if claim is not None else None,
                    "uncovered_paths": sorted(set(missing_paths)),
                }
            )

    if not findings and not any(
        claim.status is ClaimStatus.SUPPORTED for claim in artifacts.claims
    ):
        findings.append(
            {
                "code": "CORE_RELEASE_HAS_NO_SUPPORTED_CLAIMS",
                "plan_location": None,
                "claim_identity": None,
                "claim_status": None,
                "uncovered_paths": (),
            }
        )
    return tuple(findings)


def _record_grounding_rejection(
    core_dir: Path,
    artifacts: ShadowArtifacts,
    findings: tuple[dict[str, Any], ...],
) -> StrictExecutionSummary:
    try:
        code = findings[0].get("code", "LEGACY_SUPPORTED_CLAIM_NOT_EXACTLY_GROUNDED")
        _replace_core_directory(
            core_dir,
            (
                ("grounding-report.json", {
                "status": "rejected",
                "code": code,
                "findings": findings,
                "message": "strict Core requires exact evidence for every legacy-supported claim",
                }),
                ("execution.json", _execution_payload(artifacts, candidate_eligible=False)),
            ),
        )
    except Exception:
        return _record_error(core_dir, "grounding-report")
    return StrictExecutionSummary(
        status="rejected",
        core_dir=str(core_dir),
        error_path=str(core_dir / "grounding-report.json"),
        message="strict Core rejected ungrounded legacy-supported claims",
    )


def _execution_payload(
    artifacts: ShadowArtifacts,
    *,
    candidate_eligible: bool,
) -> dict[str, Any]:
    return {
        "mode": "strict",
        "blocking": True,
        "legacy_status": "passed",
        "core_verdict": artifacts.decision.verdict.value,
        "exact_supported_claims": sum(
            claim.status is ClaimStatus.SUPPORTED for claim in artifacts.claims
        ),
        "candidate_eligible": candidate_eligible,
        "approval_requests": artifacts.approval_requests,
        "artifact_publications": artifacts.artifact_publications,
    }


def _record_error(core_dir: Path, stage: str) -> StrictExecutionSummary:
    error_path = core_dir / "error.json"
    try:
        _replace_core_directory(
            core_dir,
            (
                ("execution.json", _blocked_execution_payload(RunStatus.BLOCKED)),
                ("error.json", {
                "status": "error",
                "stage": stage,
                "message": "strict Core candidate could not be materialized",
                }),
            ),
        )
        saved = str(error_path)
    except Exception:
        saved = None
    return StrictExecutionSummary(
        status="error",
        core_dir=str(core_dir),
        error_path=saved,
        message="strict Core candidate could not be materialized",
    )


def _blocked_execution_payload(legacy_status: RunStatus) -> dict[str, Any]:
    return {
        "mode": "strict",
        "blocking": True,
        "legacy_status": legacy_status.value,
        "core_verdict": None,
        "exact_supported_claims": 0,
        "candidate_eligible": False,
        "approval_requests": 0,
        "artifact_publications": 0,
    }


def _replace_core_directory(
    core_dir: Path,
    payloads: tuple[tuple[str, Any], ...],
    *,
    projections=(),
) -> None:
    core_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{core_dir.name}-", dir=core_dir.parent))
    try:
        for filename, payload in payloads:
            _write_json(staging_dir / filename, payload)
        if projections:
            projection_dir = staging_dir / "projections"
            projection_dir.mkdir()
            for projection in projections:
                _write_json(projection_dir / f"{projection.name}.json", projection.payload)
        staging_dir.replace(core_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_json_value(payload), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _json_value(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, tuple | list):
        return [_json_value(item) for item in payload]
    if isinstance(payload, dict):
        return {key: _json_value(value) for key, value in payload.items()}
    return payload
