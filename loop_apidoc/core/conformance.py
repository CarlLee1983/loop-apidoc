from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from loop_apidoc.core.conformance_policy import (
    is_high_risk,
    route_feedback,
    verify_observation_target,
)
from loop_apidoc.core.governance import contract_digest
from loop_apidoc.domain.claim_paths import ClaimPathError, claim_value_at, material_claim_paths
from loop_apidoc.domain.conformance import (
    ApplicabilityEnvelope,
    CompatibilityAmendment,
    CompatibilityAmendmentProposal,
    ConformanceCoverage,
    ConformanceRelationship,
    ConformanceRelationshipType,
    EffectiveContract,
    EffectiveValue,
    EffectiveValueAuthority,
    FeedbackAssessment,
    FeedbackRoute,
    ImplementationObservation,
    MaterialClaimReference,
    NormativeRelease,
    ObservationBundle,
    ObservationKind,
    ObservationLineage,
    ObservationOutcome,
    normative_release_digest,
)
from loop_apidoc.domain.evidence import canonical_json
from loop_apidoc.domain.models import (
    ClaimStatus,
    ContractClaim,
    GroundedApiContract,
    Operation,
)


class ConformanceInputError(ValueError):
    """Feedback evidence cannot be assessed safely or deterministically."""


class ContractConformance:
    """Deterministic conformance operations behind one domain-oriented interface."""

    version = "conformance/v1"

    def assess(
        self,
        contract: GroundedApiContract | NormativeRelease,
        bundle: ObservationBundle,
        *,
        provider: str,
        product: str,
    ) -> FeedbackAssessment:
        release = contract if isinstance(contract, NormativeRelease) else None
        normative_contract = release.contract if release is not None else contract
        self._verify_base(normative_contract, bundle)
        if release is not None and release.base != bundle.base:
            raise ConformanceInputError(
                "observation bundle base does not match the normative release"
            )
        claims = {claim.identity: claim for claim in normative_contract.claims}
        operations = {
            f"{operation.method.upper()} {operation.path}": operation
            for operation in normative_contract.operations
        }
        scope_matches = (
            bundle.applicability.provider == provider
            and bundle.applicability.product == product
        )
        relationships = tuple(
            self._assess_observation(
                observation,
                claims=claims,
                operations=operations,
                scope_matches=scope_matches,
                release=release,
            )
            for observation in sorted(bundle.observations, key=lambda item: item.id)
        )
        self._reject_conflicting_observations(relationships)
        total = sum(
            len(material_claim_paths(claim.claim_kind or "", claim.value))
            for claim in normative_contract.claims
            if claim.status is ClaimStatus.SUPPORTED
        )
        assessed = len(
            {
                (item.claim_identity, item.claim_path)
                for item in relationships
                if item.relationship
                in {
                    ConformanceRelationshipType.CONFIRMS,
                    ConformanceRelationshipType.CONTRADICTS,
                }
            }
        )
        confirmed = len(
            {
                (item.claim_identity, item.claim_path)
                for item in relationships
                if item.relationship is ConformanceRelationshipType.CONFIRMS
            }
        )
        open_count = sum(
            item.relationship is not ConformanceRelationshipType.CONFIRMS
            for item in relationships
        )
        fully_verified = total > 0 and confirmed == total and open_count == 0
        declared_targets = (
            {
                (target.claim_identity, target.claim_path)
                for target in bundle.suite.declared_material_claims
            }
            if bundle.suite is not None
            else {
                (observation.claim_identity, observation.claim_path)
                for observation in bundle.observations
            }
        )
        all_targets = {
            (claim.identity, path)
            for claim in normative_contract.claims
            if claim.status is ClaimStatus.SUPPORTED
            for path in material_claim_paths(claim.claim_kind or "", claim.value)
        }
        coverage = ConformanceCoverage(
            material_claim_count=total,
            assessed_claim_count=assessed,
            confirmed_claim_count=confirmed,
            conformance_ratio=(confirmed / total if total else 0.0),
            declared_claim_count=len(declared_targets),
            suite_coverage_ratio=(
                len(declared_targets.intersection(all_targets)) / total if total else 0.0
            ),
            suite_id=bundle.suite.id if bundle.suite is not None else bundle.runner.id,
            suite_version=bundle.runner.version,
        )
        route = route_feedback(relationships)
        report_data: dict[str, Any] = {
            "base": bundle.base.model_dump(mode="json"),
            "normative_release_digest": (
                normative_release_digest(release)
                if release is not None
                else _digest_value(
                    {
                        "contract": normative_contract.model_dump(mode="json"),
                        "fragments": [],
                        "relationships": [],
                    }
                )
            ),
            "observation_bundle_id": bundle.bundle_id,
            "observation_bundle_digest": canonical_digest(bundle),
            "policy_version": bundle.policy_version,
            "redaction_policy_version": bundle.redaction_policy_version,
            "producer": bundle.producer.model_dump(mode="json"),
            "runner": bundle.runner.model_dump(mode="json"),
            "applicability": bundle.applicability.model_dump(mode="json"),
            "relationships": [item.model_dump(mode="json") for item in relationships],
            "route": route.value,
            "coverage": coverage.model_dump(mode="json"),
            "open_discrepancy_count": open_count,
            "fully_verified": {
                "verified": fully_verified,
                "applicability": bundle.applicability.model_dump(mode="json"),
                "as_of": bundle.applicability.observed_until,
                "suite_version": bundle.runner.version,
                "reasons": [] if fully_verified else [
                    "not every material claim was independently confirmed within this exact applicability envelope"
                ],
            },
        }
        assessment_id = "assessment-" + _digest_value(report_data)[:20]
        return FeedbackAssessment(assessment_id=assessment_id, **report_data)

    def propose(
        self,
        assessment: FeedbackAssessment,
        *,
        now: datetime,
    ) -> tuple[CompatibilityAmendmentProposal, ...]:
        """Create review subjects only for safe, reproducible contradictions."""

        _require_timezone(now, "proposal time")
        if now < assessment.applicability.observed_until:
            raise ConformanceInputError(
                "proposal time must not precede observation completion"
            )
        if assessment.route is not FeedbackRoute.AMENDMENT_PROPOSAL:
            return ()
        assessment_digest = canonical_digest(assessment)
        grouped: dict[tuple[str, str], list[ConformanceRelationship]] = {}
        for relationship in assessment.relationships:
            if relationship.relationship is not ConformanceRelationshipType.CONTRADICTS:
                continue
            if is_high_risk(relationship):
                continue
            grouped.setdefault(
                (relationship.claim_identity, relationship.claim_path), []
            ).append(relationship)

        proposals: list[CompatibilityAmendmentProposal] = []
        for (claim_identity, claim_path), relationships in sorted(grouped.items()):
            proposed_values = {
                _json_key(relationship.observed_value)
                for relationship in relationships
            }
            if len(proposed_values) != 1:
                raise ConformanceInputError(
                    f"conflicting contradictions for proposal target: {claim_identity}{claim_path}"
                )
            first = relationships[0]
            data: dict[str, Any] = {
                "base": assessment.base.model_dump(mode="json"),
                "normative_release_digest": assessment.normative_release_digest,
                "assessment_id": assessment.assessment_id,
                "assessment_digest": assessment_digest,
                "observation_bundle_id": assessment.observation_bundle_id,
                "observation_bundle_digest": assessment.observation_bundle_digest,
                "policy_version": assessment.policy_version,
                "redaction_policy_version": assessment.redaction_policy_version,
                "target": {
                    "claim_identity": claim_identity,
                    "claim_path": claim_path,
                },
                "claim_kind": first.claim_kind,
                "normative_value": first.normative_value,
                "proposed_value": first.observed_value,
                "scope": assessment.applicability.model_dump(mode="json"),
                "observation_ids": sorted(
                    relationship.observation_id for relationship in relationships
                ),
                "normative_evidence_refs": sorted(
                    {
                        ref
                        for relationship in relationships
                        for ref in relationship.normative_evidence_refs
                    }
                ),
                "observation_evidence_refs": sorted(
                    {
                        ref
                        for relationship in relationships
                        for ref in relationship.evidence_refs
                    }
                ),
                "producer": assessment.producer.model_dump(mode="json"),
                "runner": assessment.runner.model_dump(mode="json"),
                "assessed_targets": [
                    {
                        "claim_identity": claim_identity,
                        "claim_path": claim_path,
                    }
                    for claim_identity, claim_path in sorted(
                        {
                            (item.claim_identity, item.claim_path)
                            for item in assessment.relationships
                            if item.relationship
                            in {
                                ConformanceRelationshipType.CONFIRMS,
                                ConformanceRelationshipType.CONTRADICTS,
                            }
                        }
                    )
                ],
                "confirmed_targets": [
                    {
                        "claim_identity": claim_identity,
                        "claim_path": claim_path,
                    }
                    for claim_identity, claim_path in sorted(
                        {
                            (item.claim_identity, item.claim_path)
                            for item in assessment.relationships
                            if item.relationship
                            is ConformanceRelationshipType.CONFIRMS
                        }
                    )
                ],
                "contradicted_targets": [
                    {
                        "claim_identity": claim_identity,
                        "claim_path": claim_path,
                    }
                    for claim_identity, claim_path in sorted(
                        {
                            (item.claim_identity, item.claim_path)
                            for item in assessment.relationships
                            if item.relationship
                            is ConformanceRelationshipType.CONTRADICTS
                        }
                    )
                ],
                "conformance_coverage": assessment.coverage.model_dump(mode="json"),
                "created_at": now,
                "requires_human_review": True,
            }
            proposal_id = "proposal-" + _digest_value(data)[:20]
            proposals.append(
                CompatibilityAmendmentProposal(proposal_id=proposal_id, **data)
            )
        return tuple(proposals)

    def compose(
        self,
        release: NormativeRelease,
        amendments: tuple[CompatibilityAmendment, ...],
        *,
        target: ApplicabilityEnvelope,
        now: datetime,
    ) -> EffectiveContract:
        """Compose one exact-scope operational view without mutating its base."""

        _require_timezone(now, "composition time")
        actual_digest = contract_digest(release.contract)
        if release.base.contract_digest != actual_digest:
            raise ConformanceInputError("normative release contract digest is stale")
        amendment_ids = [amendment.amendment_id for amendment in amendments]
        if len(amendment_ids) != len(set(amendment_ids)):
            raise ConformanceInputError("duplicate amendment ids")

        active: list[CompatibilityAmendment] = []
        expired: list[str] = []
        inapplicable: list[str] = []
        stale: list[str] = []
        for amendment in sorted(amendments, key=lambda item: item.amendment_id):
            proposal = amendment.proposal
            if proposal.scope != target:
                inapplicable.append(amendment.amendment_id)
                continue
            if amendment.approval.approved_at > now:
                stale.append(amendment.amendment_id)
                continue
            if amendment.expires_at <= now:
                expired.append(amendment.amendment_id)
                continue
            if not self._amendment_is_current(release, amendment):
                stale.append(amendment.amendment_id)
                continue
            active.append(amendment)

        all_by_id = {amendment.amendment_id: amendment for amendment in amendments}
        active_by_id = {amendment.amendment_id: amendment for amendment in active}
        superseded: set[str] = set()
        for amendment in active:
            predecessor_id = amendment.supersedes
            if predecessor_id is None:
                continue
            predecessor = all_by_id.get(predecessor_id)
            if predecessor is None:
                raise ConformanceInputError(
                    f"amendment supersedes unknown amendment: {predecessor_id}"
                )
            if predecessor_id == amendment.amendment_id:
                raise ConformanceInputError("amendment cannot supersede itself")
            if (
                predecessor.proposal.target != amendment.proposal.target
                or predecessor.proposal.scope != amendment.proposal.scope
            ):
                raise ConformanceInputError(
                    "amendment supersession must retain the same scope and target"
                )
            if predecessor_id in active_by_id:
                superseded.add(predecessor_id)
        _reject_supersession_cycles(active_by_id)
        active = [
            amendment
            for amendment in active
            if amendment.amendment_id not in superseded
        ]

        by_target: dict[tuple[str, str], list[CompatibilityAmendment]] = {}
        for amendment in active:
            amendment_target = amendment.proposal.target
            by_target.setdefault(
                (amendment_target.claim_identity, amendment_target.claim_path), []
            ).append(amendment)
        conflict = next(
            (
                key
                for key, same_target in sorted(by_target.items())
                if len(same_target) > 1
            ),
            None,
        )
        if conflict is not None:
            raise ConformanceInputError(
                "conflicting active amendments for the same scope and target: "
                f"{conflict[0]}{conflict[1]}"
            )

        overrides = {
            key: values[0]
            for key, values in by_target.items()
        }
        effective_values: list[EffectiveValue] = []
        for claim in sorted(release.contract.claims, key=lambda item: item.identity):
            if claim.status is not ClaimStatus.SUPPORTED:
                continue
            for path in material_claim_paths(claim.claim_kind or "", claim.value):
                normative = claim_value_at(claim.claim_kind or "", claim.value, path)
                amendment = overrides.get((claim.identity, path))
                normative_refs = _normative_evidence_refs(release, claim, path)
                if amendment is None:
                    effective_values.append(
                        EffectiveValue(
                            target=MaterialClaimReference(
                                claim_identity=claim.identity, claim_path=path
                            ),
                            claim_kind=claim.claim_kind,
                            normative_value=normative,
                            effective_value=normative,
                            authority=EffectiveValueAuthority.NORMATIVE,
                            normative_evidence_refs=normative_refs,
                        )
                    )
                    continue
                proposal = amendment.proposal
                effective_values.append(
                    EffectiveValue(
                        target=proposal.target,
                        claim_kind=proposal.claim_kind,
                        normative_value=normative,
                        effective_value=proposal.proposed_value,
                        authority=EffectiveValueAuthority.OBSERVED_OVERRIDE,
                        normative_evidence_refs=tuple(
                            sorted(
                                set(normative_refs).union(
                                    proposal.normative_evidence_refs
                                )
                            )
                        ),
                        amendment_id=amendment.amendment_id,
                        observation_evidence_refs=proposal.observation_evidence_refs,
                        approval_id=amendment.approval.approval_id,
                        approved_by=amendment.approval.approved_by,
                    )
                )
        all_material_targets = {
            (claim.identity, path)
            for claim in release.contract.claims
            if claim.status is ClaimStatus.SUPPORTED
            for path in material_claim_paths(claim.claim_kind or "", claim.value)
        }
        assessed_targets = {
            (target.claim_identity, target.claim_path)
            for amendment in active
            for target in amendment.proposal.assessed_targets
        }.intersection(all_material_targets)
        confirmed_targets = {
            (target.claim_identity, target.claim_path)
            for amendment in active
            for target in amendment.proposal.confirmed_targets
        }.intersection(all_material_targets)
        untested_count = len(all_material_targets - assessed_targets)
        contradicted_targets = {
            (target.claim_identity, target.claim_path)
            for amendment in active
            for target in amendment.proposal.contradicted_targets
        }.intersection(all_material_targets)
        resolved_targets = {
            (
                amendment.proposal.target.claim_identity,
                amendment.proposal.target.claim_path,
            )
            for amendment in active
        }
        unresolved_contradiction_count = len(
            contradicted_targets - resolved_targets
        )
        composed_coverage = ConformanceCoverage(
            material_claim_count=len(all_material_targets),
            assessed_claim_count=len(assessed_targets),
            confirmed_claim_count=len(confirmed_targets),
            conformance_ratio=(
                len(confirmed_targets) / len(all_material_targets)
                if all_material_targets
                else 0.0
            ),
            declared_claim_count=len(assessed_targets),
            suite_coverage_ratio=(
                len(assessed_targets) / len(all_material_targets)
                if all_material_targets
                else 0.0
            ),
            suite_version="composed/1",
        )
        identity_data = {
            "base": release.base.model_dump(mode="json"),
            "target": target.model_dump(mode="json"),
            "as_of": now,
            "applied_amendment_ids": sorted(
                amendment.amendment_id for amendment in active
            ),
        }
        return EffectiveContract(
            effective_contract_id="effective-" + _digest_value(identity_data)[:20],
            base=release.base,
            target=target,
            as_of=now,
            valid_until=min(
                (amendment.expires_at for amendment in active), default=None
            ),
            normative_contract=release.contract,
            values=tuple(effective_values),
            applied_amendment_ids=tuple(identity_data["applied_amendment_ids"]),
            superseded_amendment_ids=tuple(sorted(superseded)),
            expired_amendment_ids=tuple(expired),
            inapplicable_amendment_ids=tuple(inapplicable),
            stale_amendment_ids=tuple(stale),
            conformance_coverage=composed_coverage,
            untested_material_claim_count=untested_count,
            unresolved_contradiction_count=unresolved_contradiction_count,
            open_discrepancy_count=(
                len(expired)
                + len(stale)
                + untested_count
                + unresolved_contradiction_count
            ),
        )

    def _amendment_is_current(
        self,
        release: NormativeRelease,
        amendment: CompatibilityAmendment,
    ) -> bool:
        proposal = amendment.proposal
        approval = amendment.approval
        if proposal.base != release.base:
            return False
        if proposal.normative_release_digest != normative_release_digest(release):
            return False
        if proposal.policy_version != self.version:
            return False
        if approval.proposal_digest != canonical_digest(proposal):
            return False
        if approval.base_asset_id != proposal.base.asset_id:
            return False
        if approval.assessment_id != proposal.assessment_id:
            return False
        if approval.observation_bundle_id != proposal.observation_bundle_id:
            return False
        if approval.assessment_digest != proposal.assessment_digest:
            return False
        if approval.observation_bundle_digest != proposal.observation_bundle_digest:
            return False
        if approval.base_contract_digest != proposal.base.contract_digest:
            return False
        if approval.policy_version != proposal.policy_version:
            return False
        if approval.redaction_policy_version != proposal.redaction_policy_version:
            return False
        claims = {claim.identity: claim for claim in release.contract.claims}
        claim = claims.get(proposal.target.claim_identity)
        if claim is None or claim.status is not ClaimStatus.SUPPORTED:
            return False
        if claim.claim_kind != proposal.claim_kind:
            return False
        try:
            normative = claim_value_at(
                claim.claim_kind or "", claim.value, proposal.target.claim_path
            )
        except ClaimPathError:
            return False
        return normative == proposal.normative_value

    def _verify_base(
        self, contract: GroundedApiContract, bundle: ObservationBundle
    ) -> None:
        if bundle.policy_version != self.version:
            raise ConformanceInputError(
                f"unsupported conformance policy: {bundle.policy_version}"
            )
        actual = contract_digest(contract)
        if bundle.base.contract_digest != actual:
            raise ConformanceInputError("observation bundle base contract digest is stale")
        if bundle.base.docset_id != contract.metadata.contract_id:
            raise ConformanceInputError(
                "observation bundle docset does not match the Canonical Contract"
            )

    def _assess_observation(
        self,
        observation: ImplementationObservation,
        *,
        claims: dict[str, ContractClaim],
        operations: dict[str, Operation],
        scope_matches: bool,
        release: NormativeRelease | None,
    ) -> ConformanceRelationship:
        claim = claims.get(observation.claim_identity)
        if claim is None:
            raise ConformanceInputError(
                f"unknown claim identity: {observation.claim_identity}"
            )
        if claim.status is not ClaimStatus.SUPPORTED:
            raise ConformanceInputError(
                f"claim is not a supported normative claim: {observation.claim_identity}"
            )
        operation = operations.get(observation.operation_ref)
        if operation is None:
            raise ConformanceInputError(
                f"unknown operation reference: {observation.operation_ref}"
            )
        target_error = verify_observation_target(observation, claim, operation)
        if target_error is not None:
            raise ConformanceInputError(target_error)
        try:
            normative = claim_value_at(
                claim.claim_kind or "", claim.value, observation.claim_path
            )
        except ClaimPathError as exc:
            raise ConformanceInputError(
                f"unknown claim path for {observation.claim_identity}: {observation.claim_path}"
            ) from exc
        if observation.expected != normative:
            raise ConformanceInputError(
                f"producer expected value does not match bound normative claim: {observation.id}"
            )
        evidence_refs = tuple(sorted(item.fragment_id for item in observation.evidence))
        normative_evidence_refs = (
            _normative_evidence_refs(release, claim, observation.claim_path)
            if release is not None
            else tuple(sorted(binding.fragment_id for binding in claim.evidence))
        )
        outcomes = {attempt.outcome for attempt in observation.attempts}
        outcome = next(iter(outcomes)) if len(outcomes) == 1 else None
        if not scope_matches:
            return ConformanceRelationship(
                observation_id=observation.id,
                claim_identity=observation.claim_identity,
                claim_path=observation.claim_path,
                operation_ref=observation.operation_ref,
                kind=observation.kind,
                outcome=outcome,
                attempt_count=len(observation.attempts),
                claim_kind=claim.claim_kind,
                relationship=ConformanceRelationshipType.OUT_OF_SCOPE,
                normative_value=normative,
                evidence_refs=evidence_refs,
                normative_evidence_refs=normative_evidence_refs,
                reason="provider or product differs from the approved normative release",
            )
        observed_values = {_json_key(attempt.observed) for attempt in observation.attempts}
        if len(outcomes) != 1 or len(observed_values) != 1:
            raise ConformanceInputError(
                f"conflicting attempts within observation: {observation.id}"
            )
        observed = observation.attempts[0].observed
        assert outcome is not None
        if outcome is not ObservationOutcome.API_RESPONSE:
            relationship = ConformanceRelationshipType.INCONCLUSIVE
            reason = f"{outcome.value} is not an API behavior outcome"
        elif (
            observation.lineage is ObservationLineage.CONTRACT_DERIVED
            and _matches(observation.kind, normative, observed)
        ):
            relationship = ConformanceRelationshipType.INCONCLUSIVE
            reason = "a contract-derived probe cannot independently support its oracle claim"
        elif observation.lineage is ObservationLineage.MANUAL:
            relationship = ConformanceRelationshipType.INCONCLUSIVE
            reason = "a manual report requires independently replayable evidence"
        elif _matches(observation.kind, normative, observed):
            relationship = ConformanceRelationshipType.CONFIRMS
            reason = None
        else:
            relationship = ConformanceRelationshipType.CONTRADICTS
            reason = "observed behavior differs from the bound normative value"
        return ConformanceRelationship(
            observation_id=observation.id,
            claim_identity=observation.claim_identity,
            claim_path=observation.claim_path,
            operation_ref=observation.operation_ref,
            kind=observation.kind,
            outcome=outcome,
            attempt_count=len(observation.attempts),
            claim_kind=claim.claim_kind,
            relationship=relationship,
            normative_value=normative,
            observed_value=observed,
            evidence_refs=evidence_refs,
            normative_evidence_refs=normative_evidence_refs,
            reason=reason,
        )

    def _reject_conflicting_observations(
        self, relationships: tuple[ConformanceRelationship, ...]
    ) -> None:
        grouped: dict[tuple[str, str], set[str]] = {}
        for item in relationships:
            if item.relationship not in {
                ConformanceRelationshipType.CONFIRMS,
                ConformanceRelationshipType.CONTRADICTS,
            }:
                continue
            grouped.setdefault((item.claim_identity, item.claim_path), set()).add(
                _json_key(item.observed_value)
            )
        conflicts = [key for key, values in grouped.items() if len(values) > 1]
        if conflicts:
            claim, path = sorted(conflicts)[0]
            raise ConformanceInputError(
                f"conflicting observations for the same scope and target: {claim}{path}"
            )


