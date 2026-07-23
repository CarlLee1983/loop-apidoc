from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from loop_apidoc.core.models import ClaimProposal
from loop_apidoc.domain.claim_paths import ClaimPathError, claim_value_at, escape_segment
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
        ("openapi_method_from_pointer", "1"),
        ("openapi_path_from_pointer", "1"),
        ("openapi_response_status_from_pointer", "1"),
        ("openapi_schema_name_from_ref", "1"),
        ("openapi_request_schema_name_from_ref", "1"),
        ("openapi_request_body_property_name_from_pointer", "1"),
        ("openapi_request_body_property_required_from_schema_pointer", "1"),
        ("openapi_request_body_ref_property_name_from_fragments", "1"),
        ("openapi_request_body_ref_property_required_from_fragments", "1"),
        ("openapi_schema_ref_property_name_from_fragments", "1"),
        ("openapi_schema_ref_property_type_from_fragments", "1"),
        ("openapi_schema_ref_property_required_from_fragments", "1"),
        ("openapi_schema_two_hop_ref_property_name_from_fragments", "1"),
        ("openapi_schema_two_hop_ref_property_type_from_fragments", "1"),
        ("openapi_schema_two_hop_ref_property_required_from_fragments", "1"),
        ("openapi_schema_name_from_pointer", "1"),
        ("openapi_schema_property_name_from_pointer", "1"),
        ("openapi_schema_property_type_from_pointer", "1"),
        ("openapi_schema_property_required_from_schema_pointer", "1"),
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
    context_fragments: list[EvidenceFragment] = []
    for context_fragment_id in support.context_fragment_ids:
        context_fragment = fragments.get(context_fragment_id)
        if context_fragment is None:
            return _insufficient_relationship(
                claim_identity=claim_identity,
                claim_value=value,
                support=support,
                fragment=fragment,
                reason_code="CONTEXT_FRAGMENT_NOT_FOUND",
            )
        if context_fragment.precision is not FragmentPrecision.EXACT:
            return _insufficient_relationship(
                claim_identity=claim_identity,
                claim_value=value,
                support=support,
                fragment=fragment,
                reason_code="CONTEXT_FRAGMENT_NOT_EXACT",
            )
        if context_fragment.normalized_excerpt is None:
            return _insufficient_relationship(
                claim_identity=claim_identity,
                claim_value=value,
                support=support,
                fragment=fragment,
                reason_code="CONTEXT_FRAGMENT_NOT_MATERIALIZED",
            )
        if (
            fragment_digest(context_fragment.normalized_excerpt)
            != context_fragment.fragment_digest
        ):
            return _insufficient_relationship(
                claim_identity=claim_identity,
                claim_value=value,
                support=support,
                fragment=fragment,
                reason_code="CONTEXT_FRAGMENT_DIGEST_MISMATCH",
            )
        context_fragments.append(context_fragment)
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
        pointer_derivation = _openapi_pointer_derivation(
            support,
            fragment,
            tuple(context_fragments),
            claim_identity,
            claim_value,
            value,
        )
        if pointer_derivation is not None:
            observed_value, reason_code = pointer_derivation
            if reason_code is not None:
                return _insufficient_relationship(
                    claim_identity=claim_identity,
                    claim_value=claim_value,
                    support=support,
                    fragment=fragment,
                    reason_code=reason_code,
                    observed_value=observed_value,
                )
            return _relationship(
                claim_identity=claim_identity,
                claim_value=claim_value,
                support=support,
                fragment=fragment,
                relationship=SupportRelationshipType.DERIVED_SUPPORT,
                observed_value=observed_value,
                reason_code="OPENAPI_POINTER_DERIVATION_MATCH",
            )
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
    if method is VerificationMethod.CLAIM_BOUND_EXACT_REFERENCE:
        # A v1 reference has already bound this material claim path to this
        # digest-checked, exact fragment at the extraction boundary.  This is
        # deliberately distinct from an unstructured legacy page/line citation:
        # the latter remains insufficient because it does not name the claim it
        # is meant to support.
        return _Comparison.MATCH, None
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


