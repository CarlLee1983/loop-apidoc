from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from loop_apidoc.core.conformance import (
    ConformanceInputError,
    ContractConformance,
    canonical_digest,
)
from loop_apidoc.core.governance import contract_digest
from loop_apidoc.core.conformance_policy import route_feedback
from loop_apidoc.domain.conformance import (
    AmendmentApproval,
    ApplicabilityEnvelope,
    CompatibilityAmendment,
    ConformanceRelationship,
    ConformanceRelationshipType,
    FeedbackRoute,
    IdentityVersion,
    ImplementationObservation,
    MaterialClaimReference,
    NormativeBaseBinding,
    NormativeRelease,
    ObservationAttempt,
    ObservationBundle,
    ObservationEvidence,
    ObservationKind,
    ObservationLineage,
    ObservationOutcome,
    ReplayRecipe,
    SanitizedObservationFact,
    SuiteIdentity,
    normative_release_digest,
)
from loop_apidoc.domain.evidence import EvidenceFragment, FragmentPrecision, LineRangeLocator
from loop_apidoc.domain.models import (
    ClaimStatus,
    ContractClaim,
    ContractMetadata,
    EvidenceBinding,
    GroundedApiContract,
    Operation,
    Response,
)


NOW = datetime(2026, 8, 2, 10, tzinfo=timezone.utc)
CLAIM_ID = "operation:GET:/ping"


def _contract(*, claim_kind: str = "operation", value: object | None = None) -> GroundedApiContract:
    operation = Operation(
        method="GET",
        path="/ping",
        responses=(
            Response(
                status_code="200",
                description="OK",
                schema_ref="PingResponse" if claim_kind == "schema" else None,
            ),
        ),
    )
    return GroundedApiContract(
        metadata=ContractMetadata(
            contract_id="demo-api",
            title="Demo API",
            version="1.0.0",
            source_set_id="sources",
            source_set_version="1",
            domain_version="1",
        ),
        operations=(operation,),
        claims=(
            ContractClaim(
                identity=CLAIM_ID,
                claim_kind=claim_kind,
                status=ClaimStatus.SUPPORTED,
                value=(
                    operation.model_dump(mode="json", exclude={"evidence"})
                    if value is None
                    else value
                ),
                evidence=(
                    EvidenceBinding(
                        fragment_id="normative-fragment",
                        claim_identity=CLAIM_ID,
                        claim_path="/responses/200/status_code",
                    ),
                ),
            ),
        ),
    )


def _scope(*, environment: str = "sandbox") -> ApplicabilityEnvelope:
    return ApplicabilityEnvelope(
        provider="demo",
        product="backend",
        api_version="1.0.0",
        environment=environment,
        region="tw",
        endpoint_identity="https://sandbox.example.test",
        account_class="merchant-test",
        authentication_role="merchant",
        client_version="client/1",
        harness_version="suite/1",
        test_data_class="synthetic",
        observed_from=NOW - timedelta(minutes=1),
        observed_until=NOW,
    )


