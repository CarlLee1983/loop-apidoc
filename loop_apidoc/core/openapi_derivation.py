"""OpenAPI pointer-to-claim derivation checks used by claim verification."""

from __future__ import annotations

from typing import Any

from loop_apidoc.core.openapi_pointers import (
    _openapi_operation_from_pointer,
    _openapi_request_body_property_from_pointer,
    _openapi_request_body_property_required_from_schema_pointer,
    _openapi_request_body_ref_property_from_fragments,
    _openapi_request_body_ref_property_required_from_fragments,
    _openapi_request_schema_ref_from_pointer,
    _openapi_response_schema_ref_from_pointer,
    _openapi_response_status_from_pointer,
    _openapi_schema_name_from_pointer,
    _openapi_schema_property_from_pointer,
    _openapi_schema_property_required_from_pointer,
    _openapi_schema_ref_property_from_fragments,
    _openapi_schema_ref_property_required_from_fragments,
    _openapi_schema_two_hop_ref_property_from_fragments,
    _schema_name_from_claim_identity,
)
from loop_apidoc.domain.claim_paths import escape_segment
from loop_apidoc.domain.evidence import (
    ClaimSupportProposal,
    EvidenceFragment,
    JsonPointerLocator,
    VerificationMethod,
    canonical_json,
    fragment_digest,
)


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
    if derivation in ref_linked_derivations and any(
        context.source_artifact_id != fragment.source_artifact_id
        for context in context_fragments
    ):
        return None, "DERIVATION_CONTEXT_ARTIFACT_MISMATCH"
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


def _value_digest(value: Any) -> str:
    return fragment_digest(canonical_json(value))