def _openapi_pointer_derivation(
    support: ClaimSupportProposal,
    fragment: EvidenceFragment,
    context_fragments: tuple[EvidenceFragment, ...],
    claim_identity: str,
    claim_value: Any,
    operation_value: Any,
) -> tuple[Any, str | None] | None:
    """Verify the fixed OpenAPI pointer-to-operation-path mapping, if proposed."""
    pointer_steps = tuple(
        step
        for step in support.derivation_steps
        if (step.name, step.version)
        in {
            ("openapi_path_from_pointer", "1"),
            ("openapi_method_from_pointer", "1"),
            ("openapi_response_status_from_pointer", "1"),
            ("openapi_schema_name_from_ref", "1"),
            ("openapi_request_schema_name_from_ref", "1"),
            ("openapi_request_body_property_name_from_pointer", "1"),
            ("openapi_request_body_property_required_from_schema_pointer", "1"),
            ("openapi_request_body_ref_property_name_from_fragments", "1"),
            ("openapi_request_body_ref_property_required_from_fragments", "1"),
            ("openapi_schema_ref_property_name_from_fragments", "1"),
            ("openapi_schema_ref_property_type_from_fragments", "1"),
            ("openapi_schema_ref_property_required_from_fragments", "1"),
            ("openapi_schema_two_hop_ref_property_name_from_fragments", "1"),
            ("openapi_schema_two_hop_ref_property_type_from_fragments", "1"),
            ("openapi_schema_two_hop_ref_property_required_from_fragments", "1"),
            ("openapi_schema_name_from_pointer", "1"),
            ("openapi_schema_property_name_from_pointer", "1"),
            ("openapi_schema_property_type_from_pointer", "1"),
            ("openapi_schema_property_required_from_schema_pointer", "1"),
        }
    )
    if not pointer_steps:
        return None
    if len(support.derivation_steps) != 1 or len(pointer_steps) != 1:
        return None, "DERIVATION_CHAIN_INVALID"
    derivation = (pointer_steps[0].name, pointer_steps[0].version)
    ref_linked_derivations = {
        ("openapi_request_body_ref_property_name_from_fragments", "1"),
        ("openapi_request_body_ref_property_required_from_fragments", "1"),
        ("openapi_schema_ref_property_name_from_fragments", "1"),
        ("openapi_schema_ref_property_type_from_fragments", "1"),
        ("openapi_schema_ref_property_required_from_fragments", "1"),
        ("openapi_schema_two_hop_ref_property_name_from_fragments", "1"),
        ("openapi_schema_two_hop_ref_property_type_from_fragments", "1"),
        ("openapi_schema_two_hop_ref_property_required_from_fragments", "1"),
    }
    if derivation not in ref_linked_derivations and context_fragments:
        return None, "DERIVATION_CONTEXT_INVALID"
    if derivation == ("openapi_response_status_from_pointer", "1"):
        derived_value = _openapi_response_status_from_pointer(fragment.locator.pointer)
        expected_claim_path = (
            f"/responses/{derived_value}/status_code"
            if derived_value is not None
            else None
        )
    elif derivation == ("openapi_schema_name_from_ref", "1"):
        schema_ref = _openapi_response_schema_ref_from_pointer(
            fragment.locator.pointer,
            fragment.semantic_value,
        )
        if schema_ref is None:
            return None, "DERIVATION_INAPPLICABLE"
        expected_claim_path, derived_value = schema_ref
    elif derivation == ("openapi_request_schema_name_from_ref", "1"):
        derived_value = _openapi_request_schema_ref_from_pointer(
            fragment.locator.pointer,
            fragment.semantic_value,
        )
        if derived_value is None:
            return None, "DERIVATION_INAPPLICABLE"
        expected_claim_path = "/request_schema_ref"
    elif derivation == ("openapi_request_body_property_name_from_pointer", "1"):
        property_name = _openapi_request_body_property_from_pointer(
            fragment.locator.pointer,
            operation_value,
            fragment.semantic_value,
        )
        if property_name is None:
            return None, "DERIVATION_INAPPLICABLE"
        expected_claim_path = (
            f"/parameters/body/{escape_segment(property_name)}/name"
        )
        derived_value = property_name
    elif derivation == (
        "openapi_request_body_property_required_from_schema_pointer",
        "1",
    ):
        required_info = _openapi_request_body_property_required_from_schema_pointer(
            pointer=fragment.locator.pointer,
            source_schema=fragment.semantic_value,
            operation_value=operation_value,
            claim_path=support.claim_path,
        )
        if required_info is None:
            return None, "DERIVATION_INAPPLICABLE"
        expected_claim_path, derived_value = required_info
    elif derivation == (
        "openapi_request_body_ref_property_name_from_fragments",
        "1",
    ):
        if len(context_fragments) != 1:
            return None, "DERIVATION_CONTEXT_INVALID"
        property_name = _openapi_request_body_ref_property_from_fragments(
            property_pointer=fragment.locator.pointer,
            ref_pointer=context_fragments[0].locator.pointer,
            operation_value=operation_value,
            source_property=fragment.semantic_value,
            source_ref=context_fragments[0].semantic_value,
        )
        if property_name is None:
            return None, "DERIVATION_INAPPLICABLE"
        expected_claim_path = (
            f"/parameters/body/{escape_segment(property_name)}/name"
        )
        derived_value = property_name
    elif derivation == (
        "openapi_request_body_ref_property_required_from_fragments",
        "1",
    ):
        if len(context_fragments) != 1:
            return None, "DERIVATION_CONTEXT_INVALID"
        required_info = _openapi_request_body_ref_property_required_from_fragments(
            schema_pointer=fragment.locator.pointer,
            ref_pointer=context_fragments[0].locator.pointer,
            operation_value=operation_value,
            source_schema=fragment.semantic_value,
            source_ref=context_fragments[0].semantic_value,
            claim_path=support.claim_path,
        )
        if required_info is None:
            return None, "DERIVATION_INAPPLICABLE"
        expected_claim_path, derived_value = required_info
    elif derivation in {
        ("openapi_schema_ref_property_name_from_fragments", "1"),
        ("openapi_schema_ref_property_type_from_fragments", "1"),
    }:
        if len(context_fragments) != 1:
            return None, "DERIVATION_CONTEXT_INVALID"
        property_info = _openapi_schema_ref_property_from_fragments(
            property_pointer=fragment.locator.pointer,
            ref_pointer=context_fragments[0].locator.pointer,
            source_property=fragment.semantic_value,
            source_ref=context_fragments[0].semantic_value,
            claim_identity=claim_identity,
        )
        if property_info is None:
            return None, "DERIVATION_INAPPLICABLE"
        field_name, source_type = property_info
        if derivation == ("openapi_schema_ref_property_name_from_fragments", "1"):
            expected_claim_path = f"/fields/{escape_segment(field_name)}/name"
            derived_value = field_name
        else:
            if source_type is None:
                return None, "DERIVATION_INAPPLICABLE"
            expected_claim_path = f"/fields/{escape_segment(field_name)}/type"
            derived_value = source_type
    elif derivation == (
        "openapi_schema_ref_property_required_from_fragments",
        "1",
    ):
        if len(context_fragments) != 1:
            return None, "DERIVATION_CONTEXT_INVALID"
        required_info = _openapi_schema_ref_property_required_from_fragments(
            schema_pointer=fragment.locator.pointer,
            ref_pointer=context_fragments[0].locator.pointer,
            source_schema=fragment.semantic_value,
            source_ref=context_fragments[0].semantic_value,
            claim_identity=claim_identity,
            claim_path=support.claim_path,
        )
        if required_info is None:
            return None, "DERIVATION_INAPPLICABLE"
        expected_claim_path, derived_value = required_info
    elif derivation in {
        ("openapi_schema_two_hop_ref_property_name_from_fragments", "1"),
        ("openapi_schema_two_hop_ref_property_type_from_fragments", "1"),
        ("openapi_schema_two_hop_ref_property_required_from_fragments", "1"),
    }:
        if len(context_fragments) != 2:
            return None, "DERIVATION_CONTEXT_INVALID"
        derived = _openapi_schema_two_hop_ref_property_from_fragments(
            primary_pointer=fragment.locator.pointer,
            primary_value=fragment.semantic_value,
            first_ref_pointer=context_fragments[0].locator.pointer,
            first_ref=context_fragments[0].semantic_value,
            second_ref_pointer=context_fragments[1].locator.pointer,
            second_ref=context_fragments[1].semantic_value,
            claim_identity=claim_identity,
            claim_path=support.claim_path,
            required=derivation[0].endswith("required_from_fragments"),
        )
        if derived is None:
            return None, "DERIVATION_INAPPLICABLE"
        expected_claim_path, derived_value = derived
    elif derivation == ("openapi_schema_name_from_pointer", "1"):
        schema_name = _openapi_schema_name_from_pointer(fragment.locator.pointer)
        if schema_name is None or _schema_name_from_claim_identity(claim_identity) != schema_name:
            return None, "DERIVATION_INAPPLICABLE"
        expected_claim_path = "/name"
        derived_value = schema_name
    elif derivation in {
        ("openapi_schema_property_name_from_pointer", "1"),
        ("openapi_schema_property_type_from_pointer", "1"),
    }:
        property_info = _openapi_schema_property_from_pointer(
            fragment.locator.pointer,
            fragment.semantic_value,
        )
        if property_info is None:
            return None, "DERIVATION_INAPPLICABLE"
        schema_name, field_name, source_type = property_info
        if _schema_name_from_claim_identity(claim_identity) != schema_name:
            return None, "DERIVATION_INAPPLICABLE"
        if derivation == ("openapi_schema_property_name_from_pointer", "1"):
            expected_claim_path = f"/fields/{escape_segment(field_name)}/name"
            derived_value = field_name
        else:
            if source_type is None:
                return None, "DERIVATION_INAPPLICABLE"
            expected_claim_path = f"/fields/{escape_segment(field_name)}/type"
            derived_value = source_type
    elif derivation == (
        "openapi_schema_property_required_from_schema_pointer",
        "1",
    ):
        required_info = _openapi_schema_property_required_from_pointer(
            pointer=fragment.locator.pointer,
            source_schema=fragment.semantic_value,
            claim_identity=claim_identity,
            claim_path=support.claim_path,
        )
        if required_info is None:
            return None, "DERIVATION_INAPPLICABLE"
        expected_claim_path, derived_value = required_info
    else:
        operation = _openapi_operation_from_pointer(fragment.locator.pointer)
        if operation is None:
            return None, "DERIVATION_INAPPLICABLE"
        path, method = operation
        expected_claim_path = {
            ("openapi_path_from_pointer", "1"): "/path",
            ("openapi_method_from_pointer", "1"): "/method",
        }[derivation]
        derived_value = (
            path if derivation[0] == "openapi_path_from_pointer" else method
        )
    if support.claim_path != expected_claim_path:
        return None, "DERIVATION_CLAIM_PATH_MISMATCH"
    if (
        support.verification_method is not VerificationMethod.STRUCTURED_FIELD_PATH
        or not isinstance(fragment.locator, JsonPointerLocator)
        or fragment.semantic_role is None
    ):
        return None, "DERIVATION_INAPPLICABLE"

    step = pointer_steps[0]
    expected_input_digests = tuple(
        _value_digest(
            {
                "locator": candidate.locator,
                "semantic_value": candidate.semantic_value,
            }
        )
        for candidate in (fragment, *context_fragments)
    )
    if step.input_digests != expected_input_digests:
        return None, "DERIVATION_INPUT_MISMATCH"

    if derived_value is None:
        return None, "DERIVATION_INAPPLICABLE"
    if step.output_digest != _value_digest(derived_value):
        return derived_value, "DERIVATION_OUTPUT_MISMATCH"
    if canonical_json(derived_value) != canonical_json(claim_value):
        return derived_value, "DERIVATION_VALUE_MISMATCH"
    return derived_value, None