def _bundle(
    contract: GroundedApiContract,
    *,
    path: str = "/responses/200/status_code",
    expected: object = "200",
    observed: object = "201",
    kind: ObservationKind = ObservationKind.RESPONSE_STATUS,
    outcome: ObservationOutcome = ObservationOutcome.API_RESPONSE,
    lineage: ObservationLineage = ObservationLineage.INDEPENDENT,
) -> ObservationBundle:
    sanitized_facts = (
        (SanitizedObservationFact(kind=kind, value=observed),)
        if outcome is ObservationOutcome.API_RESPONSE
        else ()
    )
    canonical_facts = json.dumps(
        [fact.model_dump(mode="json") for fact in sanitized_facts],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return ObservationBundle(
        schema_version="implementation-observation-bundle/v1",
        bundle_id="bundle-1",
        base=NormativeBaseBinding(
            docset_id="demo-api",
            asset_id="asset-1",
            contract_digest=contract_digest(contract),
        ),
        policy_version="conformance/v1",
        redaction_policy_version="redaction/v1",
        producer=IdentityVersion(id="producer", version="1"),
        runner=IdentityVersion(id="runner", version="suite/1"),
        applicability=_scope(),
        observations=(
            ImplementationObservation(
                id="obs-1",
                kind=kind,
                operation_ref="GET /ping",
                claim_identity=CLAIM_ID,
                claim_path=path,
                expected=expected,
                probe_digest="sha256:" + "1" * 64,
                fixture_digest="sha256:" + "2" * 64,
                lineage=lineage,
                replay=ReplayRecipe(executor="runner", steps=("GET /ping",)),
                attempts=(
                    ObservationAttempt(
                        id="attempt-1",
                        observed_at=NOW,
                        outcome=outcome,
                        observed=observed,
                    ),
                ),
                evidence=(
                    ObservationEvidence(
                        fragment_id="observation-fragment",
                        digest="sha256:"
                        + hashlib.sha256(canonical_facts.encode()).hexdigest(),
                        media_type="application/json",
                        size_bytes=10,
                        sanitized_facts=sanitized_facts,
                    ),
                ),
            ),
        ),
    )


def _release(contract: GroundedApiContract) -> NormativeRelease:
    return NormativeRelease(
        base=NormativeBaseBinding(
            docset_id="demo-api",
            asset_id="asset-1",
            contract_digest=contract_digest(contract),
        ),
        contract=contract,
        fragments=(
            EvidenceFragment(
                id="normative-fragment",
                source_artifact_id="supplier-doc",
                locator=LineRangeLocator(start_line=10, end_line=10),
                fragment_digest="4" * 64,
                normalized_excerpt="Success returns HTTP 200.",
                precision=FragmentPrecision.EXACT,
            ),
        ),
    )


def test_observation_requires_fixture_identity_for_replay() -> None:
    payload = _bundle(_contract()).model_dump(mode="json")
    del payload["observations"][0]["fixture_digest"]

    with pytest.raises(ValidationError):
        ObservationBundle.model_validate(payload)


def test_observation_bundle_rejects_duplicate_evidence_fragment_ids() -> None:
    payload = _bundle(_contract()).model_dump(mode="json")
    duplicate = json.loads(json.dumps(payload["observations"][0]))
    duplicate["id"] = "obs-2"
    duplicate["attempts"][0]["id"] = "attempt-2"
    payload["observations"].append(duplicate)

    with pytest.raises(ValidationError, match="evidence fragment ids must be unique"):
        ObservationBundle.model_validate(payload)


def _approved(proposal, *, expires_at: datetime, approver: str = "reviewer") -> CompatibilityAmendment:
    approval = AmendmentApproval(
        approval_id="approval-1",
        approved_by=IdentityVersion(id=approver, version="1"),
        approved_at=NOW,
        base_asset_id=proposal.base.asset_id,
        assessment_id=proposal.assessment_id,
        observation_bundle_id=proposal.observation_bundle_id,
        proposal_digest=canonical_digest(proposal),
        assessment_digest=proposal.assessment_digest,
        observation_bundle_digest=proposal.observation_bundle_digest,
        base_contract_digest=proposal.base.contract_digest,
        policy_version=proposal.policy_version,
        redaction_policy_version=proposal.redaction_policy_version,
    )
    return CompatibilityAmendment(
        amendment_id="amendment-1",
        proposal=proposal,
        approval=approval,
        expires_at=expires_at,
    )


def _rebind_amendment(
    amendment: CompatibilityAmendment,
    release: NormativeRelease,
    **proposal_updates: object,
) -> CompatibilityAmendment:
    """Keep an amendment internally bound while changing its release under test."""
    proposal = amendment.proposal.model_copy(
        update={
            "base": release.base,
            "normative_release_digest": normative_release_digest(release),
            **proposal_updates,
        }
    )
    approval = amendment.approval.model_copy(
        update={
            "base_asset_id": proposal.base.asset_id,
            "proposal_digest": canonical_digest(proposal),
            "base_contract_digest": proposal.base.contract_digest,
        }
    )
    return amendment.model_copy(update={"proposal": proposal, "approval": approval})


def test_propose_creates_review_only_scope_bound_amendment_from_valid_contradiction() -> None:
    contract = _contract()
    service = ContractConformance()
    assessment = service.assess(
        _release(contract), _bundle(contract), provider="demo", product="backend"
    )

    proposals = service.propose(assessment, now=NOW)

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.target.claim_identity == CLAIM_ID
    assert proposal.target.claim_path == "/responses/200/status_code"
    assert proposal.normative_value == "200"
    assert proposal.proposed_value == "201"
    assert proposal.scope == _scope()
    assert proposal.observation_evidence_refs == ("observation-fragment",)
    assert proposal.normative_evidence_refs == ("normative-fragment",)
    assert proposal.normative_release_digest == assessment.normative_release_digest
    assert proposal.requires_human_review is True
    assert proposal.producer.id == "producer"
    assert proposal.runner.id == "runner"


def test_propose_cannot_precede_observation_completion() -> None:
    contract = _contract()
    assessment = ContractConformance().assess(
        _release(contract), _bundle(contract), provider="demo", product="backend"
    )

    with pytest.raises(ConformanceInputError, match="observation completion"):
        ContractConformance().propose(
            assessment, now=assessment.applicability.observed_until - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    ("outcome", "lineage"),
    [
        (ObservationOutcome.TIMEOUT, ObservationLineage.INDEPENDENT),
        (ObservationOutcome.API_RESPONSE, ObservationLineage.CONTRACT_DERIVED),
    ],
)
def test_propose_never_promotes_inconclusive_or_circular_evidence(
    outcome: ObservationOutcome, lineage: ObservationLineage
) -> None:
    contract = _contract()
    service = ContractConformance()
    assessment = service.assess(
        contract,
        _bundle(
            contract,
            observed=(None if outcome is not ObservationOutcome.API_RESPONSE else "200"),
            outcome=outcome,
            lineage=lineage,
        ),
        provider="demo",
        product="backend",
    )

    assert service.propose(assessment, now=NOW) == ()
    assert assessment.coverage.assessed_claim_count == 0
    assert assessment.coverage.confirmed_claim_count == 0


def test_assess_rejects_bundle_that_does_not_match_a_normative_release_base() -> None:
    contract = _contract()
    release = _release(contract)
    bundle = _bundle(contract).model_copy(
        update={"base": release.base.model_copy(update={"asset_id": "other-asset"})}
    )

    with pytest.raises(ConformanceInputError, match="does not match the normative release"):
        ContractConformance().assess(
            release, bundle, provider="demo", product="backend"
        )


def test_propose_skips_high_risk_contradictions_even_when_route_is_amendment() -> None:
    contract = _contract(
        claim_kind="schema",
        value={"name": "PingResponse", "fields": [{"name": "id", "type": "string"}]},
    )
    service = ContractConformance()
    assessment = service.assess(
        contract,
        _bundle(
            contract,
            path="/fields/id/name",
            expected="id",
            observed=False,
            kind=ObservationKind.RESPONSE_FIELD,
        ),
        provider="demo",
        product="backend",
    )

    forced_amendment_route = assessment.model_copy(
        update={"route": FeedbackRoute.AMENDMENT_PROPOSAL}
    )
    assert service.propose(forced_amendment_route, now=NOW) == ()


def test_propose_rejects_conflicting_contradictions_for_one_target() -> None:
    contract = _contract()
    service = ContractConformance()
    assessment = service.assess(
        _release(contract), _bundle(contract), provider="demo", product="backend"
    )
    first = assessment.relationships[0]
    second = first.model_copy(update={"observation_id": "obs-2", "observed_value": "202"})
    forced_amendment_route = assessment.model_copy(
        update={
            "route": FeedbackRoute.AMENDMENT_PROPOSAL,
            "relationships": (first, second),
        }
    )

    with pytest.raises(ConformanceInputError, match="conflicting contradictions"):
        service.propose(forced_amendment_route, now=NOW)


def test_out_of_scope_relationship_does_not_count_as_assessed_coverage() -> None:
    contract = _contract()

    assessment = ContractConformance().assess(
        contract,
        _bundle(contract),
        provider="different-provider",
        product="backend",
    )

    assert assessment.relationships[0].relationship == "out_of_scope"
    assert assessment.coverage.assessed_claim_count == 0
    assert assessment.coverage.confirmed_claim_count == 0


def test_observation_claim_must_belong_to_its_operation() -> None:
    contract = _contract()
    unrelated = Operation(
        method="POST",
        path="/unrelated",
        responses=(Response(status_code="200", description="OK"),),
    )
    forged_claim = contract.claims[0].model_copy(
        update={
            "value": unrelated.model_dump(mode="json", exclude={"evidence"})
        }
    )
    forged_contract = contract.model_copy(
        update={
            "operations": (*contract.operations, unrelated),
            "claims": (forged_claim,),
        }
    )

    with pytest.raises(ConformanceInputError, match="does not belong"):
        ContractConformance().assess(
            forged_contract,
            _bundle(forged_contract),
            provider="demo",
            product="backend",
        )


def test_observation_kind_must_match_an_allowlisted_claim_path() -> None:
    contract = _contract()
    operation = contract.operations[0].model_copy(
        update={
            "responses": (
                contract.operations[0].responses[0].model_copy(
                    update={"description": "200"}
                ),
            )
        }
    )
    contract = contract.model_copy(
        update={
            "operations": (operation,),
            "claims": (
                contract.claims[0].model_copy(
                    update={
                        "value": operation.model_dump(
                            mode="json", exclude={"evidence"}
                        )
                    }
                ),
            ),
        }
    )

    with pytest.raises(ConformanceInputError, match="not allowlisted"):
        ContractConformance().assess(
            contract,
            _bundle(
                contract,
                path="/responses/200/description",
                expected="200",
            ),
            provider="demo",
            product="backend",
        )


def test_schema_observation_must_reference_the_operation_response_schema() -> None:
    contract = _contract(
        claim_kind="schema",
        value={"name": "OtherResponse", "fields": [{"name": "id", "type": "string"}]},
    )

    with pytest.raises(ConformanceInputError, match="does not belong to its operation response"):
        ContractConformance().assess(
            contract,
            _bundle(
                contract,
                path="/fields/id/name",
                expected="id",
                observed=False,
                kind=ObservationKind.RESPONSE_FIELD,
            ),
            provider="demo",
            product="backend",
        )


def test_response_field_observation_path_suffix_is_allowlisted_by_kind() -> None:
    contract = _contract(
        claim_kind="schema",
        value={"name": "PingResponse", "fields": [{"name": "id", "type": "string"}]},
    )

    with pytest.raises(ConformanceInputError, match="not allowlisted"):
        ContractConformance().assess(
            contract,
            _bundle(
                contract,
                path="/fields/id/type",
                expected="id",
                observed=False,
                kind=ObservationKind.RESPONSE_FIELD,
            ),
            provider="demo",
            product="backend",
        )


def test_harness_failure_routes_to_implementation_correction() -> None:
    contract = _contract()

    assessment = ContractConformance().assess(
        contract,
        _bundle(contract, observed=None, outcome=ObservationOutcome.HARNESS_FAILURE),
        provider="demo",
        product="backend",
    )

    assert assessment.route == "implementation_correction"


def test_repeated_transport_failure_routes_to_provider_runtime_review() -> None:
    contract = _contract()
    bundle = _bundle(
        contract, observed=None, outcome=ObservationOutcome.TIMEOUT
    )
    observation = bundle.observations[0]
    bundle = bundle.model_copy(
        update={
            "observations": (
                observation.model_copy(
                    update={
                        "attempts": (
                            observation.attempts[0],
                            observation.attempts[0].model_copy(
                                update={"id": "attempt-2"}
                            ),
                        )
                    }
                ),
            )
        }
    )

    assessment = ContractConformance().assess(
        contract, bundle, provider="demo", product="backend"
    )

    assert assessment.route == "provider_runtime_regression_review"


@pytest.mark.parametrize(
    (
        "expected_route",
        "relationship",
        "kind",
        "outcome",
        "attempt_count",
        "normative_refs",
    ),
    (
        (
            FeedbackRoute.CLOSED_NO_CHANGE,
            ConformanceRelationshipType.CONFIRMS,
            ObservationKind.RESPONSE_STATUS,
            ObservationOutcome.API_RESPONSE,
            1,
            ("normative-fragment",),
        ),
        (
            FeedbackRoute.NEEDS_EVIDENCE,
            ConformanceRelationshipType.INCONCLUSIVE,
            ObservationKind.RESPONSE_STATUS,
            ObservationOutcome.TIMEOUT,
            1,
            (),
        ),
        (
            FeedbackRoute.PROVIDER_CLARIFICATION,
            ConformanceRelationshipType.CONTRADICTS,
            ObservationKind.RESPONSE_FIELD,
            ObservationOutcome.API_RESPONSE,
            1,
            ("normative-fragment",),
        ),
        (
            FeedbackRoute.IMPLEMENTATION_CORRECTION,
            ConformanceRelationshipType.INCONCLUSIVE,
            ObservationKind.RESPONSE_STATUS,
            ObservationOutcome.HARNESS_FAILURE,
            1,
            (),
        ),
        (
            FeedbackRoute.ENVIRONMENT_CONFIGURATION_CORRECTION,
            ConformanceRelationshipType.OUT_OF_SCOPE,
            ObservationKind.RESPONSE_STATUS,
            ObservationOutcome.API_RESPONSE,
            1,
            (),
        ),
        (
            FeedbackRoute.ENVIRONMENT_CONFIGURATION_CORRECTION,
            ConformanceRelationshipType.INCONCLUSIVE,
            ObservationKind.RESPONSE_STATUS,
            ObservationOutcome.DNS_FAILURE,
            1,
            (),
        ),
        (
            FeedbackRoute.EXTRACTION_CORRECTION,
            ConformanceRelationshipType.CONTRADICTS,
            ObservationKind.RESPONSE_STATUS,
            ObservationOutcome.API_RESPONSE,
            1,
            (),
        ),
        (
            FeedbackRoute.PROVIDER_RUNTIME_REGRESSION_REVIEW,
            ConformanceRelationshipType.INCONCLUSIVE,
            ObservationKind.RESPONSE_STATUS,
            ObservationOutcome.TIMEOUT,
            2,
            (),
        ),
        (
            FeedbackRoute.AMENDMENT_PROPOSAL,
            ConformanceRelationshipType.CONTRADICTS,
            ObservationKind.RESPONSE_STATUS,
            ObservationOutcome.API_RESPONSE,
            1,
            ("normative-fragment",),
        ),
    ),
)
def test_every_feedback_route_is_reachable(
    expected_route: FeedbackRoute,
    relationship: ConformanceRelationshipType,
    kind: ObservationKind,
    outcome: ObservationOutcome,
    attempt_count: int,
    normative_refs: tuple[str, ...],
) -> None:
    result = route_feedback(
        (
            ConformanceRelationship(
                observation_id="observation-1",
                claim_identity=CLAIM_ID,
                claim_path="/responses/200/status_code",
                operation_ref="GET /ping",
                kind=kind,
                outcome=outcome,
                attempt_count=attempt_count,
                claim_kind="operation",
                relationship=relationship,
                normative_value="200",
                observed_value="201",
                normative_evidence_refs=normative_refs,
            ),
        )
    )

    assert result is expected_route


def test_high_risk_semantic_claims_route_contradictions_to_provider_clarification() -> None:
    relationship = ConformanceRelationship(
        observation_id="observation-1",
        claim_identity="amount-direction:charge",
        claim_path="/direction",
        operation_ref="GET /ping",
        kind=ObservationKind.RESPONSE_STATUS,
        outcome=ObservationOutcome.API_RESPONSE,
        attempt_count=1,
        claim_kind="amount_direction",
        relationship=ConformanceRelationshipType.CONTRADICTS,
        normative_value="debit",
        observed_value="credit",
        normative_evidence_refs=("normative-fragment",),
    )

    assert route_feedback((relationship,)) is FeedbackRoute.PROVIDER_CLARIFICATION


def test_ungrounded_normative_contradiction_routes_to_extraction_correction() -> None:
    contract = _contract()
    claim = contract.claims[0].model_copy(update={"evidence": ()})
    contract = contract.model_copy(update={"claims": (claim,)})

    assessment = ContractConformance().assess(
        contract, _bundle(contract), provider="demo", product="backend"
    )

    assert assessment.route == "extraction_correction"
    assert ContractConformance().propose(assessment, now=NOW) == ()


def test_observation_allowlist_rejects_high_risk_semantic_claim() -> None:
    contract = _contract(claim_kind="security", value={"name": "auth", "type": "200"})

    with pytest.raises(ConformanceInputError, match="does not belong"):
        ContractConformance().assess(
            contract,
            _bundle(
                contract,
                path="/type",
                expected="200",
                observed="201",
            ),
            provider="demo",
            product="backend",
        )


def test_absent_observed_field_does_not_remove_or_change_requiredness() -> None:
    contract = _contract(
        claim_kind="schema",
        value={
            "name": "PingResponse",
            "fields": [
                {"name": "id", "type": "string", "required": True},
            ],
        },
    )
    service = ContractConformance()

    assessment = service.assess(
        contract,
        _bundle(
            contract,
            path="/fields/id/name",
            expected="id",
            observed=False,
            kind=ObservationKind.RESPONSE_FIELD,
        ),
        provider="demo",
        product="backend",
    )

    assert assessment.relationships[0].relationship == "contradicts"
    assert assessment.route == "provider_clarification"
    assert service.propose(assessment, now=NOW) == ()
    assert contract.claims[0].value["fields"][0]["required"] is True


def test_approval_identity_is_separate_from_producer_and_runner() -> None:
    contract = _contract()
    service = ContractConformance()
    assessment = service.assess(
        contract, _bundle(contract), provider="demo", product="backend"
    )
    proposal = service.propose(assessment, now=NOW)[0]

    with pytest.raises(ValueError, match="producer or runner"):
        _approved(proposal, expires_at=NOW + timedelta(days=30), approver="runner")


def test_compose_applies_only_exact_scoped_active_amendment_and_retains_authority_lineage() -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    amendment = _approved(
        service.propose(assessment, now=NOW)[0],
        expires_at=NOW + timedelta(days=30),
    )

    effective = service.compose(release, (amendment,), target=_scope(), now=NOW)

    assert effective.normative_contract == contract
    assert effective.normative_contract is contract
    assert effective.applied_amendment_ids == ("amendment-1",)
    value = next(
        item
        for item in effective.values
        if item.claim_identity == CLAIM_ID
        and item.claim_path == "/responses/200/status_code"
    )
    assert value.normative_value == "200"
    assert value.effective_value == "201"
    assert value.authority == "observed_override"
    assert value.amendment_id == "amendment-1"
    assert value.observation_evidence_refs == ("observation-fragment",)
    assert value.normative_evidence_refs == ("normative-fragment",)
    assert value.approved_by.id == "reviewer"


def test_compose_rejects_a_normative_release_with_a_stale_contract_digest() -> None:
    contract = _contract()
    release = _release(contract).model_copy(
        update={"base": _release(contract).base.model_copy(update={"contract_digest": "0" * 64})}
    )

    with pytest.raises(ConformanceInputError, match="contract digest is stale"):
        ContractConformance().compose(release, (), target=_scope(), now=NOW)


def test_compose_rejects_duplicate_amendment_ids() -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    amendment = _approved(
        service.propose(assessment, now=NOW)[0], expires_at=NOW + timedelta(days=1)
    )

    with pytest.raises(ConformanceInputError, match="duplicate amendment ids"):
        service.compose(release, (amendment, amendment), target=_scope(), now=NOW)


def test_compose_rejects_supersession_that_changes_target() -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    first_proposal = service.propose(assessment, now=NOW)[0]
    second_proposal = first_proposal.model_copy(
        update={
            "proposal_id": "proposal-2",
            "target": first_proposal.target.model_copy(
                update={"claim_path": "/responses/200/description"}
            ),
            "normative_value": "OK",
            "proposed_value": "Changed",
        }
    )
    first = _approved(first_proposal, expires_at=NOW + timedelta(days=1))
    second = _approved(
        second_proposal, expires_at=NOW + timedelta(days=1)
    ).model_copy(update={"amendment_id": "amendment-2", "supersedes": "amendment-1"})

    with pytest.raises(ConformanceInputError, match="same scope and target"):
        service.compose(release, (first, second), target=_scope(), now=NOW)


def test_compose_skips_unsupported_normative_claims() -> None:
    contract = _contract().model_copy(
        update={
            "claims": (
                _contract().claims[0].model_copy(update={"status": ClaimStatus.MISSING}),
            )
        }
    )

    effective = ContractConformance().compose(
        _release(contract), (), target=_scope(), now=NOW
    )

    assert effective.values == ()


def test_compose_classifies_expired_and_scope_mismatched_amendments() -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    proposal = service.propose(assessment, now=NOW)[0]
    expired = _approved(proposal, expires_at=NOW + timedelta(seconds=1))
    mismatch = _approved(
        proposal.model_copy(update={"scope": _scope(environment="production")}),
        expires_at=NOW + timedelta(days=1),
    ).model_copy(update={"amendment_id": "amendment-2"})

    effective = service.compose(
        release, (expired, mismatch), target=_scope(), now=NOW + timedelta(seconds=2)
    )

    assert effective.applied_amendment_ids == ()
    assert effective.expired_amendment_ids == ("amendment-1",)
    assert effective.inapplicable_amendment_ids == ("amendment-2",)


def test_compose_rejects_amendment_when_documentary_evidence_changes() -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    amendment = _approved(
        service.propose(assessment, now=NOW)[0],
        expires_at=NOW + timedelta(days=30),
    )
    changed_fragment = release.fragments[0].model_copy(
        update={
            "fragment_digest": "5" * 64,
            "normalized_excerpt": "Success returns a documented 2xx status.",
        }
    )
    changed_release = release.model_copy(update={"fragments": (changed_fragment,)})

    effective = service.compose(
        changed_release, (amendment,), target=_scope(), now=NOW
    )

    assert effective.applied_amendment_ids == ()
    assert effective.stale_amendment_ids == ("amendment-1",)


def test_compose_fails_closed_on_conflicting_same_scope_amendments() -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    first_proposal = service.propose(assessment, now=NOW)[0]
    second_proposal = first_proposal.model_copy(
        update={"proposal_id": "proposal-2", "proposed_value": "202"}
    )
    first = _approved(first_proposal, expires_at=NOW + timedelta(days=1))
    second = _approved(
        second_proposal, expires_at=NOW + timedelta(days=1)
    ).model_copy(update={"amendment_id": "amendment-2"})

    with pytest.raises(ConformanceInputError, match="conflicting active amendments"):
        service.compose(release, (first, second), target=_scope(), now=NOW)


def test_compose_applies_explicit_supersession_without_last_write_wins() -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    first_proposal = service.propose(assessment, now=NOW)[0]
    second_proposal = first_proposal.model_copy(
        update={"proposal_id": "proposal-2", "proposed_value": "202"}
    )
    first = _approved(first_proposal, expires_at=NOW + timedelta(days=1))
    second = _approved(
        second_proposal, expires_at=NOW + timedelta(days=1)
    ).model_copy(
        update={"amendment_id": "amendment-2", "supersedes": "amendment-1"}
    )

    effective = service.compose(
        release, (first, second), target=_scope(), now=NOW
    )

    assert effective.applied_amendment_ids == ("amendment-2",)
    assert effective.superseded_amendment_ids == ("amendment-1",)
    override = next(value for value in effective.values if value.amendment_id)
    assert override.effective_value == "202"


@pytest.mark.parametrize(
    ("amendment_update", "message"),
    (
        ({"supersedes": "missing"}, "supersedes unknown"),
        ({"supersedes": "amendment-1"}, "cannot supersede itself"),
    ),
)
def test_compose_rejects_invalid_active_supersession_references(
    amendment_update: dict[str, str], message: str
) -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    amendment = _approved(
        service.propose(assessment, now=NOW)[0], expires_at=NOW + timedelta(days=1)
    ).model_copy(update=amendment_update)

    with pytest.raises(ConformanceInputError, match=message):
        service.compose(release, (amendment,), target=_scope(), now=NOW)


def test_compose_marks_future_approval_as_stale_without_applying_it() -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    amendment = _approved(
        service.propose(assessment, now=NOW)[0], expires_at=NOW + timedelta(days=1)
    )
    future_approval = amendment.approval.model_copy(
        update={"approved_at": NOW + timedelta(seconds=1)}
    )
    amendment = amendment.model_copy(update={"approval": future_approval})

    effective = service.compose(release, (amendment,), target=_scope(), now=NOW)

    assert effective.applied_amendment_ids == ()
    assert effective.stale_amendment_ids == ("amendment-1",)


@pytest.mark.parametrize(
    ("bundle_update", "message"),
    (
        ({"policy_version": "conformance/v0"}, "unsupported conformance policy"),
        (
            {"base": NormativeBaseBinding(docset_id="demo-api", asset_id="asset-1", contract_digest="0" * 64)},
            "base contract digest is stale",
        ),
        (
            {"base": NormativeBaseBinding(docset_id="other-api", asset_id="asset-1", contract_digest=contract_digest(_contract()))},
            "docset does not match",
        ),
    ),
)
def test_assess_rejects_incompatible_bundle_base_bindings(
    bundle_update: dict[str, object], message: str
) -> None:
    contract = _contract()

    with pytest.raises(ConformanceInputError, match=message):
        ContractConformance().assess(
            contract,
            _bundle(contract).model_copy(update=bundle_update),
            provider="demo",
            product="backend",
        )


@pytest.mark.parametrize(
    ("contract_update", "observation_update", "message"),
    (
        ({}, {"claim_identity": "missing-claim"}, "unknown claim identity"),
        ({}, {"operation_ref": "POST /missing"}, "unknown operation reference"),
        ({}, {"expected": "201"}, "expected value does not match"),
        (
            {"claims": (_contract().claims[0].model_copy(update={"status": ClaimStatus.MISSING}),)},
            {},
            "not a supported normative claim",
        ),
    ),
)
def test_assess_rejects_invalid_observation_targets(
    contract_update: dict[str, object], observation_update: dict[str, object], message: str
) -> None:
    contract = _contract().model_copy(update=contract_update)
    bundle = _bundle(contract)
    observation = bundle.observations[0].model_copy(update=observation_update)

    with pytest.raises(ConformanceInputError, match=message):
        ContractConformance().assess(
            contract,
            bundle.model_copy(update={"observations": (observation,)}),
            provider="demo",
            product="backend",
        )


@pytest.mark.parametrize(
    "approval_update",
    (
        {"policy_version": "conformance/v0"},
        {"base_asset_id": "other-base"},
        {"assessment_id": "other-assessment"},
        {"observation_bundle_id": "other-bundle"},
        {"assessment_digest": "0" * 64},
        {"observation_bundle_digest": "0" * 64},
        {"base_contract_digest": "0" * 64},
        {"redaction_policy_version": "redaction/v0"},
    ),
)
def test_compose_marks_amendments_with_stale_approval_bindings(
    approval_update: dict[str, str],
) -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    amendment = _approved(
        service.propose(assessment, now=NOW)[0], expires_at=NOW + timedelta(days=1)
    )
    amendment = amendment.model_copy(
        update={"approval": amendment.approval.model_copy(update=approval_update)}
    )

    effective = service.compose(release, (amendment,), target=_scope(), now=NOW)

    assert effective.applied_amendment_ids == ()
    assert effective.stale_amendment_ids == ("amendment-1",)


@pytest.mark.parametrize(
    "mutation",
    ("policy", "proposal_digest", "unsupported_claim", "claim_kind", "claim_path"),
)
def test_compose_marks_stale_proposal_or_target_bindings(
    mutation: str,
) -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    amendment = _approved(
        service.propose(assessment, now=NOW)[0], expires_at=NOW + timedelta(days=1)
    )

    if mutation == "policy":
        proposal = amendment.proposal.model_copy(update={"policy_version": "conformance/v0"})
        amendment = amendment.model_copy(
            update={"proposal": proposal, "approval": amendment.approval.model_copy(
                update={"proposal_digest": canonical_digest(proposal)}
            )}
        )
    elif mutation == "proposal_digest":
        amendment = amendment.model_copy(
            update={"approval": amendment.approval.model_copy(update={"proposal_digest": "0" * 64})}
        )
    elif mutation == "unsupported_claim":
        changed_contract = contract.model_copy(
            update={
                "claims": (
                    contract.claims[0].model_copy(update={"status": ClaimStatus.MISSING}),
                )
            }
        )
        changed_release = _release(changed_contract)
        amendment = _rebind_amendment(amendment, changed_release)
        release = changed_release
    elif mutation == "claim_kind":
        changed_contract = contract.model_copy(
            update={"claims": (contract.claims[0].model_copy(update={"claim_kind": "schema"}),)}
        )
        changed_release = _release(changed_contract)
        amendment = _rebind_amendment(amendment, changed_release)
        release = changed_release
    else:
        amendment = _rebind_amendment(
            amendment,
            release,
            target=amendment.proposal.target.model_copy(
                update={"claim_path": "/responses/404/status_code"}
            ),
        )

    effective = service.compose(release, (amendment,), target=_scope(), now=NOW)

    assert effective.applied_amendment_ids == ()
    assert effective.stale_amendment_ids == ("amendment-1",)


def test_assess_rejects_an_unknown_claim_path_after_allowlist_validation() -> None:
    contract = _contract()

    with pytest.raises(ConformanceInputError, match="unknown claim path"):
        ContractConformance().assess(
            contract,
            _bundle(contract, path="/responses/404/status_code", expected="404"),
            provider="demo",
            product="backend",
        )


def test_assess_rejects_conflicting_attempt_values_within_one_observation() -> None:
    contract = _contract()
    bundle = _bundle(contract)
    observation = bundle.observations[0]
    facts = (
        SanitizedObservationFact(kind=ObservationKind.RESPONSE_STATUS, value="201"),
        SanitizedObservationFact(kind=ObservationKind.RESPONSE_STATUS, value="202"),
    )
    canonical_facts = json.dumps(
        [fact.model_dump(mode="json") for fact in facts],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    evidence = observation.evidence[0].model_copy(
        update={
            "sanitized_facts": facts,
            "digest": "sha256:" + hashlib.sha256(canonical_facts.encode()).hexdigest(),
        }
    )
    observation = observation.model_copy(
        update={
            "attempts": (
                observation.attempts[0],
                observation.attempts[0].model_copy(
                    update={"id": "attempt-2", "observed": "202"}
                ),
            ),
            "evidence": (evidence,),
        }
    )
    bundle = bundle.model_copy(update={"observations": (observation,)})

    with pytest.raises(ConformanceInputError, match="conflicting attempts"):
        ContractConformance().assess(
            contract, bundle, provider="demo", product="backend"
        )


def test_manual_observation_is_inconclusive_without_independent_replay_evidence() -> None:
    contract = _contract()
    assessment = ContractConformance().assess(
        contract,
        _bundle(contract, expected="200", observed="200", lineage=ObservationLineage.MANUAL),
        provider="demo",
        product="backend",
    )

    assert assessment.relationships[0].relationship is ConformanceRelationshipType.INCONCLUSIVE


def test_assess_rejects_conflicting_observations_for_one_scope_and_target() -> None:
    contract = _contract()
    first_bundle = _bundle(contract, observed="201")
    second_observation = _bundle(contract, observed="202").observations[0].model_copy(
        update={
            "id": "obs-2",
            "attempts": (
                _bundle(contract, observed="202").observations[0].attempts[0].model_copy(
                    update={"id": "attempt-2"}
                ),
            ),
            "evidence": (
                _bundle(contract, observed="202").observations[0].evidence[0].model_copy(
                    update={"fragment_id": "observation-fragment-2"}
                ),
            ),
        }
    )
    bundle = first_bundle.model_copy(
        update={"observations": (first_bundle.observations[0], second_observation)}
    )

    with pytest.raises(ConformanceInputError, match="conflicting observations"):
        ContractConformance().assess(
            contract, bundle, provider="demo", product="backend"
        )


def test_operation_success_observation_matches_the_documented_success_status() -> None:
    contract = _contract()
    assessment = ContractConformance().assess(
        contract,
        _bundle(
            contract,
            kind=ObservationKind.OPERATION_SUCCESS,
            expected="200",
            observed=True,
        ),
        provider="demo",
        product="backend",
    )

    assert assessment.relationships[0].relationship is ConformanceRelationshipType.CONFIRMS


def test_compose_requires_timezone_aware_composition_time() -> None:
    with pytest.raises(ConformanceInputError, match="composition time must include a timezone"):
        ContractConformance().compose(
            _release(_contract()), (), target=_scope(), now=NOW.replace(tzinfo=None)
        )


def test_compose_rejects_supersession_cycles() -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    proposal = service.propose(assessment, now=NOW)[0]
    first = _approved(proposal, expires_at=NOW + timedelta(days=1)).model_copy(
        update={"supersedes": "amendment-2"}
    )
    second = _approved(
        proposal.model_copy(update={"proposal_id": "proposal-2"}),
        expires_at=NOW + timedelta(days=1),
    ).model_copy(update={"amendment_id": "amendment-2", "supersedes": "amendment-1"})

    with pytest.raises(ConformanceInputError, match="supersession cycle"):
        service.compose(release, (first, second), target=_scope(), now=NOW)


def test_domain_observation_models_reject_non_reproducible_or_ambiguous_input() -> None:
    contract = _contract()
    payload = _bundle(contract).model_dump(mode="json")
    duplicate_attempt = json.loads(json.dumps(payload["observations"][0]["attempts"][0]))
    payload["observations"][0]["attempts"].append(duplicate_attempt)

    with pytest.raises(ValidationError, match="attempt ids must be unique within an observation"):
        ObservationBundle.model_validate(payload)

    payload = _bundle(contract).model_dump(mode="json")
    payload["observations"][0]["attempts"][0]["observed_at"] = "2026-08-02T10:01:00Z"
    with pytest.raises(ValidationError, match="outside the applicability window"):
        ObservationBundle.model_validate(payload)


def test_domain_models_require_unique_declared_targets_and_timezone_aware_scope() -> None:
    target = {"claim_identity": CLAIM_ID, "claim_path": "/responses/200/status_code"}
    with pytest.raises(ValidationError, match="declared material claims must be unique"):
        SuiteIdentity(id="runner", version="suite/1", declared_material_claims=(target, target))

    payload = _scope().model_dump(mode="json")
    payload["observed_from"] = "2026-08-02T09:00:00"
    with pytest.raises(ValidationError, match="observation times must include a timezone"):
        ApplicabilityEnvelope.model_validate(payload)


def test_compose_rejects_stale_release_and_duplicate_amendment_ids() -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    amendment = _approved(
        service.propose(assessment, now=NOW)[0], expires_at=NOW + timedelta(days=1)
    )

    with pytest.raises(ConformanceInputError, match="contract digest is stale"):
        service.compose(
            release.model_copy(
                update={"base": release.base.model_copy(update={"contract_digest": "0" * 64})}
            ),
            (),
            target=_scope(),
            now=NOW,
        )
    with pytest.raises(ConformanceInputError, match="duplicate amendment ids"):
        service.compose(release, (amendment, amendment), target=_scope(), now=NOW)


@pytest.mark.parametrize(
    ("proposal_update", "approval_update"),
    (
        ({"policy_version": "conformance/v0"}, {}),
        ({}, {"proposal_digest": "0" * 64}),
    ),
)
def test_compose_marks_proposal_or_approval_digest_drift_stale(
    proposal_update: dict[str, str], approval_update: dict[str, str]
) -> None:
    contract = _contract()
    release = _release(contract)
    service = ContractConformance()
    assessment = service.assess(
        release, _bundle(contract), provider="demo", product="backend"
    )
    amendment = _approved(
        service.propose(assessment, now=NOW)[0], expires_at=NOW + timedelta(days=1)
    )
    proposal = amendment.proposal.model_copy(update=proposal_update)
    amendment = amendment.model_copy(
        update={
            "proposal": proposal,
            "approval": amendment.approval.model_copy(update=approval_update),
        }
    )

    assert service.compose(release, (amendment,), target=_scope(), now=NOW).stale_amendment_ids == (
        "amendment-1",
    )


def test_assess_rejects_conflicting_attempts_and_marks_manual_reports_inconclusive() -> None:
    contract = _contract()
    bundle = _bundle(contract)
    first = bundle.observations[0]
    conflicting = first.model_copy(
        update={
            "attempts": (
                first.attempts[0],
                first.attempts[0].model_copy(update={"id": "attempt-2", "observed": "202"}),
            )
        }
    )
    with pytest.raises(ConformanceInputError, match="conflicting attempts"):
        ContractConformance().assess(
            contract,
            bundle.model_copy(update={"observations": (conflicting,)}),
            provider="demo",
            product="backend",
        )

    manual = _bundle(contract, observed="200", lineage=ObservationLineage.MANUAL)
    assessment = ContractConformance().assess(
        contract, manual, provider="demo", product="backend"
    )
    assert assessment.relationships[0].relationship is ConformanceRelationshipType.INCONCLUSIVE


def test_domain_models_fail_closed_on_release_scope_and_observation_integrity() -> None:
    contract = _contract()
    release_payload = _release(contract).model_dump(mode="json")
    release_payload["base"]["docset_id"] = "other-docset"
    with pytest.raises(ValidationError, match="docset does not match"):
        NormativeRelease.model_validate(release_payload)

    release_payload = _release(contract).model_dump(mode="json")
    release_payload["fragments"].append(release_payload["fragments"][0])
    with pytest.raises(ValidationError, match="fragment ids must be unique"):
        NormativeRelease.model_validate(release_payload)

    scope_payload = _scope().model_dump(mode="json")
    scope_payload["observed_until"] = "2026-08-02T08:59:00Z"
    with pytest.raises(ValidationError, match="must not precede"):
        ApplicabilityEnvelope.model_validate(scope_payload)

    scope_payload = _scope().model_dump(mode="json")
    scope_payload["feature_flags"] = ["one", "one"]
    with pytest.raises(ValidationError, match="feature_flags must be unique"):
        ApplicabilityEnvelope.model_validate(scope_payload)

    bundle_payload = _bundle(contract).model_dump(mode="json")
    bundle_payload["observations"][0]["evidence"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="facts do not match evidence digest"):
        ObservationBundle.model_validate(bundle_payload)

    bundle_payload = _bundle(contract).model_dump(mode="json")
    bundle_payload["observations"][0]["attempts"][0]["outcome"] = "timeout"
    with pytest.raises(ValidationError, match="non-API outcomes cannot carry"):
        ObservationBundle.model_validate(bundle_payload)


def test_suite_coverage_is_separate_from_documentary_support() -> None:
    contract = _contract()
    bundle = _bundle(contract).model_copy(
        update={
            "suite": SuiteIdentity(
                id="runner",
                version="suite/1",
                declared_material_claims=(
                    {
                        "claim_identity": CLAIM_ID,
                        "claim_path": "/responses/200/status_code",
                    },
                ),
            )
        }
    )

    assessment = ContractConformance().assess(
        contract, bundle, provider="demo", product="backend"
    )

    assert assessment.coverage.suite_id == "runner"
    assert assessment.coverage.declared_claim_count == 1
    assert assessment.coverage.suite_coverage_ratio < 1.0
    assert contract.claims[0].status is ClaimStatus.SUPPORTED


def test_inconclusive_target_remains_untested_and_open_after_other_amendment() -> None:
    contract = _contract()
    operation = contract.operations[0].model_copy(
        update={
            "responses": (
                *contract.operations[0].responses,
                Response(status_code="202", description="Accepted"),
            )
        }
    )
    contract = contract.model_copy(
        update={
            "operations": (operation,),
            "claims": (
                contract.claims[0].model_copy(
                    update={
                        "value": operation.model_dump(
                            mode="json", exclude={"evidence"}
                        )
                    }
                ),
            ),
        }
    )
    release = _release(contract)
    service = ContractConformance()
    bundle = _bundle(contract)
    primary = bundle.observations[0]
    inconclusive = primary.model_copy(
        update={
            "id": "obs-timeout",
            "kind": ObservationKind.RESPONSE_STATUS,
            "claim_path": "/responses/202/status_code",
            "expected": "202",
            "attempts": (
                primary.attempts[0].model_copy(
                    update={
                        "id": "attempt-timeout",
                        "outcome": ObservationOutcome.TIMEOUT,
                        "observed": None,
                    }
                ),
            ),
            "evidence": (
                primary.evidence[0].model_copy(
                    update={
                        "fragment_id": "timeout-fragment",
                        "digest": "sha256:" + "3" * 64,
                        "sanitized_facts": (),
                    }
                ),
            ),
        }
    )
    bundle = bundle.model_copy(update={"observations": (primary, inconclusive)})
    assessment = service.assess(
        release, bundle, provider="demo", product="backend"
    )
    proposal = service.propose(assessment, now=NOW)[0]

    assert MaterialClaimReference(
        claim_identity=CLAIM_ID,
        claim_path="/responses/202/status_code",
    ) not in proposal.assessed_targets

    effective = service.compose(
        release,
        (_approved(proposal, expires_at=NOW + timedelta(days=30)),),
        target=_scope(),
        now=NOW,
    )

    assert effective.untested_material_claim_count > 0
    assert effective.open_discrepancy_count > 0


def test_sanitized_evidence_facts_are_digest_bound_and_raw_bodies_are_rejected() -> None:
    facts = (
        SanitizedObservationFact(
            kind=ObservationKind.RESPONSE_STATUS,
            value="201",
        ),
    )
    canonical = '[{"kind":"response_status","value":"201"}]'
    digest = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

    evidence = ObservationEvidence(
        fragment_id="safe-fact",
        digest=digest,
        media_type="application/json",
        size_bytes=len(canonical),
        sanitized_facts=facts,
    )

    assert evidence.sanitized_facts == facts
    with pytest.raises(ValueError, match="allowlisted JSON type"):
        SanitizedObservationFact(
            kind=ObservationKind.RESPONSE_JSON_TYPE,
            value='{"raw":"body"}',
        )


def test_observation_evidence_fact_must_match_api_attempt_value() -> None:
    payload = _bundle(_contract()).model_dump(mode="json")
    facts = [{"kind": "response_status", "value": "200"}]
    canonical = json.dumps(
        facts, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    payload["observations"][0]["evidence"][0]["sanitized_facts"] = facts
    payload["observations"][0]["evidence"][0]["digest"] = (
        "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    )

    with pytest.raises(ValidationError, match="must match the observed API value"):
        ObservationBundle.model_validate(payload)
