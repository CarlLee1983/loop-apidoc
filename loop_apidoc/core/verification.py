from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from loop_apidoc.core.models import ClaimProposal
from loop_apidoc.domain.claim_paths import ClaimPathError, claim_value_at
from loop_apidoc.domain.evidence import (
    ClaimEvidenceRelationship,
    ClaimSupportProposal,
    EvidenceBundle,
    EvidenceFragment,
    FragmentPrecision,
    JsonPointerLocator,
    SupportRelationshipType,
    TableCellLocator,
    VerificationMethod,
    canonical_json,
    fragment_digest,
    make_relationship_id,
    normalize_excerpt,
)
from loop_apidoc.domain.identity import canonical_claim_identity
from loop_apidoc.domain.models import FrozenModel


class EvidenceViolation(FrozenModel):
    code: str
    message: str
    fragment_id: str | None = None


class _Comparison(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    INSUFFICIENT = "insufficient"


_ALLOWED_DERIVATIONS = frozenset(
    {
        ("canonical_json", "1"),
        ("normalize_boolean_token", "1"),
        ("unicode_nfc", "1"),
    }
)


def validate_evidence_bundle(
    bundle: EvidenceBundle,
) -> tuple[EvidenceViolation, ...]:
    violations: list[EvidenceViolation] = []
    artifact_ids = {artifact.id for artifact in bundle.artifacts}
    fragments: dict[str, EvidenceFragment] = {}
    for fragment in bundle.fragments:
        previous = fragments.get(fragment.id)
        if previous is not None and previous != fragment:
            violations.append(
                EvidenceViolation(
                    code="DUPLICATE_FRAGMENT_ID",
                    message="duplicate fragment ID represents different values",
                    fragment_id=fragment.id,
                )
            )
        else:
            fragments[fragment.id] = fragment
        if fragment.source_artifact_id not in artifact_ids:
            violations.append(
                EvidenceViolation(
                    code="SOURCE_ARTIFACT_NOT_FOUND",
                    message="fragment references an unknown source artifact",
                    fragment_id=fragment.id,
                )
            )
        if (
            fragment.normalized_excerpt is not None
            and fragment_digest(fragment.normalized_excerpt)
            != fragment.fragment_digest
        ):
            violations.append(
                EvidenceViolation(
                    code="FRAGMENT_DIGEST_MISMATCH",
                    message="fragment digest does not match normalized excerpt",
                    fragment_id=fragment.id,
                )
            )

    for fragment in fragments.values():
        parent_id = fragment.parent_fragment_id
        if parent_id is None:
            continue
        parent = fragments.get(parent_id)
        if parent is None:
            violations.append(
                EvidenceViolation(
                    code="PARENT_FRAGMENT_NOT_FOUND",
                    message="fragment parent does not exist",
                    fragment_id=fragment.id,
                )
            )
        elif parent.source_artifact_id != fragment.source_artifact_id:
            violations.append(
                EvidenceViolation(
                    code="PARENT_ARTIFACT_MISMATCH",
                    message="fragment parent belongs to a different source artifact",
                    fragment_id=fragment.id,
                )
            )

    for fragment in fragments.values():
        visited: set[str] = set()
        current: EvidenceFragment | None = fragment
        while current is not None and current.parent_fragment_id is not None:
            if current.id in visited:
                violations.append(
                    EvidenceViolation(
                        code="FRAGMENT_PARENT_CYCLE",
                        message="fragment parent chain contains a cycle",
                        fragment_id=fragment.id,
                    )
                )
                break
            visited.add(current.id)
            current = fragments.get(current.parent_fragment_id)

    unique = {
        (item.code, item.message, item.fragment_id): item for item in violations
    }
    return tuple(
        unique[key]
        for key in sorted(
            unique,
            key=lambda item: (
                item[2] or "",
                item[0],
                item[1],
            ),
        )
    )


def verify_claim_support(
    proposal: ClaimProposal,
    bundle: EvidenceBundle,
) -> tuple[ClaimEvidenceRelationship, ...]:
    identity = canonical_claim_identity(
        proposal.claim_kind,
        proposal.subject,
        proposal.predicate,
    )
    fragments = {fragment.id: fragment for fragment in bundle.fragments}
    relationships = tuple(
        _verify_one(
            claim_identity=identity,
            claim_kind=proposal.claim_kind,
            value=proposal.value,
            support=support,
            fragments=fragments,
        )
        for support in proposal.support_proposals
    )
    return tuple(
        sorted(
            relationships,
            key=lambda item: (
                item.claim_identity,
                item.claim_path,
                item.fragment_id,
                item.relationship.value,
                item.id,
            ),
        )
    )


def _verify_one(
    *,
    claim_identity: str,
    claim_kind: str,
    value: Any,
    support: ClaimSupportProposal,
    fragments: Mapping[str, EvidenceFragment],
) -> ClaimEvidenceRelationship:
    fragment = fragments.get(support.fragment_id)
    if fragment is None:
        return _insufficient_relationship(
            claim_identity=claim_identity,
            claim_value=value,
            support=support,
            fragment=None,
            reason_code="FRAGMENT_NOT_FOUND",
        )
    if fragment.precision is not FragmentPrecision.EXACT:
        return _insufficient_relationship(
            claim_identity=claim_identity,
            claim_value=value,
            support=support,
            fragment=fragment,
            reason_code="FRAGMENT_NOT_EXACT",
        )
    if fragment.normalized_excerpt is None:
        return _insufficient_relationship(
            claim_identity=claim_identity,
            claim_value=value,
            support=support,
            fragment=fragment,
            reason_code="FRAGMENT_NOT_MATERIALIZED",
        )
    if fragment_digest(fragment.normalized_excerpt) != fragment.fragment_digest:
        return _insufficient_relationship(
            claim_identity=claim_identity,
            claim_value=value,
            support=support,
            fragment=fragment,
            reason_code="FRAGMENT_DIGEST_MISMATCH",
        )
    try:
        claim_value = claim_value_at(claim_kind, value, support.claim_path)
    except ClaimPathError:
        return _insufficient_relationship(
            claim_identity=claim_identity,
            claim_value=value,
            support=support,
            fragment=fragment,
            reason_code="CLAIM_PATH_UNKNOWN",
        )

    if support.proposed_relationship is SupportRelationshipType.DERIVED_SUPPORT:
        reason = _invalid_derivation_reason(support, claim_value)
        if reason is not None:
            return _insufficient_relationship(
                claim_identity=claim_identity,
                claim_value=claim_value,
                support=support,
                fragment=fragment,
                reason_code=reason,
            )

    comparison, observed = _compare(claim_value, fragment, support.verification_method)
    if comparison is _Comparison.MATCH:
        return _relationship(
            claim_identity=claim_identity,
            claim_value=claim_value,
            support=support,
            fragment=fragment,
            relationship=support.proposed_relationship,
            observed_value=observed,
            reason_code=_match_reason(support.verification_method),
        )
    if comparison is _Comparison.MISMATCH and _is_value_bearing(fragment):
        return _relationship(
            claim_identity=claim_identity,
            claim_value=claim_value,
            support=support,
            fragment=fragment,
            relationship=SupportRelationshipType.CONTRADICTS,
            observed_value=observed,
            reason_code="EVIDENCE_VALUE_MISMATCH",
        )
    reason_code = (
        "FRAGMENT_NOT_VALUE_BEARING"
        if comparison is _Comparison.MISMATCH
        else "VERIFIER_INAPPLICABLE"
    )
    return _insufficient_relationship(
        claim_identity=claim_identity,
        claim_value=claim_value,
        support=support,
        fragment=fragment,
        reason_code=reason_code,
        observed_value=observed,
    )


def _compare(
    claim_value: Any,
    fragment: EvidenceFragment,
    method: VerificationMethod,
) -> tuple[_Comparison, Any]:
    has_semantic_value = fragment.semantic_role is not None
    if method is VerificationMethod.TABLE_CELL_MAPPING:
        if not isinstance(fragment.locator, TableCellLocator) or not has_semantic_value:
            return _Comparison.INSUFFICIENT, None
        return _compare_values(claim_value, fragment.semantic_value)
    if method is VerificationMethod.STRUCTURED_FIELD_PATH:
        if not isinstance(fragment.locator, JsonPointerLocator) or not has_semantic_value:
            return _Comparison.INSUFFICIENT, None
        return _compare_values(claim_value, fragment.semantic_value)
    if method in {
        VerificationMethod.ENUM_VALUE,
        VerificationMethod.SOURCE_FACT_COVERAGE,
    }:
        if has_semantic_value:
            return _compare_values(claim_value, fragment.semantic_value)
        if isinstance(claim_value, str):
            return _compare_values(
                normalize_excerpt(claim_value),
                fragment.normalized_excerpt,
            )
        return _Comparison.INSUFFICIENT, None
    if has_semantic_value:
        return _compare_values(claim_value, fragment.semantic_value)
    expected = (
        normalize_excerpt(claim_value)
        if isinstance(claim_value, str)
        else canonical_json(claim_value)
    )
    return _compare_values(expected, fragment.normalized_excerpt)


def _compare_values(expected: Any, observed: Any) -> tuple[_Comparison, Any]:
    relationship = (
        _Comparison.MATCH
        if canonical_json(expected) == canonical_json(observed)
        else _Comparison.MISMATCH
    )
    return relationship, observed


def _is_value_bearing(fragment: EvidenceFragment) -> bool:
    return (
        isinstance(fragment.locator, (TableCellLocator, JsonPointerLocator))
        or fragment.semantic_role is not None
    )


def _invalid_derivation_reason(
    support: ClaimSupportProposal,
    claim_value: Any,
) -> str | None:
    if not support.derivation_steps:
        return "DERIVATION_STEPS_REQUIRED"
    if any(
        (step.name, step.version) not in _ALLOWED_DERIVATIONS
        for step in support.derivation_steps
    ):
        return "DERIVATION_NOT_ALLOWED"
    if support.derivation_steps[-1].output_digest != _value_digest(claim_value):
        return "DERIVATION_OUTPUT_MISMATCH"
    return None


def _match_reason(method: VerificationMethod) -> str:
    return {
        VerificationMethod.EXACT_NORMALIZED_VALUE: "EXACT_VALUE_MATCH",
        VerificationMethod.TABLE_CELL_MAPPING: "TABLE_CELL_VALUE_MATCH",
        VerificationMethod.STRUCTURED_FIELD_PATH: "STRUCTURED_VALUE_MATCH",
        VerificationMethod.ENUM_VALUE: "ENUM_VALUE_MATCH",
        VerificationMethod.SOURCE_FACT_COVERAGE: "SOURCE_FACT_MATCH",
    }[method]


def _insufficient_relationship(
    *,
    claim_identity: str,
    claim_value: Any,
    support: ClaimSupportProposal,
    fragment: EvidenceFragment | None,
    reason_code: str,
    observed_value: Any = None,
) -> ClaimEvidenceRelationship:
    return _relationship(
        claim_identity=claim_identity,
        claim_value=claim_value,
        support=support,
        fragment=fragment,
        relationship=SupportRelationshipType.INSUFFICIENT,
        observed_value=observed_value,
        reason_code=reason_code,
    )


def _relationship(
    *,
    claim_identity: str,
    claim_value: Any,
    support: ClaimSupportProposal,
    fragment: EvidenceFragment | None,
    relationship: SupportRelationshipType,
    observed_value: Any,
    reason_code: str,
) -> ClaimEvidenceRelationship:
    evidence_value_digest = (
        _value_digest(observed_value) if observed_value is not None else None
    )
    payload = {
        "claim_identity": claim_identity,
        "claim_path": support.claim_path,
        "fragment_id": support.fragment_id,
        "relationship": relationship,
        "verification_method": support.verification_method,
        "claim_value_digest": _value_digest(claim_value),
        "evidence_value_digest": evidence_value_digest,
        "observed_value": observed_value,
        "reason_code": reason_code,
        "derivation_steps": support.derivation_steps,
    }
    return ClaimEvidenceRelationship(
        id=make_relationship_id(payload),
        **payload,
    )


def _value_digest(value: Any) -> str:
    return fragment_digest(canonical_json(value))