def _openapi_operation_from_pointer(pointer: str) -> tuple[str, str] | None:
    """Return an OpenAPI operation path and method from a canonical pointer."""
    segments = pointer.split("/")
    if len(segments) != 4 or segments[0] or segments[1] != "paths":
        return None
    encoded_path, method = segments[2:]
    if method not in {
        "get",
        "put",
        "post",
        "delete",
        "options",
        "head",
        "patch",
        "trace",
    }:
        return None
    path = _decode_json_pointer_segment(encoded_path)
    if path is None or not path.startswith("/"):
        return None
    return path, method.upper()


def _openapi_response_status_from_pointer(pointer: str) -> str | None:
    """Return an OpenAPI response key only from a canonical response pointer."""
    segments = pointer.split("/")
    if len(segments) != 6 or segments[0] or segments[4] != "responses":
        return None
    if _openapi_operation_from_pointer("/".join(segments[:4])) is None:
        return None
    status = _decode_json_pointer_segment(segments[5])
    if status == "default":
        return status
    if (
        status is not None
        and len(status) == 3
        and status[0] in "12345"
        and all("0" <= character <= "9" for character in status[1:])
    ):
        return status
    return None


def _openapi_response_schema_ref_from_pointer(
    pointer: str,
    source_ref: Any,
) -> tuple[str, str] | None:
    """Map one local response-schema ``$ref`` to its canonical claim path."""
    segments = pointer.split("/")
    if (
        len(segments) != 10
        or segments[0]
        or segments[4] != "responses"
        or segments[6] != "content"
        or segments[8] != "schema"
        or segments[9] != "$ref"
    ):
        return None
    status = _openapi_response_status_from_pointer("/".join(segments[:6]))
    media_type = _decode_json_pointer_segment(segments[7])
    schema_name = _local_openapi_schema_name(source_ref)
    if status is None or not media_type or schema_name is None:
        return None
    return f"/responses/{status}/schema_ref", schema_name


