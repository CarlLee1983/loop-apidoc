"""Fail-closed eligibility checks for persisted strict Core artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from loop_apidoc.core.governance import contract_digest, release_id_for_contract
from loop_apidoc.core.models import (
    ClaimEvidenceRelationship,
    ContractRelease,
    GroundedClaim,
    ReleaseStatus,
    ValidationDecision,
    ValidationVerdict,
)
from loop_apidoc.core.verification import validate_evidence_bundle
from loop_apidoc.domain.builder import ContractClaimInput, build_grounded_contract
from loop_apidoc.domain.evidence import EvidenceBundle
from loop_apidoc.domain.models import ClaimStatus, GroundedApiContract


class StrictCoreExecutionError(ValueError):
    """A run declares strict mode but is not eligible for Foundry promotion."""


def require_eligible_strict_candidate(run_dir: Path) -> ContractRelease | None:
    """Validate strict Core promotion invariants when the run declares strict mode.

    Legacy and shadow runs predate ``core/execution.json`` and retain their
    established Foundry path. Once a run carries that artifact, no failing or
    partial strict execution can be imported or approved, including through
    ``--allow-failing``.
    """
    declared_mode = _declared_architecture_mode(run_dir)
    execution_path = run_dir / "core" / "execution.json"
    if not execution_path.exists():
        if declared_mode == "strict" or (run_dir / "core" / "release.json").exists():
            raise StrictCoreExecutionError(
                "strict Core execution marker is missing"
            )
        return None
    if declared_mode is None:
        raise StrictCoreExecutionError(
            "strict Core execution requires a strict run descriptor"
        )
    if declared_mode != "strict":
        raise StrictCoreExecutionError(
            "strict Core execution is present for a non-strict run"
        )
    try:
        payload = json.loads(execution_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StrictCoreExecutionError(
            "strict Core execution artifact is unreadable"
        ) from exc
    if not isinstance(payload, dict):
        raise StrictCoreExecutionError("strict Core execution artifact is invalid")

    required = {
        "mode": "strict",
        "blocking": True,
        "legacy_status": "passed",
        "candidate_eligible": True,
        "approval_requests": 0,
        "artifact_publications": 0,
    }
    for field, expected in required.items():
        if payload.get(field) != expected:
            raise StrictCoreExecutionError(
                f"strict Core execution is not eligible: {field}"
            )
    if payload.get("core_verdict") not in {
        ValidationVerdict.ACCEPT.value,
        ValidationVerdict.REVIEW.value,
    }:
        raise StrictCoreExecutionError(
            "strict Core execution is not eligible: core_verdict"
        )
    supported = payload.get("exact_supported_claims")
    if not isinstance(supported, int) or isinstance(supported, bool) or supported < 1:
        raise StrictCoreExecutionError(
            "strict Core execution is not eligible: exact_supported_claims"
        )

    core_dir = run_dir / "core"
    release_path = core_dir / "release.json"
    try:
        release = ContractRelease.model_validate_json(
            release_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise StrictCoreExecutionError(
            "strict Core execution is missing a valid candidate release"
        ) from exc
    if release.status is not ReleaseStatus.CANDIDATE:
        raise StrictCoreExecutionError(
            "strict Core execution release is not a candidate"
        )
    if release.validation.policy_profile != "strict":
        raise StrictCoreExecutionError(
            "strict Core execution release has the wrong policy profile"
        )
    if release.validation.verdict.value != payload["core_verdict"]:
        raise StrictCoreExecutionError(
            "strict Core execution release verdict does not match execution"
        )
    _verify_core_candidate_artifacts(
        core_dir=core_dir,
        release=release,
        execution=payload,
    )
    return release


def _declared_architecture_mode(run_dir: Path) -> str | None:
    run_path = run_dir / "run.json"
    if not run_path.exists():
        return None
    try:
        payload = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StrictCoreExecutionError("run descriptor is unreadable") from exc
    if not isinstance(payload, dict):
        raise StrictCoreExecutionError("run descriptor is invalid")
    mode = payload.get("architecture_mode")
    if mode is None:
        return None
    if mode not in {"legacy", "shadow", "strict"}:
        raise StrictCoreExecutionError("run descriptor has an invalid architecture mode")
    return mode


def _verify_core_candidate_artifacts(
    *,
    core_dir: Path,
    release: ContractRelease,
    execution: dict,
) -> None:
    try:
        contract = GroundedApiContract.model_validate_json(
            (core_dir / "contract.json").read_text(encoding="utf-8")
        )
        decision = ValidationDecision.model_validate_json(
            (core_dir / "decision.json").read_text(encoding="utf-8")
        )
        evidence = EvidenceBundle.model_validate_json(
            (core_dir / "evidence.json").read_text(encoding="utf-8")
        )
        raw_claims = json.loads((core_dir / "claims.json").read_text(encoding="utf-8"))
        raw_relationships = json.loads(
            (core_dir / "relationships.json").read_text(encoding="utf-8")
        )
        if not isinstance(raw_claims, list) or not isinstance(raw_relationships, list):
            raise ValueError("claims and relationships must be arrays")
        claims = tuple(GroundedClaim.model_validate(item) for item in raw_claims)
        relationships = tuple(
            ClaimEvidenceRelationship.model_validate(item) for item in raw_relationships
        )
    except (OSError, ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise StrictCoreExecutionError(
            "strict Core candidate artifacts are incomplete or invalid"
        ) from exc

    if validate_evidence_bundle(evidence):
        raise StrictCoreExecutionError("strict Core evidence bundle is invalid")
    if (
        evidence.source_set_id != contract.metadata.source_set_id
        or evidence.source_set_version != contract.metadata.source_set_version
    ):
        raise StrictCoreExecutionError("strict Core evidence is not bound to contract")
    relationship_by_id = {relationship.id: relationship for relationship in relationships}
    expected_relationships = {
        relationship.id: relationship
        for claim in claims
        for relationship in claim.support_relationships
    }
    if relationship_by_id != expected_relationships:
        raise StrictCoreExecutionError(
            "strict Core relationships are not bound to claims"
        )
    rebuilt = build_grounded_contract(
        contract.metadata,
        tuple(
            ContractClaimInput(
                identity=claim.canonical_identity,
                claim_kind=claim.claim_kind,
                value=claim.value,
                status=claim.status,
                evidence_refs=claim.evidence_refs,
                support_relationships=claim.support_relationships,
            )
            for claim in claims
        ),
    )
    if rebuilt != contract:
        raise StrictCoreExecutionError("strict Core contract is not bound to claims")
    if decision != release.validation:
        raise StrictCoreExecutionError("strict Core decision does not match release")
    if (
        release.contract_id != contract.metadata.contract_id
        or release.contract_digest != contract_digest(contract)
        or release.release_id != release_id_for_contract(contract)
        or release.source_set_id != contract.metadata.source_set_id
        or release.source_set_version != contract.metadata.source_set_version
    ):
        raise StrictCoreExecutionError("strict Core release is not bound to contract")
    exact_supported = sum(claim.status is ClaimStatus.SUPPORTED for claim in claims)
    if execution["exact_supported_claims"] != exact_supported:
        raise StrictCoreExecutionError(
            "strict Core execution count does not match claims"
        )
