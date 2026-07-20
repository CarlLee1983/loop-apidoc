from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from loop_apidoc.core.models import ClaimProposal, GroundedClaim
from loop_apidoc.domain.identity import canonical_claim_identity
from loop_apidoc.domain.models import ClaimStatus


def reconcile_claims(
    proposals: tuple[ClaimProposal, ...],
    *,
    evidence_fragment_ids: frozenset[str],
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
        group = grouped[identity]
        valid = [
            proposal
            for proposal in group
            if proposal.evidence_refs
            and set(proposal.evidence_refs).issubset(evidence_fragment_ids)
        ]
        evidence = tuple(
            sorted({ref for proposal in valid for ref in proposal.evidence_refs})
        )
        lineage = tuple(sorted(proposal.id for proposal in group))
        if not valid:
            status = ClaimStatus.UNVERIFIED
            value = group[0].value
        else:
            by_value = {
                _canonical_value(proposal.value): proposal.value for proposal in valid
            }
            if len(by_value) > 1:
                status = ClaimStatus.CONFLICTING
                value = tuple(by_value[key] for key in sorted(by_value))
            else:
                value = next(iter(by_value.values()))
                status = ClaimStatus.MISSING if value is None else ClaimStatus.SUPPORTED
        reconciled.append(
            GroundedClaim(
                id=_stable_id(identity, lineage),
                canonical_identity=identity,
                claim_kind=group[0].claim_kind,
                value=value,
                evidence_refs=evidence,
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


def _canonical_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_id(identity: str, lineage: tuple[str, ...]) -> str:
    digest = hashlib.sha256(f"{identity}|{'|'.join(lineage)}".encode()).hexdigest()[:20]
    return f"claim-{digest}"