def _openapi_request_schema_ref_from_pointer(
    pointer: str,
    source_ref: Any,
) -> str | None:
    """Map one local request-body schema ``$ref`` to its canonical claim."""
    segments = pointer.split("/")
    if (
        len(segments) != 9
        or segments[0]
        or segments[4] != "requestBody"
        or segments[5] != "content"
        or segments[7] != "schema"
        or segments[8] != "$ref"
    ):
        return None
    if _openapi_operation_from_pointer("/".join(segments[:4])) is None:
        return None
    media_type = _decode_json_pointer_segment(segments[6])
    schema_name = _local_openapi_schema_name(source_ref)
    if not media_type or schema_name is None:
        return None
    return schema_name


def _openapi_request_body_property_from_pointer(
    pointer: str,
    operation_value: Any,
    source_property: Any,
) -> str | None:
    """Return a request-body field path for the operation's local schema.

    The pointer may descend through object ``properties`` and array ``items``.
    Array boundaries are represented with ``[]`` so the derived name remains the
    same structural name that the extraction contract uses (for example,
    ``data[].playerId``).  Any other JSON Pointer segment fails closed.
    """
    segments = pointer.split("/")
    if (
        len(segments) < 6
        or segments[0]
        or segments[1:3] != ["components", "schemas"]
        or segments[4] != "properties"
    ):
        return None
    schema_name = _decode_json_pointer_segment(segments[3])
    property_name = _decode_json_pointer_segment(segments[5])
    if (
        not isinstance(operation_value, Mapping)
        or not schema_name
        or not property_name
        or operation_value.get("request_schema_ref") != schema_name
    ):
        return None

    field_name = property_name
    if isinstance(source_property, Mapping) and source_property.get("type") == "array":
        field_name = f"{field_name}[]"
    index = 6
    while index < len(segments):
        segment = segments[index]
        if segment == "items":
            field_name = f"{field_name}[]"
            index += 1
            continue
        if segment != "properties" or index + 1 >= len(segments):
            return None
        nested_name = _decode_json_pointer_segment(segments[index + 1])
        if not nested_name:
            return None
        field_name = f"{field_name}.{nested_name}"
        index += 2
    return field_name


