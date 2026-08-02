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
from loop_apidoc.domain.conformance import (
    AmendmentApproval,
    ApplicabilityEnvelope,
    CompatibilityAmendment,
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
