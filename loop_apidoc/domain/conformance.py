from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from loop_apidoc.domain.base import FrozenModel
from loop_apidoc.domain.evidence import ClaimEvidenceRelationship, EvidenceFragment
from loop_apidoc.domain.models import GroundedApiContract


Digest = str


class ObservationKind(str, Enum):
    OPERATION_SUCCESS = "operation_success"
    RESPONSE_STATUS = "response_status"
    RESPONSE_FIELD = "response_field"
    RESPONSE_JSON_TYPE = "response_json_type"


class ObservationOutcome(str, Enum):
    API_RESPONSE = "api_response"
    NETWORK_FAILURE = "network_failure"
    DNS_FAILURE = "dns_failure"
    PROXY_FAILURE = "proxy_failure"
    GATEWAY_FAILURE = "gateway_failure"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    HARNESS_FAILURE = "harness_failure"
    FIXTURE_FAILURE = "fixture_failure"


class ObservationLineage(str, Enum):
    INDEPENDENT = "independent"
    CONTRACT_DERIVED = "contract_derived"
    MANUAL = "manual"


class ConformanceRelationshipType(str, Enum):
    CONFIRMS = "confirms"
    CONTRADICTS = "contradicts"
    INCONCLUSIVE = "inconclusive"
    OUT_OF_SCOPE = "out_of_scope"


class FeedbackRoute(str, Enum):
    CLOSED_NO_CHANGE = "closed_no_change"
    NEEDS_EVIDENCE = "needs_evidence"
    PROVIDER_CLARIFICATION = "provider_clarification"
    IMPLEMENTATION_CORRECTION = "implementation_correction"
    ENVIRONMENT_CONFIGURATION_CORRECTION = "environment_configuration_correction"
    EXTRACTION_CORRECTION = "extraction_correction"
    PROVIDER_RUNTIME_REGRESSION_REVIEW = "provider_runtime_regression_review"
    AMENDMENT_PROPOSAL = "amendment_proposal"


class IdentityVersion(FrozenModel):
    id: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=200)


class MaterialClaimReference(FrozenModel):
    claim_identity: str = Field(min_length=1, max_length=500)
    claim_path: str = Field(max_length=1000)


class SuiteIdentity(IdentityVersion):
    declared_material_claims: tuple[MaterialClaimReference, ...] = Field(
        default=(), max_length=10_000
    )

    @model_validator(mode="after")
    def _unique_declared_claims(self) -> SuiteIdentity:
        targets = [
            (target.claim_identity, target.claim_path)
            for target in self.declared_material_claims
        ]
        if len(targets) != len(set(targets)):
            raise ValueError("declared material claims must be unique")
        return self


class NormativeBaseBinding(FrozenModel):
    docset_id: str = Field(min_length=1, max_length=200)
    asset_id: str = Field(min_length=1, max_length=240)
    contract_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")


class NormativeRelease(FrozenModel):
    """One immutable approved normative base and its documentary evidence graph."""

    base: NormativeBaseBinding
    contract: GroundedApiContract
    fragments: tuple[EvidenceFragment, ...] = ()
    relationships: tuple[ClaimEvidenceRelationship, ...] = ()

    @model_validator(mode="after")
    def _base_and_evidence_are_bound(self) -> NormativeRelease:
        if self.base.docset_id != self.contract.metadata.contract_id:
            raise ValueError("normative release docset does not match its contract")
        fragment_ids = {fragment.id for fragment in self.fragments}
        if len(fragment_ids) != len(self.fragments):
            raise ValueError("normative release fragment ids must be unique")
        unknown = sorted(
            {
                relationship.fragment_id
                for relationship in self.relationships
                if relationship.fragment_id not in fragment_ids
            }
        )
        if unknown:
            raise ValueError(
                f"normative relationship references unknown fragment: {unknown[0]}"
            )
        return self