def _openapi_request_body_property_required_from_schema_pointer(
    *,
    pointer: str,
    source_schema: Any,
    operation_value: Any,
    claim_path: str,
) -> tuple[str, bool] | None:
    """Derive one direct body field's required flag from its request schema.

    The complete component schema is the evidence: it identifies the operation's
    declared request schema, exposes the direct property, and records the
    schema-level ``required`` array.  Nested paths and local ``$ref`` hops are
    intentionally outside this one-fragment derivation.
    """
    schema_name = _openapi_schema_name_from_pointer(pointer)
    if (
        schema_name is None
        or not isinstance(source_schema, Mapping)
        or not isinstance(operation_value, Mapping)
        or operation_value.get("request_schema_ref") != schema_name
    ):
        return None
    parts = claim_path.strip("/").split("/")
    if (
        len(parts) != 4
        or parts[:2] != ["parameters", "body"]
        or parts[3] != "required"
    ):
        return None
    field_name = _decode_json_pointer_segment(parts[2])
    if not field_name or "." in field_name:
        return None
    property_name = field_name.removesuffix("[]")
    properties = source_schema.get("properties")
    source_property = properties.get(property_name) if isinstance(properties, Mapping) else None
    if not isinstance(source_property, Mapping):
        return None
    if field_name.endswith("[]") != (source_property.get("type") == "array"):
        return None
    required = source_schema.get("required", ())
    if not isinstance(required, (list, tuple)) or not all(
        isinstance(name, str) for name in required
    ):
        return None
    return claim_path, property_name in required


def _openapi_request_body_ref_property_from_fragments(
    *,
    property_pointer: str,
    ref_pointer: str,
    operation_value: Any,
    source_property: Any,
    source_ref: Any,
) -> str | None:
    """Map one array-item ``$ref`` and one child property to a body field.

    Both pointers are intentionally constrained to one local schema hop.  The
    operation identifies the root request schema, the context pointer proves
    its array item reference, and the primary pointer proves the child field.
    """
    property_segments = property_pointer.split("/")
    ref_segments = ref_pointer.split("/")
    if (
        len(property_segments) != 6
        or property_segments[0]
        or property_segments[1:3] != ["components", "schemas"]
        or property_segments[4] != "properties"
        or len(ref_segments) != 8
        or ref_segments[0]
        or ref_segments[1:3] != ["components", "schemas"]
        or ref_segments[4] != "properties"
        or ref_segments[6:] != ["items", "$ref"]
    ):
        return None
    item_schema = _decode_json_pointer_segment(property_segments[3])
    item_property = _decode_json_pointer_segment(property_segments[5])
    request_schema = _decode_json_pointer_segment(ref_segments[3])
    request_property = _decode_json_pointer_segment(ref_segments[5])
    if (
        not isinstance(operation_value, Mapping)
        or not item_schema
        or not item_property
        or not request_schema
        or not request_property
        or operation_value.get("request_schema_ref") != request_schema
        or _local_openapi_schema_name(source_ref) != item_schema
    ):
        return None
    suffix = "[]" if (
        isinstance(source_property, Mapping)
        and source_property.get("type") == "array"
    ) else ""
    return f"{request_property}[].{item_property}{suffix}"


