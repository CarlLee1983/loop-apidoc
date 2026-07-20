from __future__ import annotations

import hashlib
import json
from datetime import datetime

from loop_apidoc.core.models import (
    ApprovalDecision,
    ContractRelease,
    ReleaseStatus,
    ValidationDecision,
    ValidationVerdict,
)
from loop_apidoc.domain.models import GroundedApiContract


class ApprovalRejected(ValueError):
    """An approval violates policy, identity separation, or release state."""


def make_candidate_release(
    contract: GroundedApiContract,
    validation: ValidationDecision,
    *,
    runtime_identities: tuple[str, ...],
    core_version: str,
    policy_version: str,
    projection_versions: tuple[tuple[str, str], ...],
    now: datetime,
    supersedes: str | None = None,
) -> ContractRelease:
    if validation.verdict is ValidationVerdict.REJECT:
        raise ApprovalRejected("rejected validation cannot create a candidate release")
    digest = contract_digest(contract)
    release_id = release_id_for_contract(contract)
    return ContractRelease(
        release_id=release_id,
        contract_id=contract.metadata.contract_id,
        contract_digest=digest,
        source_set_id=contract.metadata.source_set_id,
        source_set_version=contract.metadata.source_set_version,
        status=ReleaseStatus.CANDIDATE,
        validation=validation,
        runtime_identities=tuple(sorted(set(runtime_identities))),
        core_version=core_version,
        domain_version=contract.metadata.domain_version,
        policy_version=policy_version,
        projection_versions=tuple(sorted(projection_versions)),
        created_at=now,
        supersedes=supersedes,
    )


def approve_release(
    candidate: ContractRelease,
    decision: ApprovalDecision,
) -> ContractRelease:
    if candidate.status is not ReleaseStatus.CANDIDATE:
        raise ApprovalRejected("only candidate releases can be approved")
    if not decision.approved:
        raise ApprovalRejected(decision.reason or "approval denied")
    if (
        decision.actor.kind.value == "runtime"
        or decision.actor.id in candidate.runtime_identities
    ):
        raise ApprovalRejected("a runtime cannot approve its own output")
    return candidate.model_copy(
        update={
            "status": ReleaseStatus.APPROVED,
            "approved_at": decision.decided_at,
            "approved_by": decision.actor.id,
        }
    )


def publish_release(
    approved: ContractRelease,
    artifact_refs: tuple[str, ...],
    now: datetime,
) -> ContractRelease:
    if approved.status is not ReleaseStatus.APPROVED:
        raise ApprovalRejected("only approved releases can be published")
    if not artifact_refs:
        raise ApprovalRejected("publication requires at least one artifact")
    return approved.model_copy(
        update={
            "status": ReleaseStatus.PUBLISHED,
            "artifact_refs": artifact_refs,
            "published_at": now,
        }
    )


def contract_digest(contract: GroundedApiContract) -> str:
    canonical = json.dumps(
        contract.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def release_id_for_contract(contract: GroundedApiContract) -> str:
    return f"{contract.metadata.contract_id}-{contract_digest(contract)[:16]}"