class ApplicabilityEnvelope(FrozenModel):
    provider: str = Field(min_length=1, max_length=200)
    product: str = Field(min_length=1, max_length=200)
    api_version: str | None = Field(default=None, max_length=200)
    environment: str = Field(min_length=1, max_length=200)
    region: str | None = Field(default=None, max_length=200)
    endpoint_identity: str = Field(min_length=1, max_length=500)
    account_class: str | None = Field(default=None, max_length=200)
    feature_flags: tuple[str, ...] = Field(default=(), max_length=100)
    authentication_role: str = Field(min_length=1, max_length=200)
    client_version: str = Field(min_length=1, max_length=200)
    harness_version: str = Field(min_length=1, max_length=200)
    test_data_class: str = Field(min_length=1, max_length=200)
    observed_from: datetime
    observed_until: datetime

    @field_validator("observed_from", "observed_until")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation times must include a timezone")
        return value

    @model_validator(mode="after")
    def _ordered_window(self) -> ApplicabilityEnvelope:
        if self.observed_until < self.observed_from:
            raise ValueError("observed_until must not precede observed_from")
        if len(set(self.feature_flags)) != len(self.feature_flags):
            raise ValueError("feature_flags must be unique")
        return self


class ReplayRecipe(FrozenModel):
    executor: str = Field(min_length=1, max_length=200)
    steps: tuple[str, ...] = Field(min_length=1, max_length=50)


class ObservationAttempt(FrozenModel):
    id: str = Field(min_length=1, max_length=200)
    observed_at: datetime
    outcome: ObservationOutcome
    observed: Any = None
    error_class: str | None = Field(default=None, max_length=200)

    @field_validator("observed_at")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("attempt observed_at must include a timezone")
        return value


class SanitizedObservationFact(FrozenModel):
    kind: ObservationKind
    value: bool | int | float | str | None

    @model_validator(mode="after")
    def _value_is_allowlisted_for_kind(self) -> SanitizedObservationFact:
        _validate_observed_value(self.kind, self.value, label="sanitized fact")
        return self