def _openapi_request_body_ref_property_required_from_fragments(
    *,
    schema_pointer: str,
    ref_pointer: str,
    operation_value: Any,
    source_schema: Any,
    source_ref: Any,
    claim_path: str,
) -> tuple[str, bool] | None:
    """Derive a one-hop array item's required flag from linked fragments."""
    child_schema = _openapi_schema_name_from_pointer(schema_pointer)
    ref_segments = ref_pointer.split("/")
    if (
        child_schema is None
        or not isinstance(source_schema, Mapping)
        or len(ref_segments) != 8
        or ref_segments[0]
        or ref_segments[1:3] != ["components", "schemas"]
        or ref_segments[4] != "properties"
        or ref_segments[6:] != ["items", "$ref"]
    ):
        return None
    request_schema = _decode_json_pointer_segment(ref_segments[3])
    request_property = _decode_json_pointer_segment(ref_segments[5])
    if (
        not isinstance(operation_value, Mapping)
        or not request_schema
        or not request_property
        or operation_value.get("request_schema_ref") != request_schema
        or _local_openapi_schema_name(source_ref) != child_schema
    ):
        return None
    parts = claim_path.strip("/").split("/")
    if (
        len(parts) != 4
        or parts[:2] != ["parameters", "body"]
        or parts[3] != "required"
    ):
        return None
    field_name = _decode_json_pointer_segment(parts[2])
    if not field_name or field_name.count(".") != 1:
        return None
    outer_name, child_name = field_name.split(".", 1)
    if not outer_name.endswith("[]") or outer_name.removesuffix("[]") != request_property:
        return None
    property_name = child_name.removesuffix("[]")
    properties = source_schema.get("properties")
    source_property = properties.get(property_name) if isinstance(properties, Mapping) else None
    if not isinstance(source_property, Mapping):
        return None
    if child_name.endswith("[]") != (source_property.get("type") == "array"):
        return None
    required = source_schema.get("required", ())
    if not isinstance(required, (list, tuple)) or not all(
        isinstance(name, str) for name in required
    ):
        return None
    return claim_path, property_name in required


def _openapi_schema_ref_property_from_fragments(
    *,
    property_pointer: str,
    ref_pointer: str,
    source_property: Any,
    source_ref: Any,
    claim_identity: str,
) -> tuple[str, str | None] | None:
    """Map one local component ``$ref`` to a nested schema field.

    The primary fragment must be the complete property object in the referenced
    component.  The context fragment must be the root schema's direct property
    or array item's local ``$ref``.  No ref is followed implicitly: both source
    values are supplied as exact fragments and re-checked here.
    """
    property_parts = property_pointer.split("/")
    ref_parts = ref_pointer.split("/")
    if (
        len(property_parts) != 6
        or property_parts[0]
        or property_parts[1:3] != ["components", "schemas"]
        or property_parts[4] != "properties"
        or not isinstance(source_property, Mapping)
    ):
        return None
    item_schema = _decode_json_pointer_segment(property_parts[3])
    item_property = _decode_json_pointer_segment(property_parts[5])
    if not item_schema or not item_property:
        return None

    is_array_item = (
        len(ref_parts) == 8
        and not ref_parts[0]
        and ref_parts[1:3] == ["components", "schemas"]
        and ref_parts[4] == "properties"
        and ref_parts[6:] == ["items", "$ref"]
    )
    is_direct_property = (
        len(ref_parts) == 7
        and not ref_parts[0]
        and ref_parts[1:3] == ["components", "schemas"]
        and ref_parts[4] == "properties"
        and ref_parts[6] == "$ref"
    )
    if not (is_array_item or is_direct_property):
        return None
    root_schema = _decode_json_pointer_segment(ref_parts[3])
    root_property = _decode_json_pointer_segment(ref_parts[5])
    if (
        not root_schema
        or not root_property
        or _schema_name_from_claim_identity(claim_identity) != root_schema
        or _local_openapi_schema_name(source_ref) != item_schema
    ):
        return None
    source_type = source_property.get("type")
    if source_type is not None and not isinstance(source_type, str):
        return None
    prefix = f"{root_property}[]" if is_array_item else root_property
    suffix = "[]" if source_type == "array" else ""
    return f"{prefix}.{item_property}{suffix}", source_type