def canonical_digest(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return _digest_value(value)


def _digest_value(value: Any) -> str:
    payload = canonical_json(value)
    return hashlib.sha256(payload.encode()).hexdigest()


def _json_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _matches(kind: ObservationKind, normative: Any, observed: Any) -> bool:
    if kind is ObservationKind.RESPONSE_FIELD:
        return observed in {True, "present"}
    if kind is ObservationKind.OPERATION_SUCCESS:
        return observed is True
    return observed == normative


def _normative_evidence_refs(
    release: NormativeRelease,
    claim: ContractClaim,
    path: str,
) -> tuple[str, ...]:
    refs = {
        binding.fragment_id
        for binding in claim.evidence
        if binding.claim_path in {None, path}
    }
    refs.update(
        relationship.fragment_id
        for relationship in release.relationships
        if relationship.claim_identity == claim.identity
        and relationship.claim_path == path
    )
    return tuple(sorted(refs))


def _require_timezone(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ConformanceInputError(f"{label} must include a timezone")


def _reject_supersession_cycles(
    amendments: dict[str, CompatibilityAmendment],
) -> None:
    for start in amendments:
        visited: set[str] = set()
        current = start
        while current in amendments:
            if current in visited:
                raise ConformanceInputError("amendment supersession cycle")
            visited.add(current)
            predecessor = amendments[current].supersedes
            if predecessor is None:
                break
            current = predecessor