class ObservationEvidence(FrozenModel):
    fragment_id: str = Field(min_length=1, max_length=200)
    digest: Digest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    media_type: Literal["application/json", "text/plain"]
    size_bytes: int = Field(ge=0, le=1024 * 1024)
    sanitized_facts: tuple[SanitizedObservationFact, ...] = Field(
        default=(), max_length=1000
    )

    @model_validator(mode="after")
    def _facts_match_declared_digest(self) -> ObservationEvidence:
        # Empty facts remain compatible with the v1 normalized-bundle adapter. When
        # facts are carried here, Core can verify them without retaining raw traffic.
        if not self.sanitized_facts:
            return self
        payload = json.dumps(
            [fact.model_dump(mode="json") for fact in self.sanitized_facts],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        expected = "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if self.digest != expected:
            raise ValueError("sanitized observation facts do not match evidence digest")
        return self


class ImplementationObservation(FrozenModel):
    id: str = Field(min_length=1, max_length=200)
    kind: ObservationKind
    operation_ref: str = Field(min_length=1, max_length=500)
    claim_identity: str = Field(min_length=1, max_length=500)
    claim_path: str = Field(max_length=1000)
    expected: Any
    probe_digest: Digest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    fixture_digest: Digest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    lineage: ObservationLineage
    replay: ReplayRecipe
    attempts: tuple[ObservationAttempt, ...] = Field(min_length=1, max_length=20)
    evidence: tuple[ObservationEvidence, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _unique_attempts(self) -> ImplementationObservation:
        ids = [attempt.id for attempt in self.attempts]
        if len(ids) != len(set(ids)):
            raise ValueError("attempt ids must be unique within an observation")
        _validate_expected_value(self.kind, self.expected)
        for attempt in self.attempts:
            if attempt.outcome is ObservationOutcome.API_RESPONSE:
                _validate_observed_value(
                    self.kind, attempt.observed, label="observed API value"
                )
            elif attempt.observed is not None:
                raise ValueError("non-API outcomes cannot carry an observed value")
        if any(
            attempt.outcome is ObservationOutcome.API_RESPONSE
            for attempt in self.attempts
        ) and any(not fragment.sanitized_facts for fragment in self.evidence):
            raise ValueError(
                "API-response evidence requires digest-bound sanitized facts"
            )
        api_values = {
            _json_scalar_key(attempt.observed)
            for attempt in self.attempts
            if attempt.outcome is ObservationOutcome.API_RESPONSE
        }
        if api_values:
            evidence_facts = {
                _json_scalar_key(fact.value)
                for fragment in self.evidence
                for fact in fragment.sanitized_facts
                if fact.kind is self.kind
            }
            unrelated = any(
                fact.kind is not self.kind
                for fragment in self.evidence
                for fact in fragment.sanitized_facts
            )
            if unrelated or evidence_facts != api_values:
                raise ValueError(
                    "digest-bound evidence facts must match the observed API value"
                )
        return self


class ObservationBundle(FrozenModel):
    schema_version: Literal["implementation-observation-bundle/v1"]
    bundle_id: str = Field(min_length=1, max_length=200)
    base: NormativeBaseBinding
    policy_version: Literal["conformance/v1"]
    redaction_policy_version: Literal["redaction/v1"]
    producer: IdentityVersion
    runner: IdentityVersion
    suite: SuiteIdentity | None = None
    applicability: ApplicabilityEnvelope
    observations: tuple[ImplementationObservation, ...] = Field(
        min_length=1, max_length=1000
    )

    @model_validator(mode="after")
    def _unique_ids_and_times(self) -> ObservationBundle:
        observation_ids = [item.id for item in self.observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation ids must be unique")
        attempt_ids = [
            attempt.id
            for observation in self.observations
            for attempt in observation.attempts
        ]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("attempt ids must be unique across the bundle")
        evidence_fragment_ids = [
            fragment.fragment_id
            for observation in self.observations
            for fragment in observation.evidence
        ]
        if len(evidence_fragment_ids) != len(set(evidence_fragment_ids)):
            raise ValueError("evidence fragment ids must be unique across the bundle")
        for observation in self.observations:
            for attempt in observation.attempts:
                if not (
                    self.applicability.observed_from
                    <= attempt.observed_at
                    <= self.applicability.observed_until
                ):
                    raise ValueError(
                        f"attempt {attempt.id} falls outside the applicability window"
                    )
        if self.suite is not None and (
            self.suite.id != self.runner.id
            or self.suite.version != self.runner.version
        ):
            raise ValueError("suite identity must match the observation runner")
        return self


class ConformanceRelationship(FrozenModel):
    observation_id: str
    claim_identity: str
    claim_path: str
    operation_ref: str
    kind: ObservationKind
    outcome: ObservationOutcome | None = None
    attempt_count: int = Field(default=1, ge=1, le=20)
    claim_kind: str | None = None
    relationship: ConformanceRelationshipType
    normative_value: Any = None
    observed_value: Any = None
    evidence_refs: tuple[str, ...] = ()
    normative_evidence_refs: tuple[str, ...] = ()
    reason: str | None = None


class ConformanceCoverage(FrozenModel):
    material_claim_count: int = Field(ge=0)
    assessed_claim_count: int = Field(ge=0)
    confirmed_claim_count: int = Field(ge=0)
    conformance_ratio: float = Field(ge=0.0, le=1.0)
    declared_claim_count: int = Field(default=0, ge=0)
    suite_coverage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    suite_id: str | None = None
    suite_version: str


class BoundedVerification(FrozenModel):
    verified: bool
    applicability: ApplicabilityEnvelope
    as_of: datetime
    suite_version: str
    reasons: tuple[str, ...] = ()


class FeedbackAssessment(FrozenModel):
    schema_version: Literal["feedback-assessment/v1"] = "feedback-assessment/v1"
    assessment_id: str
    base: NormativeBaseBinding
    normative_release_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    observation_bundle_id: str
    observation_bundle_digest: Digest
    policy_version: str
    redaction_policy_version: str
    producer: IdentityVersion
    runner: IdentityVersion
    applicability: ApplicabilityEnvelope
    relationships: tuple[ConformanceRelationship, ...]
    route: FeedbackRoute
    coverage: ConformanceCoverage
    open_discrepancy_count: int = Field(ge=0)
    fully_verified: BoundedVerification


class CompatibilityAmendmentProposal(FrozenModel):
    schema_version: Literal["compatibility-amendment-proposal/v1"] = (
        "compatibility-amendment-proposal/v1"
    )
    proposal_id: str = Field(min_length=1, max_length=240)
    base: NormativeBaseBinding
    normative_release_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    assessment_id: str = Field(min_length=1, max_length=240)
    assessment_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    observation_bundle_id: str = Field(min_length=1, max_length=200)
    observation_bundle_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: str = Field(min_length=1, max_length=200)
    redaction_policy_version: str = Field(min_length=1, max_length=200)
    target: MaterialClaimReference
    claim_kind: str | None = Field(default=None, max_length=200)
    normative_value: Any = None
    proposed_value: Any = None
    scope: ApplicabilityEnvelope
    observation_ids: tuple[str, ...] = Field(min_length=1, max_length=1000)
    normative_evidence_refs: tuple[str, ...] = Field(default=(), max_length=1000)
    observation_evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=1000)
    producer: IdentityVersion
    runner: IdentityVersion
    assessed_targets: tuple[MaterialClaimReference, ...] = ()
    confirmed_targets: tuple[MaterialClaimReference, ...] = ()
    contradicted_targets: tuple[MaterialClaimReference, ...] = ()
    conformance_coverage: ConformanceCoverage | None = None
    created_at: datetime
    requires_human_review: Literal[True] = True

    @field_validator("created_at")
    @classmethod
    def _created_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("proposal created_at must include a timezone")
        return value


class AmendmentApproval(FrozenModel):
    approval_id: str = Field(min_length=1, max_length=240)
    approved_by: IdentityVersion
    approved_at: datetime
    base_asset_id: str = Field(min_length=1, max_length=240)
    assessment_id: str = Field(min_length=1, max_length=240)
    observation_bundle_id: str = Field(min_length=1, max_length=200)
    proposal_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    assessment_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    observation_bundle_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    base_contract_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: str = Field(min_length=1, max_length=200)
    redaction_policy_version: str = Field(min_length=1, max_length=200)

    @field_validator("approved_at")
    @classmethod
    def _approved_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approval time must include a timezone")
        return value


class CompatibilityAmendment(FrozenModel):
    schema_version: Literal["compatibility-amendment/v1"] = (
        "compatibility-amendment/v1"
    )
    amendment_id: str = Field(min_length=1, max_length=240)
    proposal: CompatibilityAmendmentProposal
    approval: AmendmentApproval
    expires_at: datetime
    revalidation_triggers: tuple[str, ...] = Field(default=(), max_length=100)
    supersedes: str | None = Field(default=None, max_length=240)

    @field_validator("expires_at")
    @classmethod
    def _expires_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("amendment expiry must include a timezone")
        return value

    @model_validator(mode="after")
    def _approval_is_independent_and_bound(self) -> CompatibilityAmendment:
        identities = {self.proposal.producer.id, self.proposal.runner.id}
        if self.approval.approved_by.id in identities:
            raise ValueError(
                "amendment approver cannot be the feedback producer or runner"
            )
        if self.expires_at <= self.approval.approved_at:
            raise ValueError("amendment expiry must follow approval")
        if self.approval.approved_at < self.proposal.created_at:
            raise ValueError("amendment approval must not precede its proposal")
        if self.approval.approved_at < self.proposal.scope.observed_until:
            raise ValueError("amendment approval must follow observation completion")
        if len(set(self.revalidation_triggers)) != len(self.revalidation_triggers):
            raise ValueError("revalidation triggers must be unique")
        return self


class EffectiveValueAuthority(str, Enum):
    NORMATIVE = "normative"
    OBSERVED_OVERRIDE = "observed_override"


class EffectiveValue(FrozenModel):
    target: MaterialClaimReference
    claim_kind: str | None = None
    normative_value: Any = None
    effective_value: Any = None
    authority: EffectiveValueAuthority
    normative_evidence_refs: tuple[str, ...] = ()
    amendment_id: str | None = None
    observation_evidence_refs: tuple[str, ...] = ()
    approval_id: str | None = None
    approved_by: IdentityVersion | None = None

    @property
    def claim_identity(self) -> str:
        return self.target.claim_identity

    @property
    def claim_path(self) -> str:
        return self.target.claim_path


class EffectiveContract(FrozenModel):
    schema_version: Literal["effective-contract/v1"] = "effective-contract/v1"
    effective_contract_id: str = Field(min_length=1, max_length=240)
    base: NormativeBaseBinding
    target: ApplicabilityEnvelope
    as_of: datetime
    valid_until: datetime | None = None
    normative_contract: GroundedApiContract
    values: tuple[EffectiveValue, ...]
    applied_amendment_ids: tuple[str, ...] = ()
    superseded_amendment_ids: tuple[str, ...] = ()
    expired_amendment_ids: tuple[str, ...] = ()
    inapplicable_amendment_ids: tuple[str, ...] = ()
    stale_amendment_ids: tuple[str, ...] = ()
    conformance_coverage: ConformanceCoverage
    untested_material_claim_count: int = Field(ge=0)
    unresolved_contradiction_count: int = Field(ge=0)
    open_discrepancy_count: int = Field(default=0, ge=0)

    @field_validator("as_of")
    @classmethod
    def _as_of_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("effective contract as_of must include a timezone")
        return value

    @field_validator("valid_until")
    @classmethod
    def _valid_until_has_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("effective contract validity must include a timezone")
        return value


_JSON_TYPES = {"null", "boolean", "number", "string", "array", "object"}


def _json_scalar_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_observed_value(
    kind: ObservationKind, value: Any, *, label: str
) -> None:
    if kind is ObservationKind.OPERATION_SUCCESS:
        valid = type(value) is bool
        expected = "a boolean"
    elif kind is ObservationKind.RESPONSE_STATUS:
        valid = isinstance(value, str) and len(value) == 3 and value.isascii() and value.isdigit()
        expected = "a three-digit status string"
    elif kind is ObservationKind.RESPONSE_FIELD:
        valid = type(value) is bool
        expected = "a field-presence boolean"
    else:
        valid = isinstance(value, str) and value in _JSON_TYPES
        expected = "an allowlisted JSON type"
    if not valid:
        raise ValueError(f"{label} for {kind.value} must be {expected}")


def _validate_expected_value(kind: ObservationKind, value: Any) -> None:
    if kind is ObservationKind.OPERATION_SUCCESS:
        valid = (
            isinstance(value, str)
            and len(value) == 3
            and value.isascii()
            and value.isdigit()
            and value.startswith("2")
        )
        expected = "a documented 2xx status string"
    elif kind is ObservationKind.RESPONSE_FIELD:
        valid = isinstance(value, str) and bool(value.strip())
        expected = "the documented field name"
    else:
        _validate_observed_value(kind, value, label="expected value")
        return
    if not valid:
        raise ValueError(f"expected value for {kind.value} must be {expected}")


def normative_release_digest(release: NormativeRelease) -> str:
    payload = {
        "contract": release.contract.model_dump(mode="json"),
        "fragments": [fragment.model_dump(mode="json") for fragment in release.fragments],
        "relationships": [
            relationship.model_dump(mode="json")
            for relationship in release.relationships
        ],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