def _openapi_schema_ref_property_required_from_fragments(
    *,
    schema_pointer: str,
    ref_pointer: str,
    source_schema: Any,
    source_ref: Any,
    claim_identity: str,
    claim_path: str,
) -> tuple[str, bool] | None:
    """Derive a one-hop referenced schema field's required flag."""
    child_schema = _openapi_schema_name_from_pointer(schema_pointer)
    ref_parts = ref_pointer.split("/")
    is_array_item = (
        len(ref_parts) == 8
        and not ref_parts[0]
        and ref_parts[1:3] == ["components", "schemas"]
        and ref_parts[4] == "properties"
        and ref_parts[6:] == ["items", "$ref"]
    )
    is_direct_property = (
        len(ref_parts) == 7
        and not ref_parts[0]
        and ref_parts[1:3] == ["components", "schemas"]
        and ref_parts[4] == "properties"
        and ref_parts[6] == "$ref"
    )
    if (
        child_schema is None
        or not isinstance(source_schema, Mapping)
        or not (is_array_item or is_direct_property)
    ):
        return None
    root_schema = _decode_json_pointer_segment(ref_parts[3])
    root_property = _decode_json_pointer_segment(ref_parts[5])
    if (
        not root_schema
        or not root_property
        or _schema_name_from_claim_identity(claim_identity) != root_schema
        or _local_openapi_schema_name(source_ref) != child_schema
    ):
        return None
    parts = claim_path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "fields" or parts[2] != "required":
        return None
    field_name = _decode_json_pointer_segment(parts[1])
    if not field_name or field_name.count(".") != 1:
        return None
    prefix, child_name = field_name.split(".", 1)
    expected_prefix = f"{root_property}[]" if is_array_item else root_property
    if prefix != expected_prefix:
        return None
    property_name = child_name.removesuffix("[]")
    properties = source_schema.get("properties")
    source_property = properties.get(property_name) if isinstance(properties, Mapping) else None
    if not isinstance(source_property, Mapping):
        return None
    if child_name.endswith("[]") != (source_property.get("type") == "array"):
        return None
    required = source_schema.get("required", ())
    if not isinstance(required, (list, tuple)) or not all(
        isinstance(name, str) for name in required
    ):
        return None
    return claim_path, property_name in required


def _openapi_schema_two_hop_ref_property_from_fragments(
    *,
    primary_pointer: str, primary_value: Any,
    first_ref_pointer: str, first_ref: Any,
    second_ref_pointer: str, second_ref: Any,
    claim_identity: str, claim_path: str, required: bool,
) -> tuple[str, Any] | None:
    """Verify exactly two ordered ``items.$ref`` hops for a schema field."""
    def ref_parts(pointer: str) -> tuple[str, str] | None:
        parts = pointer.split("/")
        if not (len(parts) == 8 and not parts[0] and parts[1:3] == ["components", "schemas"] and parts[4] == "properties" and parts[6:] == ["items", "$ref"]):
            return None
        parent = _decode_json_pointer_segment(parts[3])
        prop = _decode_json_pointer_segment(parts[5])
        return (parent, prop) if parent and prop else None
    first = ref_parts(first_ref_pointer)
    second = ref_parts(second_ref_pointer)
    if first is None or second is None or _schema_name_from_claim_identity(claim_identity) != first[0] or _local_openapi_schema_name(first_ref) != second[0]:
        return None
    child_schema = _local_openapi_schema_name(second_ref)
    parts = claim_path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "fields" or parts[2] not in {"name", "type", "required"}:
        return None
    field_name = _decode_json_pointer_segment(parts[1])
    prefix = f"{first[1]}[].{second[1]}[]"
    if not field_name or not field_name.startswith(f"{prefix}."):
        return None
    property_name = field_name.removeprefix(f"{prefix}.").removesuffix("[]")
    if required:
        if _openapi_schema_name_from_pointer(primary_pointer) != child_schema or not isinstance(primary_value, Mapping):
            return None
        properties = primary_value.get("properties")
        source_property = (
            properties.get(property_name) if isinstance(properties, Mapping) else None
        )
        required_names = primary_value.get("required", ())
        if not isinstance(source_property, Mapping) or not isinstance(required_names, (list, tuple)) or not all(isinstance(name, str) for name in required_names):
            return None
        if field_name.endswith("[]") != (source_property.get("type") == "array"):
            return None
        return claim_path, property_name in required_names
    pointer_parts = primary_pointer.split("/")
    if not (len(pointer_parts) == 6 and not pointer_parts[0] and pointer_parts[1:3] == ["components", "schemas"] and pointer_parts[4] == "properties" and _decode_json_pointer_segment(pointer_parts[3]) == child_schema and isinstance(primary_value, Mapping)):
        return None
    if _decode_json_pointer_segment(pointer_parts[5]) != property_name:
        return None
    source_type = primary_value.get("type")
    if source_type is not None and not isinstance(source_type, str):
        return None
    expected_field = f"{prefix}.{property_name}{'[]' if source_type == 'array' else ''}"
    if field_name != expected_field:
        return None
    return claim_path, (field_name if parts[2] == "name" else source_type)


