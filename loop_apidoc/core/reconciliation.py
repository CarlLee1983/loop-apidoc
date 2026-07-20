from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from loop_apidoc.core.models import ClaimProposal, GroundedClaim
from loop_apidoc.core.verification import verify_claim_support
from loop_apidoc.domain.claim_paths import claim_value_at, material_claim_paths
from loop_apidoc.domain.evidence import (
    ClaimEvidenceRelationship,
    EvidenceBundle,
    SupportRelationshipType,
    canonical_json,
    fragment_digest,
    make_relationship_id,
)
from loop_apidoc.domain.identity import canonical_claim_identity
from loop_apidoc.domain.models import ClaimStatus


_SUPPORT_TYPES = frozenset(
    {
        SupportRelationshipType.EXPLICIT_SUPPORT,
        SupportRelationshipType.DERIVED_SUPPORT,
    }
)


def reconcile_claims(
    proposals: tuple[ClaimProposal, ...],
    *,
    evidence_bundle: EvidenceBundle,
    previous: tuple[GroundedClaim, ...] = (),
) -> tuple[GroundedClaim, ...]:
    grouped: dict[str, list[ClaimProposal]] = defaultdict(list)
    for proposal in proposals:
        identity = canonical_claim_identity(
            proposal.claim_kind,
            proposal.subject,
            proposal.predicate,
        )
        grouped[identity].append(proposal)

    reconciled: list[GroundedClaim] = []
    for identity in sorted(grouped):
        group = sorted(grouped[identity], key=lambda item: item.id)
        verified_by_proposal = {
            proposal.id: verify_claim_support(proposal, evidence_bundle)
            for proposal in group
        }
        fully_supported: list[ClaimProposal] = []
        relationships: list[ClaimEvidenceRelationship] = []
        has_contradiction = False

        for proposal in group:
            verified = verified_by_proposal[proposal.id]
            required = set(
                material_claim_paths(proposal.claim_kind, proposal.value)
            )
            supported = {
                item.claim_path
                for item in verified
                if item.relationship in _SUPPORT_TYPES
            }
            contradictions = tuple(
                item
                for item in verified
                if item.relationship is SupportRelationshipType.CONTRADICTS
            )
            has_contradiction = has_contradiction or bool(contradictions)
            relationships.extend(verified)
            uncovered = tuple(sorted(required - supported))
            relationships.extend(
                _coverage_relationships(
                    identity=identity,
                    proposal=proposal,
                    paths=uncovered,
                    verified=verified,
                )
            )
            if required and not uncovered and not contradictions:
                fully_supported.append(proposal)

        lineage = tuple(sorted(proposal.id for proposal in group))
        if has_contradiction:
            status = ClaimStatus.CONFLICTING
            value = _reconciled_values(group)
        elif fully_supported:
            supported_values = {
                canonical_json(proposal.value): proposal.value
                for proposal in fully_supported
            }
            if len(supported_values) > 1:
                status = ClaimStatus.CONFLICTING
                value = tuple(
                    supported_values[key] for key in sorted(supported_values)
                )
            else:
                status = ClaimStatus.SUPPORTED
                value = next(iter(supported_values.values()))
        elif all(proposal.value is None for proposal in group):
            status = ClaimStatus.MISSING
            value = None
        else:
            status = ClaimStatus.UNVERIFIED
            value = group[0].value

        ordered_relationships = _ordered_relationships(relationships)
        evidence = tuple(
            sorted(
                {
                    item.fragment_id
                    for item in ordered_relationships
                    if item.relationship is not SupportRelationshipType.INSUFFICIENT
                }
            )
        )
        reconciled.append(
            GroundedClaim(
                id=_stable_id(identity, lineage),
                canonical_identity=identity,
                claim_kind=group[0].claim_kind,
                value=value,
                evidence_refs=evidence,
                support_relationships=ordered_relationships,
                status=status,
                lineage=lineage,
            )
        )

    new_identities = {claim.canonical_identity for claim in reconciled}
    for claim in previous:
        if claim.canonical_identity not in new_identities:
            reconciled.append(
                claim.model_copy(update={"status": ClaimStatus.SUPERSEDED})
            )
    return tuple(sorted(reconciled, key=lambda claim: claim.canonical_identity))


def _coverage_relationships(
    *,
    identity: str,
    proposal: ClaimProposal,
    paths: tuple[str, ...],
    verified: tuple[ClaimEvidenceRelationship, ...],
) -> tuple[ClaimEvidenceRelationship, ...]:
    if not paths or not verified:
        return ()
    candidate = verified[0]
    relationships: list[ClaimEvidenceRelationship] = []
    for path in paths:
        claim_value = claim_value_at(proposal.claim_kind, proposal.value, path)
        payload: dict[str, Any] = {
            "claim_identity": identity,
            "claim_path": path,
            "fragment_id": candidate.fragment_id,
            "relationship": SupportRelationshipType.INSUFFICIENT,
            "verification_method": candidate.verification_method,
            "claim_value_digest": fragment_digest(canonical_json(claim_value)),
            "evidence_value_digest": None,
            "observed_value": None,
            "reason_code": "CLAIM_PATH_UNCOVERED",
            "derivation_steps": (),
        }
        relationships.append(
            ClaimEvidenceRelationship(
                id=make_relationship_id(payload),
                **payload,
            )
        )
    return tuple(relationships)


def _ordered_relationships(
    relationships: list[ClaimEvidenceRelationship],
) -> tuple[ClaimEvidenceRelationship, ...]:
    unique = {item.id: item for item in relationships}
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.claim_identity,
                item.claim_path,
                item.fragment_id,
                item.relationship.value,
                item.id,
            ),
        )
    )


def _reconciled_values(group: list[ClaimProposal]) -> Any:
    by_value = {canonical_json(proposal.value): proposal.value for proposal in group}
    if len(by_value) == 1:
        return next(iter(by_value.values()))
    return tuple(by_value[key] for key in sorted(by_value))


def _stable_id(identity: str, lineage: tuple[str, ...]) -> str:
    digest = hashlib.sha256(f"{identity}|{'|'.join(lineage)}".encode()).hexdigest()[:20]
    return f"claim-{digest}"