def _openapi_schema_name_from_pointer(pointer: str) -> str | None:
    """Return the name of one direct ``components.schemas`` member."""
    segments = pointer.split("/")
    if (
        len(segments) != 4
        or segments[0]
        or segments[1:3] != ["components", "schemas"]
    ):
        return None
    return _decode_json_pointer_segment(segments[3])


def _schema_name_from_claim_identity(claim_identity: str) -> str | None:
    prefix = "claim:schema:"
    suffix = ":definition"
    if not claim_identity.startswith(prefix) or not claim_identity.endswith(suffix):
        return None
    name = claim_identity[len(prefix) : -len(suffix)]
    return name or None


def _openapi_schema_property_from_pointer(
    pointer: str,
    source_property: Any,
) -> tuple[str, str, str | None] | None:
    """Return one inline schema property and its source-stated type.

    The source pointer must select the complete property object.  Every inline
    ``items`` segment contributes an array marker; no ``$ref`` is followed.
    This keeps the structural relationship reproducible from the exact pointer
    and prevents a property from an unrelated component schema being attached
    to the claim.
    """
    segments = pointer.split("/")
    if (
        len(segments) < 6
        or segments[0]
        or segments[1:3] != ["components", "schemas"]
        or segments[4] != "properties"
        or not isinstance(source_property, Mapping)
    ):
        return None
    schema_name = _decode_json_pointer_segment(segments[3])
    property_name = _decode_json_pointer_segment(segments[5])
    if not schema_name or not property_name:
        return None
    source_type = source_property.get("type")
    if source_type is not None and not isinstance(source_type, str):
        return None
    field_name = property_name
    index = 6
    while index < len(segments):
        segment = segments[index]
        if segment == "items":
            field_name = f"{field_name}[]"
            index += 1
            continue
        if segment != "properties" or index + 1 >= len(segments):
            return None
        nested_name = _decode_json_pointer_segment(segments[index + 1])
        if not nested_name:
            return None
        field_name = f"{field_name}.{nested_name}"
        index += 2
    if source_type == "array":
        field_name = f"{field_name}[]"
    return schema_name, field_name, source_type


def _openapi_schema_property_required_from_pointer(
    *,
    pointer: str,
    source_schema: Any,
    claim_identity: str,
    claim_path: str,
) -> tuple[str, bool] | None:
    """Derive a direct field's required flag from one complete schema object."""
    schema_name = _openapi_schema_name_from_pointer(pointer)
    if (
        schema_name is None
        or _schema_name_from_claim_identity(claim_identity) != schema_name
        or not isinstance(source_schema, Mapping)
    ):
        return None
    parts = claim_path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "fields" or parts[2] != "required":
        return None
    field_name = _decode_json_pointer_segment(parts[1])
    if not field_name:
        return None
    property_name = field_name.removesuffix("[]")
    properties = source_schema.get("properties")
    if not isinstance(properties, Mapping) or property_name not in properties:
        return None
    required = source_schema.get("required", ())
    if not isinstance(required, (list, tuple)) or not all(
        isinstance(name, str) for name in required
    ):
        return None
    return claim_path, property_name in required


def _local_openapi_schema_name(source_ref: Any) -> str | None:
    prefix = "#/components/schemas/"
    if not isinstance(source_ref, str) or not source_ref.startswith(prefix):
        return None
    encoded_name = source_ref.removeprefix(prefix)
    if not encoded_name or "/" in encoded_name:
        return None
    return _decode_json_pointer_segment(encoded_name)


def _decode_json_pointer_segment(value: str) -> str | None:
    decoded: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(value) or value[index + 1] not in {"0", "1"}:
            return None
        decoded.append("~" if value[index + 1] == "0" else "/")
        index += 2
    return "".join(decoded)


def _match_reason(method: VerificationMethod) -> str:
    return {
        VerificationMethod.EXACT_NORMALIZED_VALUE: "EXACT_VALUE_MATCH",
        VerificationMethod.CLAIM_BOUND_EXACT_REFERENCE: "CLAIM_BOUND_EXACT_REFERENCE",
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
        "context_fragment_ids": support.context_fragment_ids,
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
