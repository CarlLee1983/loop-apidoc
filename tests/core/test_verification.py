from __future__ import annotations

from datetime import datetime, timezone

import pytest

from loop_apidoc.core.models import ClaimProposal
from loop_apidoc.core.verification import (
    validate_evidence_bundle,
    verify_claim_support,
)
from loop_apidoc.domain.evidence import (
    ClaimSupportProposal,
    DerivationStep,
    EvidenceBundle,
    EvidenceFragment,
    FragmentPrecision,
    FragmentReconstructionRef,
    JsonPointerLocator,
    LineRangeLocator,
    PageLocator,
    SourceArtifact,
    SupportRelationshipType,
    TableCellLocator,
    VerificationMethod,
    WholeDocumentLocator,
    canonical_json,
    fragment_digest,
)


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def _support(
    fragment_id: str,
    claim_path: str = "",
    method: VerificationMethod = VerificationMethod.EXACT_NORMALIZED_VALUE,
) -> ClaimSupportProposal:
    return ClaimSupportProposal(
        fragment_id=fragment_id,
        claim_path=claim_path,
        proposed_relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
        verification_method=method,
    )


def _proposal(
    value: object,
    support: ClaimSupportProposal,
    *,
    claim_kind: str = "scalar",
) -> ClaimProposal:
    return ClaimProposal(
        id="proposal-1",
        claim_kind=claim_kind,
        subject="payment",
        predicate="definition",
        value=value,
        support_proposals=(support,),
        runtime_identity="parser",
    )


def _schema_proposal(
    supports: tuple[ClaimSupportProposal, ...],
    *,
    required: bool,
) -> ClaimProposal:
    return ClaimProposal(
        id="schema-proposal",
        claim_kind="schema",
        subject="PaymentRequest",
        predicate="definition",
        value={
            "name": "PaymentRequest",
            "fields": [
                {"name": "amount", "type": "integer", "required": required}
            ],
        },
        support_proposals=supports,
        runtime_identity="parser",
    )


def _artifact(artifact_id: str = "artifact-1") -> SourceArtifact:
    return SourceArtifact(
        id=artifact_id,
        source_id="manual",
        media_type="text/markdown",
        content_digest="a" * 64,
        acquired_at=NOW,
    )


def _bundle(
    *fragments: EvidenceFragment,
    artifacts: tuple[SourceArtifact, ...] | None = None,
) -> EvidenceBundle:
    return EvidenceBundle(
        source_set_id="sources",
        source_set_version="1",
        artifacts=artifacts or (_artifact(),),
        fragments=fragments,
    )


def _exact_fragment(
    fragment_id: str,
    excerpt: str,
    *,
    locator=None,
    semantic_value: object = None,
    semantic_role: str | None = None,
    digest: str | None = None,
    artifact_id: str = "artifact-1",
    parent_fragment_id: str | None = None,
) -> EvidenceFragment:
    normalized = excerpt
    return EvidenceFragment(
        id=fragment_id,
        source_artifact_id=artifact_id,
        locator=locator or LineRangeLocator(start_line=1, end_line=1),
        fragment_digest=digest or fragment_digest(normalized),
        normalized_excerpt=normalized,
        semantic_value=semantic_value,
        semantic_role=semantic_role,
        parent_fragment_id=parent_fragment_id,
        precision=FragmentPrecision.EXACT,
    )


def test_table_cell_supports_matching_field_path():
    support = _support(
        "fragment-required",
        "/parameters/query/amount/required",
        VerificationMethod.TABLE_CELL_MAPPING,
    )
    proposal = _proposal(
        {
            "method": "POST",
            "path": "/payments",
            "parameters": [
                {"name": "amount", "location": "query", "required": True}
            ],
        },
        support,
        claim_kind="operation",
    )
    fragment = _exact_fragment(
        "fragment-required",
        "Y",
        locator=TableCellLocator(
            table_index=0,
            row_index=0,
            column_index=2,
            row_key="amount",
            column_name="Required",
        ),
        semantic_value=True,
        semantic_role="parameter.required",
    )

    relationship = verify_claim_support(proposal, _bundle(fragment))[0]

    assert relationship.relationship is SupportRelationshipType.EXPLICIT_SUPPORT
    assert relationship.claim_path == "/parameters/query/amount/required"


def test_whole_document_reference_is_insufficient():
    fragment = EvidenceFragment(
        id="fragment-whole",
        source_artifact_id="artifact-1",
        locator=WholeDocumentLocator(),
        fragment_digest="a" * 64,
        precision=FragmentPrecision.DOCUMENT,
    )

    relationship = verify_claim_support(
        _proposal("Demo", _support("fragment-whole")),
        _bundle(fragment),
    )[0]

    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == "FRAGMENT_NOT_EXACT"


def test_different_exact_value_contradicts_claim():
    fragment = _exact_fragment(
        "fragment-currency",
        "TWD",
        semantic_value="TWD",
        semantic_role="field.value",
    )

    relationship = verify_claim_support(
        _proposal("USD", _support("fragment-currency")),
        _bundle(fragment),
    )[0]

    assert relationship.relationship is SupportRelationshipType.CONTRADICTS
    assert relationship.observed_value == "TWD"


def test_unequal_page_scope_is_insufficient_not_a_false_contradiction():
    fragment = _exact_fragment(
        "fragment-page",
        "Currencies: USD and TWD",
        locator=PageLocator(page=2),
    )

    relationship = verify_claim_support(
        _proposal("USD", _support("fragment-page")),
        _bundle(fragment),
    )[0]

    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == "FRAGMENT_NOT_VALUE_BEARING"


def test_claim_bound_exact_reference_supports_verified_line_range():
    """A v1 claim-path binding can support prose that has no parsed value."""
    fragment = _exact_fragment(
        "fragment-claim-bound",
        "The currency is USD for this request.",
        locator=LineRangeLocator(start_line=12, end_line=12),
    )

    relationship = verify_claim_support(
        _proposal(
            "USD",
            _support(
                "fragment-claim-bound",
                method=VerificationMethod.CLAIM_BOUND_EXACT_REFERENCE,
            ),
        ),
        _bundle(fragment),
    )[0]

    assert relationship.relationship is SupportRelationshipType.EXPLICIT_SUPPORT
    assert relationship.reason_code == "CLAIM_BOUND_EXACT_REFERENCE"
    assert relationship.observed_value is None


def test_json_pointer_support_uses_canonical_structured_value():
    value = {"type": "string"}
    fragment = _exact_fragment(
        "fragment-json",
        '{"type":"string"}',
        locator=JsonPointerLocator(pointer="/components/schemas/Id"),
        semantic_value=value,
        semantic_role="structured.value",
    )

    relationship = verify_claim_support(
        _proposal(
            value,
            _support(
                "fragment-json",
                method=VerificationMethod.STRUCTURED_FIELD_PATH,
            ),
        ),
        _bundle(fragment),
    )[0]

    assert relationship.relationship is SupportRelationshipType.EXPLICIT_SUPPORT


def test_invalid_fragment_digest_is_insufficient():
    fragment = _exact_fragment(
        "fragment-bad",
        "USD",
        semantic_value="USD",
        semantic_role="field.value",
        digest="0" * 64,
    )

    relationship = verify_claim_support(
        _proposal("USD", _support("fragment-bad")),
        _bundle(fragment),
    )[0]

    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == "FRAGMENT_DIGEST_MISMATCH"


def test_bundle_validation_reports_duplicate_unknown_and_bad_digest():
    first = _exact_fragment("duplicate", "USD")
    second = _exact_fragment(
        "duplicate",
        "TWD",
        artifact_id="missing-artifact",
        digest="0" * 64,
    )

    violations = validate_evidence_bundle(_bundle(first, second))

    assert {violation.code for violation in violations} == {
        "DUPLICATE_FRAGMENT_ID",
        "SOURCE_ARTIFACT_NOT_FOUND",
        "FRAGMENT_DIGEST_MISMATCH",
    }


def test_conflicting_duplicate_fragment_ids_fail_closed_regardless_of_order():
    matching = _exact_fragment(
        "duplicate",
        "USD",
        semantic_value="USD",
        semantic_role="field.value",
    )
    contradicting = _exact_fragment(
        "duplicate",
        "TWD",
        semantic_value="TWD",
        semantic_role="field.value",
    )
    proposal = _proposal("USD", _support("duplicate"))

    forward = verify_claim_support(proposal, _bundle(matching, contradicting))[0]
    reverse = verify_claim_support(proposal, _bundle(contradicting, matching))[0]

    assert forward == reverse
    assert forward.relationship is SupportRelationshipType.INSUFFICIENT
    assert forward.reason_code == "DUPLICATE_FRAGMENT_ID"


def test_conflicting_duplicate_context_fragment_ids_fail_closed():
    primary = _exact_fragment(
        "primary",
        "USD",
        semantic_value="USD",
        semantic_role="field.value",
    )
    first_context = _exact_fragment("duplicate-context", "Currency: USD")
    second_context = _exact_fragment("duplicate-context", "Currency: TWD")
    support = _support("primary").model_copy(
        update={"context_fragment_ids": ("duplicate-context",)}
    )
    proposal = _proposal("USD", support)

    forward = verify_claim_support(
        proposal,
        _bundle(primary, first_context, second_context),
    )[0]
    reverse = verify_claim_support(
        proposal,
        _bundle(primary, second_context, first_context),
    )[0]

    assert forward == reverse
    assert forward.relationship is SupportRelationshipType.INSUFFICIENT
    assert forward.reason_code == "DUPLICATE_FRAGMENT_ID"


def test_missing_fragment_and_unknown_claim_path_are_insufficient():
    missing = verify_claim_support(
        _proposal("USD", _support("missing")),
        _bundle(),
    )[0]
    unknown_path = verify_claim_support(
        _proposal(
            {"method": "GET", "path": "/health"},
            _support("fragment", "/not-a-material-path"),
            claim_kind="operation",
        ),
        _bundle(_exact_fragment("fragment", "GET")),
    )[0]

    assert missing.reason_code == "FRAGMENT_NOT_FOUND"
    assert unknown_path.reason_code == "CLAIM_PATH_UNKNOWN"


def test_reconstructable_but_unmaterialized_fragment_is_insufficient():
    locator = LineRangeLocator(start_line=1, end_line=1)
    fragment = EvidenceFragment(
        id="fragment-reconstructable",
        source_artifact_id="artifact-1",
        locator=locator,
        fragment_digest=fragment_digest("USD"),
        reconstruction_ref=FragmentReconstructionRef(
            source_artifact_id="artifact-1",
            locator=locator,
            expected_digest=fragment_digest("USD"),
        ),
        precision=FragmentPrecision.EXACT,
    )

    relationship = verify_claim_support(
        _proposal("USD", _support(fragment.id)),
        _bundle(fragment),
    )[0]

    assert relationship.reason_code == "FRAGMENT_NOT_MATERIALIZED"


@pytest.mark.parametrize(
    ("steps", "reason"),
    [
        ((), "DERIVATION_STEPS_REQUIRED"),
        (
            (
                DerivationStep(
                    name="model_guess",
                    version="1",
                    input_digests=("a" * 64,),
                    output_digest=fragment_digest(canonical_json("USD")),
                ),
            ),
            "DERIVATION_NOT_ALLOWED",
        ),
        (
            (
                DerivationStep(
                    name="canonical_json",
                    version="1",
                    input_digests=("a" * 64,),
                    output_digest="0" * 64,
                ),
            ),
            "DERIVATION_OUTPUT_MISMATCH",
        ),
    ],
)
def test_derived_support_requires_allowlisted_digest_chain(steps, reason):
    support = ClaimSupportProposal(
        fragment_id="fragment",
        claim_path="",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.EXACT_NORMALIZED_VALUE,
        derivation_steps=steps,
    )

    relationship = verify_claim_support(
        _proposal("USD", support),
        _bundle(
            _exact_fragment(
                "fragment",
                "USD",
                semantic_value="USD",
                semantic_role="field.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == reason


def test_allowlisted_derived_support_can_be_verified():
    support = ClaimSupportProposal(
        fragment_id="fragment",
        claim_path="",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.EXACT_NORMALIZED_VALUE,
        derivation_steps=(
            DerivationStep(
                name="canonical_json",
                version="1",
                input_digests=("a" * 64,),
                output_digest=fragment_digest(canonical_json("USD")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal("USD", support),
        _bundle(
            _exact_fragment(
                "fragment",
                "USD",
                semantic_value="USD",
                semantic_role="field.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT


def test_openapi_path_key_can_provide_verified_derived_support():
    """A source operation location can deterministically establish its path key."""
    source_operation = {"summary": "Create payment"}
    locator = JsonPointerLocator(pointer="/paths/~1payments/post")
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": "/paths/~1payments/post"},
        "semantic_value": source_operation,
    }
    support = ClaimSupportProposal(
        fragment_id="source-operation",
        claim_path="/path",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_path_from_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json("/payments")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {"method": "POST", "path": "/payments"},
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "source-operation",
                '{"summary":"Create payment"}',
                locator=locator,
                semantic_value=source_operation,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "/payments"
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_operation_pointer_can_provide_verified_derived_method():
    """An OpenAPI operation key can deterministically establish its method."""
    source_operation = {"summary": "Create payment"}
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": "/paths/~1payments/post"},
        "semantic_value": source_operation,
    }
    support = ClaimSupportProposal(
        fragment_id="source-operation",
        claim_path="/method",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_method_from_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json("POST")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {"method": "POST", "path": "/payments"},
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "source-operation",
                '{"summary":"Create payment"}',
                locator=JsonPointerLocator(pointer="/paths/~1payments/post"),
                semantic_value=source_operation,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "POST"
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_response_pointer_can_provide_verified_derived_status():
    """An OpenAPI response key can deterministically establish its status code."""
    source_response = {"description": "Accepted"}
    derivation_input = {
        "locator": {
            "kind": "json_pointer",
            "pointer": "/paths/~1payments/post/responses/202",
        },
        "semantic_value": source_response,
    }
    support = ClaimSupportProposal(
        fragment_id="source-response",
        claim_path="/responses/202/status_code",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_response_status_from_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json("202")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {"responses": [{"status_code": "202"}]},
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "source-response",
                '{"description":"Accepted"}',
                locator=JsonPointerLocator(
                    pointer="/paths/~1payments/post/responses/202"
                ),
                semantic_value=source_response,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "202"
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_response_range_pointer_provides_verified_derived_status():
    """An OpenAPI response range preserves its canonical ``2XX`` key."""
    pointer = "/paths/~1payments/post/responses/2XX"
    source_response = {"description": "Successful response"}
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": pointer},
        "semantic_value": source_response,
    }
    support = ClaimSupportProposal(
        fragment_id="source-response-range",
        claim_path="/responses/2XX/status_code",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_response_status_from_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json("2XX")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {"responses": [{"status_code": "2XX"}]},
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "source-response-range",
                '{"description":"Successful response"}',
                locator=JsonPointerLocator(pointer=pointer),
                semantic_value=source_response,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "2XX"
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_schema_ref_can_provide_verified_derived_schema_name():
    """A local OpenAPI schema reference can deterministically establish its name."""
    source_ref = "#/components/schemas/Payment"
    derivation_input = {
        "locator": {
            "kind": "json_pointer",
            "pointer": (
                "/paths/~1payments/post/responses/202/content/"
                "application~1json/schema/$ref"
            ),
        },
        "semantic_value": source_ref,
    }
    support = ClaimSupportProposal(
        fragment_id="response-schema-ref",
        claim_path="/responses/202/schema_ref",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_schema_name_from_ref",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json("Payment")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {
                "responses": [
                    {"status_code": "202", "schema_ref": "Payment"}
                ]
            },
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "response-schema-ref",
                '"#/components/schemas/Payment"',
                locator=JsonPointerLocator(
                    pointer=(
                        "/paths/~1payments/post/responses/202/content/"
                        "application~1json/schema/$ref"
                    )
                ),
                semantic_value=source_ref,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "Payment"
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_request_schema_ref_can_provide_verified_derived_schema_name():
    """A local request-body schema ref deterministically establishes its name."""
    source_ref = "#/components/schemas/PaymentRequest"
    pointer = (
        "/paths/~1payments/post/requestBody/content/application~1json/schema/$ref"
    )
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": pointer},
        "semantic_value": source_ref,
    }
    support = ClaimSupportProposal(
        fragment_id="request-schema-ref",
        claim_path="/request_schema_ref",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_request_schema_name_from_ref",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json("PaymentRequest")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {"request_schema_ref": "PaymentRequest"},
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "request-schema-ref",
                '"#/components/schemas/PaymentRequest"',
                locator=JsonPointerLocator(pointer=pointer),
                semantic_value=source_ref,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "PaymentRequest"
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_request_property_pointer_can_provide_derived_body_field_name():
    """A property belongs only to the operation's referenced request schema."""
    pointer = "/components/schemas/PaymentRequest/properties/amount"
    source_property = {"type": "integer"}
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": pointer},
        "semantic_value": source_property,
    }
    support = ClaimSupportProposal(
        fragment_id="request-property",
        claim_path="/parameters/body/amount/name",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_request_body_property_name_from_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json("amount")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {
                "request_schema_ref": "PaymentRequest",
                "parameters": [
                    {"name": "amount", "location": "body", "required": True}
                ],
            },
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "request-property",
                '{"type":"integer"}',
                locator=JsonPointerLocator(pointer=pointer),
                semantic_value=source_property,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "amount"
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_request_schema_pointer_proves_direct_body_field_requiredness():
    """A complete request schema proves its own direct body's required flag."""
    pointer = "/components/schemas/PaymentRequest"
    source_schema = {
        "type": "object",
        "required": ["amount"],
        "properties": {"amount": {"type": "integer"}},
    }
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": pointer},
        "semantic_value": source_schema,
    }
    support = ClaimSupportProposal(
        fragment_id="request-schema",
        claim_path="/parameters/body/amount/required",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_request_body_property_required_from_schema_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json(True)),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {
                "request_schema_ref": "PaymentRequest",
                "parameters": [
                    {"name": "amount", "location": "body", "required": True}
                ],
            },
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "request-schema",
                '{"properties":{"amount":{"type":"integer"}},"required":["amount"],"type":"object"}',
                locator=JsonPointerLocator(pointer=pointer),
                semantic_value=source_schema,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value is True
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_request_array_property_pointer_retains_array_marker():
    """An array property maps to the extraction contract's ``[]`` suffix."""
    pointer = "/components/schemas/PaymentRequest/properties/gameCodes"
    source_property = {"type": "array", "items": {"type": "string"}}
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": pointer},
        "semantic_value": source_property,
    }
    support = ClaimSupportProposal(
        fragment_id="request-array-property",
        claim_path="/parameters/body/gameCodes[]/name",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_request_body_property_name_from_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json("gameCodes[]")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {
                "request_schema_ref": "PaymentRequest",
                "parameters": [
                    {"name": "gameCodes[]", "location": "body", "required": True}
                ],
            },
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "request-array-property",
                '{"items":{"type":"string"},"type":"array"}',
                locator=JsonPointerLocator(pointer=pointer),
                semantic_value=source_property,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "gameCodes[]"
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_request_schema_pointer_provides_direct_body_required_flag():
    """A complete request schema proves one direct body field's required flag."""
    pointer = "/components/schemas/PaymentRequest"
    source_schema = {
        "type": "object",
        "required": ["amount"],
        "properties": {"amount": {"type": "integer"}},
    }
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": pointer},
        "semantic_value": source_schema,
    }
    support = ClaimSupportProposal(
        fragment_id="request-schema",
        claim_path="/parameters/body/amount/required",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_request_body_property_required_from_schema_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json(True)),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {
                "request_schema_ref": "PaymentRequest",
                "parameters": [
                    {"name": "amount", "location": "body", "required": True}
                ],
            },
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "request-schema",
                canonical_json(source_schema),
                locator=JsonPointerLocator(pointer=pointer),
                semantic_value=source_schema,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value is True
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_request_array_item_property_pointer_provides_nested_body_name():
    """A request schema array item property retains its array path segment."""
    pointer = "/components/schemas/BatchRequest/properties/data/items/properties/playerId"
    source_property = {"type": "string"}
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": pointer},
        "semantic_value": source_property,
    }
    support = ClaimSupportProposal(
        fragment_id="request-array-item-property",
        claim_path="/parameters/body/data[].playerId/name",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_request_body_property_name_from_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json("data[].playerId")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {
                "request_schema_ref": "BatchRequest",
                "parameters": [
                    {
                        "name": "data[].playerId",
                        "location": "body",
                        "required": True,
                    }
                ],
            },
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "request-array-item-property",
                '{"type":"string"}',
                locator=JsonPointerLocator(pointer=pointer),
                semantic_value=source_property,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "data[].playerId"
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_request_ref_item_property_requires_linked_exact_fragments():
    """A referenced array-item property needs both the link and child evidence."""
    property_pointer = "/components/schemas/Voucher/properties/playerId"
    ref_pointer = "/components/schemas/BatchRequest/properties/data/items/$ref"
    source_property = {"type": "string"}
    source_ref = "#/components/schemas/Voucher"
    property_input = {
        "locator": {"kind": "json_pointer", "pointer": property_pointer},
        "semantic_value": source_property,
    }
    ref_input = {
        "locator": {"kind": "json_pointer", "pointer": ref_pointer},
        "semantic_value": source_ref,
    }
    support = ClaimSupportProposal(
        fragment_id="voucher-property",
        context_fragment_ids=("request-item-ref",),
        claim_path="/parameters/body/data[].playerId/name",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_request_body_ref_property_name_from_fragments",
                version="1",
                input_digests=(
                    fragment_digest(canonical_json(property_input)),
                    fragment_digest(canonical_json(ref_input)),
                ),
                output_digest=fragment_digest(canonical_json("data[].playerId")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {
                "request_schema_ref": "BatchRequest",
                "parameters": [
                    {
                        "name": "data[].playerId",
                        "location": "body",
                        "required": True,
                    }
                ],
            },
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "voucher-property",
                '{"type":"string"}',
                locator=JsonPointerLocator(pointer=property_pointer),
                semantic_value=source_property,
                semantic_role="structured.value",
            ),
            _exact_fragment(
                "request-item-ref",
                '"#/components/schemas/Voucher"',
                locator=JsonPointerLocator(pointer=ref_pointer),
                semantic_value=source_ref,
                semantic_role="structured.value",
            ),
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "data[].playerId"
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_request_ref_item_required_uses_linked_exact_fragments():
    """A child schema's required list needs the request ``items.$ref`` link."""
    child_pointer = "/components/schemas/Voucher"
    ref_pointer = "/components/schemas/BatchRequest/properties/data/items/$ref"
    child_schema = {
        "type": "object",
        "required": ["playerId"],
        "properties": {"playerId": {"type": "string"}},
    }
    source_ref = "#/components/schemas/Voucher"
    child_input = {
        "locator": {"kind": "json_pointer", "pointer": child_pointer},
        "semantic_value": child_schema,
    }
    ref_input = {
        "locator": {"kind": "json_pointer", "pointer": ref_pointer},
        "semantic_value": source_ref,
    }
    support = ClaimSupportProposal(
        fragment_id="voucher-schema",
        context_fragment_ids=("request-item-ref",),
        claim_path="/parameters/body/data[].playerId/required",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name=(
                    "openapi_request_body_ref_property_required_from_fragments"
                ),
                version="1",
                input_digests=(
                    fragment_digest(canonical_json(child_input)),
                    fragment_digest(canonical_json(ref_input)),
                ),
                output_digest=fragment_digest(canonical_json(True)),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            {
                "request_schema_ref": "BatchRequest",
                "parameters": [
                    {
                        "name": "data[].playerId",
                        "location": "body",
                        "required": True,
                    }
                ],
            },
            support,
            claim_kind="operation",
        ),
        _bundle(
            _exact_fragment(
                "voucher-schema",
                canonical_json(child_schema),
                locator=JsonPointerLocator(pointer=child_pointer),
                semantic_value=child_schema,
                semantic_role="structured.value",
            ),
            _exact_fragment(
                "request-item-ref",
                '"#/components/schemas/Voucher"',
                locator=JsonPointerLocator(pointer=ref_pointer),
                semantic_value=source_ref,
                semantic_role="structured.value",
            ),
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value is True
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_schema_pointers_provide_name_and_direct_field_claims():
    """A schema root and direct property prove the matching schema claims."""
    schema_pointer = "/components/schemas/PaymentRequest"
    property_pointer = f"{schema_pointer}/properties/amount"
    source_schema = {
        "type": "object",
        "required": ["amount"],
        "properties": {"amount": {"type": "integer"}},
    }
    source_property = source_schema["properties"]["amount"]

    def step(name: str, pointer: str, value: object) -> DerivationStep:
        semantic_value = source_schema if pointer == schema_pointer else source_property
        return DerivationStep(
            name=name,
            version="1",
            input_digests=(
                fragment_digest(
                    canonical_json(
                        {
                            "locator": {"kind": "json_pointer", "pointer": pointer},
                            "semantic_value": semantic_value,
                        }
                    )
                ),
            ),
            output_digest=fragment_digest(canonical_json(value)),
        )

    supports = (
        ClaimSupportProposal(
            fragment_id="schema-root",
            claim_path="/name",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(
                step("openapi_schema_name_from_pointer", schema_pointer, "PaymentRequest"),
            ),
        ),
        ClaimSupportProposal(
            fragment_id="amount-property",
            claim_path="/fields/amount/name",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(
                step(
                    "openapi_schema_property_name_from_pointer",
                    property_pointer,
                    "amount",
                ),
            ),
        ),
        ClaimSupportProposal(
            fragment_id="amount-property",
            claim_path="/fields/amount/type",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(
                step(
                    "openapi_schema_property_type_from_pointer",
                    property_pointer,
                    "integer",
                ),
            ),
        ),
        ClaimSupportProposal(
            fragment_id="schema-root",
            claim_path="/fields/amount/required",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(
                step(
                    "openapi_schema_property_required_from_schema_pointer",
                    schema_pointer,
                    True,
                ),
            ),
        ),
    )

    relationships = verify_claim_support(
        _schema_proposal(supports, required=True),
        _bundle(
            _exact_fragment(
                "schema-root",
                canonical_json(source_schema),
                locator=JsonPointerLocator(pointer=schema_pointer),
                semantic_value=source_schema,
                semantic_role="structured.value",
            ),
            _exact_fragment(
                "amount-property",
                canonical_json(source_property),
                locator=JsonPointerLocator(pointer=property_pointer),
                semantic_value=source_property,
                semantic_role="structured.value",
            ),
        ),
    )

    assert {
        (relationship.claim_path, relationship.observed_value)
        for relationship in relationships
        if relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    } == {
        ("/name", "PaymentRequest"),
        ("/fields/amount/name", "amount"),
        ("/fields/amount/type", "integer"),
        ("/fields/amount/required", True),
    }


def test_openapi_schema_required_mapping_proves_false_from_complete_schema():
    """A field is false only when its exact schema omits it from ``required``."""
    pointer = "/components/schemas/PaymentRequest"
    source_schema = {"type": "object", "properties": {"amount": {"type": "integer"}}}
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": pointer},
        "semantic_value": source_schema,
    }
    support = ClaimSupportProposal(
        fragment_id="schema-root",
        claim_path="/fields/amount/required",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_schema_property_required_from_schema_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json(False)),
            ),
        ),
    )

    relationship = verify_claim_support(
        _schema_proposal((support,), required=False),
        _bundle(
            _exact_fragment(
                "schema-root",
                canonical_json(source_schema),
                locator=JsonPointerLocator(pointer=pointer),
                semantic_value=source_schema,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value is False
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def test_openapi_schema_required_mapping_requires_array_shape_parity():
    pointer = "/components/schemas/SearchRequest"

    def verify(source_property: dict[str, object]):
        source_schema = {
            "type": "object",
            "required": ["tags"],
            "properties": {"tags": source_property},
        }
        derivation_input = {
            "locator": {"kind": "json_pointer", "pointer": pointer},
            "semantic_value": source_schema,
        }
        support = ClaimSupportProposal(
            fragment_id="schema-root",
            claim_path="/fields/tags[]/required",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(
                DerivationStep(
                    name="openapi_schema_property_required_from_schema_pointer",
                    version="1",
                    input_digests=(
                        fragment_digest(canonical_json(derivation_input)),
                    ),
                    output_digest=fragment_digest(canonical_json(True)),
                ),
            ),
        )
        return verify_claim_support(
            ClaimProposal(
                id="search-schema",
                claim_kind="schema",
                subject="SearchRequest",
                predicate="definition",
                value={
                    "name": "SearchRequest",
                    "fields": [
                        {"name": "tags[]", "type": "string", "required": True}
                    ],
                },
                support_proposals=(support,),
                runtime_identity="parser",
            ),
            _bundle(
                _exact_fragment(
                    "schema-root",
                    canonical_json(source_schema),
                    locator=JsonPointerLocator(pointer=pointer),
                    semantic_value=source_schema,
                    semantic_role="structured.value",
                )
            ),
        )[0]

    array_relationship = verify(
        {"type": "array", "items": {"type": "string"}}
    )
    scalar_relationship = verify({"type": "string"})

    assert array_relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert scalar_relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert scalar_relationship.reason_code == "DERIVATION_INAPPLICABLE"


def test_openapi_schema_property_pointer_derives_nested_field_name():
    """A schema property pointer deterministically establishes its field path."""
    pointer = "/components/schemas/Batch/properties/data/items/properties/playerId"
    source_property = {"type": "string"}
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": pointer},
        "semantic_value": source_property,
    }
    support = ClaimSupportProposal(
        fragment_id="schema-property",
        claim_path="/fields/data[].playerId/name",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_schema_property_name_from_pointer",
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json("data[].playerId")),
            ),
        ),
    )

    relationship = verify_claim_support(
        ClaimProposal(
            id="batch-schema",
            claim_kind="schema",
            subject="Batch",
            predicate="definition",
            value={
                "name": "Batch",
                "fields": [{"name": "data[].playerId", "type": "string"}],
            },
            support_proposals=(support,),
            runtime_identity="parser",
        ),
        _bundle(
            _exact_fragment(
                "schema-property",
                '{"type":"string"}',
                locator=JsonPointerLocator(pointer=pointer),
                semantic_value=source_property,
                semantic_role="structured.value",
            )
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == "data[].playerId"


def test_openapi_schema_ref_field_uses_linked_exact_fragments():
    """A parent schema field behind one ``items.$ref`` remains verifiable."""
    child_pointer = "/components/schemas/Voucher/properties/playerId"
    child_schema_pointer = "/components/schemas/Voucher"
    ref_pointer = "/components/schemas/Batch/properties/data/items/$ref"
    child_property = {"type": "string"}
    child_schema = {
        "type": "object",
        "required": ["playerId"],
        "properties": {"playerId": child_property},
    }
    source_ref = "#/components/schemas/Voucher"

    def derivation_input(pointer: str, semantic_value: object) -> str:
        return fragment_digest(
            canonical_json(
                {
                    "locator": {"kind": "json_pointer", "pointer": pointer},
                    "semantic_value": semantic_value,
                }
            )
        )

    supports = (
        ClaimSupportProposal(
            fragment_id="voucher-property",
            context_fragment_ids=("batch-item-ref",),
            claim_path="/fields/data[].playerId/name",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(
                DerivationStep(
                    name="openapi_schema_ref_property_name_from_fragments",
                    version="1",
                    input_digests=(
                        derivation_input(child_pointer, child_property),
                        derivation_input(ref_pointer, source_ref),
                    ),
                    output_digest=fragment_digest(
                        canonical_json("data[].playerId")
                    ),
                ),
            ),
        ),
        ClaimSupportProposal(
            fragment_id="voucher-property",
            context_fragment_ids=("batch-item-ref",),
            claim_path="/fields/data[].playerId/type",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(
                DerivationStep(
                    name="openapi_schema_ref_property_type_from_fragments",
                    version="1",
                    input_digests=(
                        derivation_input(child_pointer, child_property),
                        derivation_input(ref_pointer, source_ref),
                    ),
                    output_digest=fragment_digest(canonical_json("string")),
                ),
            ),
        ),
        ClaimSupportProposal(
            fragment_id="voucher-schema",
            context_fragment_ids=("batch-item-ref",),
            claim_path="/fields/data[].playerId/required",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(
                DerivationStep(
                    name="openapi_schema_ref_property_required_from_fragments",
                    version="1",
                    input_digests=(
                        derivation_input(child_schema_pointer, child_schema),
                        derivation_input(ref_pointer, source_ref),
                    ),
                    output_digest=fragment_digest(canonical_json(True)),
                ),
            ),
        ),
    )

    relationships = verify_claim_support(
        ClaimProposal(
            id="batch-schema",
            claim_kind="schema",
            subject="Batch",
            predicate="definition",
            value={
                "name": "Batch",
                "fields": [
                    {"name": "data[].playerId", "type": "string", "required": True}
                ],
            },
            support_proposals=supports,
            runtime_identity="parser",
        ),
        _bundle(
            _exact_fragment(
                "voucher-property",
                canonical_json(child_property),
                locator=JsonPointerLocator(pointer=child_pointer),
                semantic_value=child_property,
                semantic_role="structured.value",
            ),
            _exact_fragment(
                "voucher-schema",
                canonical_json(child_schema),
                locator=JsonPointerLocator(pointer=child_schema_pointer),
                semantic_value=child_schema,
                semantic_role="structured.value",
            ),
            _exact_fragment(
                "batch-item-ref",
                '"#/components/schemas/Voucher"',
                locator=JsonPointerLocator(pointer=ref_pointer),
                semantic_value=source_ref,
                semantic_role="structured.value",
            ),
        ),
    )

    assert {
        (item.claim_path, item.observed_value)
        for item in relationships
        if item.relationship is SupportRelationshipType.DERIVED_SUPPORT
    } == {
        ("/fields/data[].playerId/name", "data[].playerId"),
        ("/fields/data[].playerId/type", "string"),
        ("/fields/data[].playerId/required", True),
    }


def test_openapi_local_schema_ref_does_not_cross_source_artifacts():
    child_pointer = "/components/schemas/Voucher/properties/playerId"
    ref_pointer = "/components/schemas/Batch/properties/data/items/$ref"
    child_property = {"type": "string"}
    source_ref = "#/components/schemas/Voucher"

    def derivation_input(pointer: str, semantic_value: object) -> str:
        return fragment_digest(
            canonical_json(
                {
                    "locator": {"kind": "json_pointer", "pointer": pointer},
                    "semantic_value": semantic_value,
                }
            )
        )

    support = ClaimSupportProposal(
        fragment_id="voucher-property",
        context_fragment_ids=("batch-item-ref",),
        claim_path="/fields/data[].playerId/name",
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name="openapi_schema_ref_property_name_from_fragments",
                version="1",
                input_digests=(
                    derivation_input(child_pointer, child_property),
                    derivation_input(ref_pointer, source_ref),
                ),
                output_digest=fragment_digest(canonical_json("data[].playerId")),
            ),
        ),
    )

    relationship = verify_claim_support(
        ClaimProposal(
            id="batch-schema",
            claim_kind="schema",
            subject="Batch",
            predicate="definition",
            value={
                "name": "Batch",
                "fields": [{"name": "data[].playerId", "type": "string"}],
            },
            support_proposals=(support,),
            runtime_identity="parser",
        ),
        _bundle(
            _exact_fragment(
                "voucher-property",
                canonical_json(child_property),
                locator=JsonPointerLocator(pointer=child_pointer),
                semantic_value=child_property,
                semantic_role="structured.value",
                artifact_id="artifact-2",
            ),
            _exact_fragment(
                "batch-item-ref",
                '"#/components/schemas/Voucher"',
                locator=JsonPointerLocator(pointer=ref_pointer),
                semantic_value=source_ref,
                semantic_role="structured.value",
                artifact_id="artifact-1",
            ),
            artifacts=(_artifact("artifact-1"), _artifact("artifact-2")),
        ),
    )[0]

    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == "DERIVATION_CONTEXT_ARTIFACT_MISMATCH"


def test_openapi_schema_two_hop_ref_field_uses_ordered_exact_fragments():
    """Two explicit array-item refs prove a bounded flattened schema field."""
    property_pointer = "/components/schemas/Level/properties/level"
    schema_pointer = "/components/schemas/Level"
    parent_ref_pointer = "/components/schemas/Response/properties/entries/items/$ref"
    child_ref_pointer = "/components/schemas/Entry/properties/levels/items/$ref"
    source_property = {"type": "integer"}
    source_schema = {
        "type": "object",
        "required": ["level"],
        "properties": {"level": source_property},
    }
    parent_ref = "#/components/schemas/Entry"
    child_ref = "#/components/schemas/Level"

    def digest(pointer: str, semantic_value: object) -> str:
        return fragment_digest(canonical_json({
            "locator": {"kind": "json_pointer", "pointer": pointer},
            "semantic_value": semantic_value,
        }))

    supports = (
        ClaimSupportProposal(
            fragment_id="level-property", context_fragment_ids=("entries-ref", "levels-ref"),
            claim_path="/fields/entries[].levels[].level/name",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(DerivationStep(
                name="openapi_schema_two_hop_ref_property_name_from_fragments", version="1",
                input_digests=(digest(property_pointer, source_property), digest(parent_ref_pointer, parent_ref), digest(child_ref_pointer, child_ref)),
                output_digest=fragment_digest(canonical_json("entries[].levels[].level")),
            ),),
        ),
        ClaimSupportProposal(
            fragment_id="level-property", context_fragment_ids=("entries-ref", "levels-ref"),
            claim_path="/fields/entries[].levels[].level/type",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(DerivationStep(
                name="openapi_schema_two_hop_ref_property_type_from_fragments", version="1",
                input_digests=(digest(property_pointer, source_property), digest(parent_ref_pointer, parent_ref), digest(child_ref_pointer, child_ref)),
                output_digest=fragment_digest(canonical_json("integer")),
            ),),
        ),
        ClaimSupportProposal(
            fragment_id="level-schema", context_fragment_ids=("entries-ref", "levels-ref"),
            claim_path="/fields/entries[].levels[].level/required",
            proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
            verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
            derivation_steps=(DerivationStep(
                name="openapi_schema_two_hop_ref_property_required_from_fragments", version="1",
                input_digests=(digest(schema_pointer, source_schema), digest(parent_ref_pointer, parent_ref), digest(child_ref_pointer, child_ref)),
                output_digest=fragment_digest(canonical_json(True)),
            ),),
        ),
    )
    relationships = verify_claim_support(
        ClaimProposal(
            id="response-schema", claim_kind="schema", subject="Response", predicate="definition",
            value={"name": "Response", "fields": [{"name": "entries[].levels[].level", "type": "integer", "required": True}]},
            support_proposals=supports, runtime_identity="parser",
        ),
        _bundle(
            _exact_fragment("level-property", canonical_json(source_property), locator=JsonPointerLocator(pointer=property_pointer), semantic_value=source_property, semantic_role="structured.value"),
            _exact_fragment("level-schema", canonical_json(source_schema), locator=JsonPointerLocator(pointer=schema_pointer), semantic_value=source_schema, semantic_role="structured.value"),
            _exact_fragment("entries-ref", '"#/components/schemas/Entry"', locator=JsonPointerLocator(pointer=parent_ref_pointer), semantic_value=parent_ref, semantic_role="structured.value"),
            _exact_fragment("levels-ref", '"#/components/schemas/Level"', locator=JsonPointerLocator(pointer=child_ref_pointer), semantic_value=child_ref, semantic_role="structured.value"),
        ),
    )

    assert all(item.relationship is SupportRelationshipType.DERIVED_SUPPORT for item in relationships)


@pytest.mark.parametrize(
    ("method", "value", "fragment", "expected_reason"),
    [
        (
            VerificationMethod.TABLE_CELL_MAPPING,
            "USD",
            _exact_fragment("plain-table", "USD"),
            "VERIFIER_INAPPLICABLE",
        ),
        (
            VerificationMethod.STRUCTURED_FIELD_PATH,
            "USD",
            _exact_fragment("plain-structured", "USD"),
            "VERIFIER_INAPPLICABLE",
        ),
        (
            VerificationMethod.ENUM_VALUE,
            1,
            _exact_fragment("plain-enum", "1"),
            "VERIFIER_INAPPLICABLE",
        ),
    ],
)
def test_specialized_verifiers_fail_closed_when_fragment_shape_is_wrong(
    method,
    value,
    fragment,
    expected_reason,
):
    relationship = verify_claim_support(
        _proposal(value, _support(fragment.id, method=method)),
        _bundle(fragment),
    )[0]

    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == expected_reason


def test_enum_verifier_matches_normalized_excerpt_without_semantic_value():
    fragment = _exact_fragment("enum", "USD")

    relationship = verify_claim_support(
        _proposal(
            "USD",
            _support("enum", method=VerificationMethod.ENUM_VALUE),
        ),
        _bundle(fragment),
    )[0]

    assert relationship.relationship is SupportRelationshipType.EXPLICIT_SUPPORT
    assert relationship.reason_code == "ENUM_VALUE_MATCH"


@pytest.mark.parametrize(
    "bundle",
    [
        _bundle(
            _exact_fragment(
                "child",
                "USD",
                parent_fragment_id="missing-parent",
            )
        ),
        _bundle(
            _exact_fragment("parent", "parent"),
            _exact_fragment(
                "child",
                "USD",
                artifact_id="artifact-2",
                parent_fragment_id="parent",
            ),
            artifacts=(_artifact(), _artifact("artifact-2")),
        ),
        _bundle(
            _exact_fragment("a", "A", parent_fragment_id="b"),
            _exact_fragment("b", "B", parent_fragment_id="a"),
        ),
    ],
)
def test_invalid_fragment_hierarchy_is_reported(bundle):
    assert validate_evidence_bundle(bundle)


def test_relationship_identity_and_order_are_deterministic():
    proposal = ClaimProposal(
        id="proposal-1",
        claim_kind="scalar",
        subject="payment",
        predicate="definition",
        value="USD",
        support_proposals=(
            _support("fragment-b"),
            _support("fragment-a"),
        ),
        runtime_identity="parser",
    )
    bundle = _bundle(
        _exact_fragment(
            "fragment-a",
            "USD",
            semantic_value="USD",
            semantic_role="field.value",
        ),
        _exact_fragment(
            "fragment-b",
            "USD",
            semantic_value="USD",
            semantic_role="field.value",
        ),
    )

    first = verify_claim_support(proposal, bundle)
    second = verify_claim_support(proposal, bundle.model_copy())

    assert first == second
    assert tuple(item.fragment_id for item in first) == ("fragment-a", "fragment-b")
    assert all(item.id.startswith("relationship-") for item in first)


INLINE_PATH = "/v1/things"
INLINE_SCHEMA_POINTER = (
    "/paths/~1v1~1things/post/requestBody/content/"
    "application~1x-www-form-urlencoded/schema"
)
INLINE_SCHEMA = {
    "type": "object",
    "required": ["amount"],
    "properties": {
        "amount": {"type": "integer"},
        "note": {"type": "string"},
        "nested": {"type": "object", "properties": {"inner": {"type": "string"}}},
        "items": {"type": "array", "items": {"type": "object"}},
    },
}


def _inline_operation(
    field: str,
    *,
    required: bool = True,
    path: str = INLINE_PATH,
    method: str = "POST",
    request_schema_ref: str | None = None,
) -> dict:
    operation: dict = {
        "method": method,
        "path": path,
        "parameters": [{"name": field, "location": "body", "required": required}],
    }
    if request_schema_ref is not None:
        operation["request_schema_ref"] = request_schema_ref
    return operation


def _verify_inline(
    derivation: str,
    pointer: str,
    source_value: object,
    claim_path: str,
    derived: object,
    operation: dict,
):
    derivation_input = {
        "locator": {"kind": "json_pointer", "pointer": pointer},
        "semantic_value": source_value,
    }
    support = ClaimSupportProposal(
        fragment_id="inline-fragment",
        claim_path=claim_path,
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name=derivation,
                version="1",
                input_digests=(fragment_digest(canonical_json(derivation_input)),),
                output_digest=fragment_digest(canonical_json(derived)),
            ),
        ),
    )
    return verify_claim_support(
        _proposal(operation, support, claim_kind="operation"),
        _bundle(
            _exact_fragment(
                "inline-fragment",
                canonical_json(source_value),
                locator=JsonPointerLocator(pointer=pointer),
                semantic_value=source_value,
                semantic_role="structured.value",
            )
        ),
    )[0]


def _inline_name(pointer, source_value, field="amount", **operation_kwargs):
    return _verify_inline(
        "openapi_inline_request_body_property_name_from_pointer",
        pointer,
        source_value,
        f"/parameters/body/{field}/name",
        field,
        _inline_operation(field, **operation_kwargs),
    )


def _inline_required(
    source_value, claim_required, field="amount", pointer=INLINE_SCHEMA_POINTER,
    **operation_kwargs,
):
    return _verify_inline(
        "openapi_inline_request_body_property_required_from_schema_pointer",
        pointer,
        source_value,
        f"/parameters/body/{field}/required",
        claim_required,
        _inline_operation(field, required=claim_required, **operation_kwargs),
    )


def _assert_derived(relationship, observed):
    assert relationship.relationship is SupportRelationshipType.DERIVED_SUPPORT
    assert relationship.observed_value == observed
    assert relationship.reason_code == "OPENAPI_POINTER_DERIVATION_MATCH"


def _assert_refused(relationship, reason_code="DERIVATION_INAPPLICABLE"):
    """Refusal carries the reason code the component derivation gives."""
    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == reason_code


def test_inline_request_body_property_pointer_proves_body_field_name():
    _assert_derived(
        _inline_name(
            f"{INLINE_SCHEMA_POINTER}/properties/amount", {"type": "integer"}
        ),
        "amount",
    )


def test_inline_request_body_schema_proves_required_true():
    _assert_derived(_inline_required(INLINE_SCHEMA, True), True)


def test_inline_request_body_schema_proves_required_false():
    _assert_derived(_inline_required(INLINE_SCHEMA, False, field="note"), False)


def test_inline_request_body_array_property_name_carries_array_marker():
    """An inline array property gets ``[]`` like a component property."""
    _assert_derived(
        _inline_name(
            f"{INLINE_SCHEMA_POINTER}/properties/items",
            INLINE_SCHEMA["properties"]["items"],
            field="items[]",
        ),
        "items[]",
    )


def test_inline_request_body_array_property_refuses_a_plain_name():
    # The component derivation reports DERIVATION_CLAIM_PATH_MISMATCH here.
    _assert_refused(
        _inline_name(
            f"{INLINE_SCHEMA_POINTER}/properties/items",
            INLINE_SCHEMA["properties"]["items"],
            field="items",
        ),
        "DERIVATION_CLAIM_PATH_MISMATCH",
    )


def test_inline_request_body_required_accepts_an_array_marked_claim():
    _assert_derived(_inline_required(INLINE_SCHEMA, False, field="items[]"), False)


def test_inline_request_body_required_refuses_inconsistent_array_markers():
    _assert_refused(_inline_required(INLINE_SCHEMA, False, field="items"))
    _assert_refused(_inline_required(INLINE_SCHEMA, False, field="amount[]"))


@pytest.mark.parametrize(
    "operation_kwargs",
    [
        {"path": "/v1/other"},
        {"method": "GET"},
    ],
)
def test_inline_request_body_derivations_refuse_a_different_operation(operation_kwargs):
    _assert_refused(
        _inline_name(
            f"{INLINE_SCHEMA_POINTER}/properties/amount",
            {"type": "integer"},
            **operation_kwargs,
        )
    )
    _assert_refused(_inline_required(INLINE_SCHEMA, True, **operation_kwargs))


def test_inline_request_body_method_binding_ignores_case_only():
    _assert_derived(
        _inline_name(
            f"{INLINE_SCHEMA_POINTER}/properties/amount",
            {"type": "integer"},
            method="post",
        ),
        "amount",
    )


def test_inline_request_body_derivations_refuse_an_absent_property():
    _assert_refused(
        _inline_name(f"{INLINE_SCHEMA_POINTER}/properties/ghost", None, field="ghost")
    )
    _assert_refused(_inline_required(INLINE_SCHEMA, False, field="ghost"))


def test_inline_request_body_required_refuses_a_disagreeing_flag():
    # The component derivation reports DERIVATION_OUTPUT_MISMATCH here.
    _assert_refused(
        _inline_required(INLINE_SCHEMA, False), "DERIVATION_OUTPUT_MISMATCH"
    )
    _assert_refused(
        _inline_required(INLINE_SCHEMA, True, field="note"),
        "DERIVATION_OUTPUT_MISMATCH",
    )


@pytest.mark.parametrize(
    "suffix, value, field",
    [
        ("/properties/nested/properties/inner", {"type": "string"}, "nested.inner"),
        ("/properties/nested/properties/inner", {"type": "string"}, "inner"),
        ("/properties/items/items", {"type": "object"}, "items"),
        ("/properties/items/items/properties/id", {"type": "string"}, "id"),
    ],
)
def test_inline_request_body_name_refuses_nested_or_items_pointers(
    suffix, value, field
):
    _assert_refused(
        _inline_name(f"{INLINE_SCHEMA_POINTER}{suffix}", value, field=field)
    )


def test_inline_request_body_required_refuses_a_nested_schema_pointer():
    nested = INLINE_SCHEMA["properties"]["nested"]
    _assert_refused(
        _inline_required(
            nested,
            False,
            field="inner",
            pointer=f"{INLINE_SCHEMA_POINTER}/properties/nested",
        )
    )


def test_inline_request_body_required_refuses_a_ref_schema():
    ref_schema = {"$ref": "#/components/schemas/Thing"}
    _assert_refused(_inline_required(ref_schema, True))
    _assert_refused(
        _inline_required({**INLINE_SCHEMA, "$ref": "#/components/schemas/Thing"}, True)
    )


def test_inline_request_body_derivations_refuse_an_operation_with_request_schema_ref():
    _assert_refused(
        _inline_name(
            f"{INLINE_SCHEMA_POINTER}/properties/amount",
            {"type": "integer"},
            request_schema_ref="ThingRequest",
        )
    )
    _assert_refused(
        _inline_required(INLINE_SCHEMA, True, request_schema_ref="ThingRequest")
    )


SECURITY_PATH = "/v1/things"
SECURITY_OPERATION_POINTER = "/paths/~1v1~1things/post"
SECURITY_OPERATION = {"method": "POST", "path": SECURITY_PATH, "security": ["bearerAuth"]}
SECURITY_OPERATION_OBJECT = {"operationId": "createThing", "responses": {}}
SECURITY_SCHEME_DERIVATION = "openapi_security_scheme_name_from_pointer"
SECURITY_OPERATION_DERIVATION = (
    "openapi_operation_security_from_operation_requirement"
)
SECURITY_DOCUMENT_DERIVATION = "openapi_operation_security_from_document_requirement"


def _verify_security(
    derivation: str,
    primary: tuple[str, object],
    *,
    context: tuple[str, object, str] | None = None,
    claim_kind: str = "operation",
    claim_value: object = None,
    claim_path: str = "/security/bearerAuth",
    derived: object = "bearerAuth",
):
    """Verify one security derivation; ``primary`` is (pointer, semantic value)."""
    pointer, source_value = primary
    inputs = [{"locator": {"kind": "json_pointer", "pointer": pointer}, "semantic_value": source_value}]
    fragments = [
        _exact_fragment(
            "primary",
            canonical_json(source_value),
            locator=JsonPointerLocator(pointer=pointer),
            semantic_value=source_value,
            semantic_role="structured.value",
        )
    ]
    context_ids: tuple[str, ...] = ()
    if context is not None:
        context_pointer, context_value, context_artifact = context
        inputs.append(
            {
                "locator": {"kind": "json_pointer", "pointer": context_pointer},
                "semantic_value": context_value,
            }
        )
        fragments.append(
            _exact_fragment(
                "context",
                canonical_json(context_value),
                locator=JsonPointerLocator(pointer=context_pointer),
                semantic_value=context_value,
                semantic_role="structured.value",
                artifact_id=context_artifact,
            )
        )
        context_ids = ("context",)
    support = ClaimSupportProposal(
        fragment_id="primary",
        context_fragment_ids=context_ids,
        claim_path=claim_path,
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name=derivation,
                version="1",
                input_digests=tuple(
                    fragment_digest(canonical_json(item)) for item in inputs
                ),
                output_digest=fragment_digest(canonical_json(derived)),
            ),
        ),
    )
    value = SECURITY_OPERATION if claim_value is None else claim_value
    return verify_claim_support(
        _proposal(value, support, claim_kind=claim_kind),
        _bundle(
            *fragments,
            artifacts=(_artifact("artifact-1"), _artifact("artifact-2")),
        ),
    )[0]


def _verify_scheme_name(pointer: str, claimed: str = "bearerAuth", **kwargs):
    return _verify_security(
        SECURITY_SCHEME_DERIVATION,
        (pointer, {"type": "http", "scheme": "bearer"}),
        claim_kind="security",
        claim_value={"name": claimed, "type": "http"},
        claim_path="/name",
        derived=kwargs.pop("derived", claimed),
        **kwargs,
    )


def _verify_operation_requirement(
    requirement,
    pointer=f"{SECURITY_OPERATION_POINTER}/security/0",
    **kwargs,
):
    return _verify_security(
        SECURITY_OPERATION_DERIVATION, (pointer, requirement), **kwargs
    )


def _verify_document_requirement(
    requirement,
    context_pointer=SECURITY_OPERATION_POINTER,
    context_value=SECURITY_OPERATION_OBJECT,
    context_artifact="artifact-1",
    pointer="/security/1",
    **kwargs,
):
    return _verify_security(
        SECURITY_DOCUMENT_DERIVATION,
        (pointer, requirement),
        context=(context_pointer, context_value, context_artifact),
        **kwargs,
    )


def test_security_scheme_pointer_proves_scheme_name():
    _assert_derived(
        _verify_scheme_name("/components/securitySchemes/bearerAuth"), "bearerAuth"
    )


def test_operation_level_requirement_proves_operation_security():
    _assert_derived(_verify_operation_requirement({"bearerAuth": []}), "bearerAuth")


def test_document_level_requirement_with_operation_context_proves_security():
    _assert_derived(_verify_document_requirement({"bearerAuth": []}), "bearerAuth")


@pytest.mark.parametrize(
    "requirement",
    [{"basicAuth": []}, {"bearerAuth": [], "basicAuth": []}, {"bearerAuth": ["read"]}, {}],
)
def test_security_requirements_refuse_a_different_key_and_unsupported_shapes(
    requirement,
):
    """A differing key trips the claim-path check; other shapes are inapplicable."""
    code = (
        "DERIVATION_CLAIM_PATH_MISMATCH"
        if requirement == {"basicAuth": []}
        else "DERIVATION_INAPPLICABLE"
    )
    _assert_refused(_verify_operation_requirement(requirement), code)
    _assert_refused(_verify_document_requirement(requirement), code)


def test_security_scheme_name_refuses_a_different_key():
    _assert_refused(
        _verify_scheme_name("/components/securitySchemes/basicAuth", derived="basicAuth"),
        "DERIVATION_VALUE_MISMATCH",
    )


@pytest.mark.parametrize(
    "pointer",
    [
        "/components/securitySchemes/bearerAuth/type",
        "/components/securitySchemes",
        "/components/schemas/bearerAuth",
        "/components/securitySchemes/bearer~2Auth",
    ],
)
def test_security_scheme_name_refuses_a_non_exact_pointer(pointer):
    _assert_refused(_verify_scheme_name(pointer))


@pytest.mark.parametrize(
    "pointer",
    [
        "/paths/~1v1~1other/post/security/0",
        "/paths/~1v1~1things/get/security/0",
        "/paths/~1v1~1things/post/security/first",
        "/paths/~1v1~1things/post/security",
    ],
)
def test_operation_requirement_refuses_another_operation_or_index(pointer):
    _assert_refused(_verify_operation_requirement({"bearerAuth": []}, pointer))


def test_operation_requirement_method_binding_ignores_case_only():
    _assert_derived(
        _verify_operation_requirement(
            {"bearerAuth": []},
            claim_value={**SECURITY_OPERATION, "method": "post"},
        ),
        "bearerAuth",
    )


def test_document_requirement_without_context_is_refused():
    _assert_refused(
        _verify_security(
            SECURITY_DOCUMENT_DERIVATION, ("/security/1", {"bearerAuth": []})
        ),
        "DERIVATION_CONTEXT_INVALID",
    )


def test_document_requirement_refuses_context_from_another_artifact():
    _assert_refused(
        _verify_document_requirement(
            {"bearerAuth": []}, context_artifact="artifact-2"
        ),
        "DERIVATION_CONTEXT_ARTIFACT_MISMATCH",
    )


@pytest.mark.parametrize("own_security", [[{"basicAuth": []}], []])
def test_document_requirement_refuses_an_operation_with_its_own_security(
    own_security,
):
    _assert_refused(
        _verify_document_requirement(
            {"bearerAuth": []},
            context_value={**SECURITY_OPERATION_OBJECT, "security": own_security},
        )
    )


@pytest.mark.parametrize(
    "context_pointer",
    ["/paths/~1v1~1other/post", "/paths/~1v1~1things/get", "/paths/~1v1~1things"],
)
def test_document_requirement_refuses_a_context_for_another_operation(
    context_pointer,
):
    _assert_refused(
        _verify_document_requirement(
            {"bearerAuth": []}, context_pointer=context_pointer
        )
    )


def test_document_requirement_refuses_a_non_document_pointer():
    _assert_refused(
        _verify_document_requirement({"bearerAuth": []}, pointer="/paths/x/security/1")
    )


def test_operation_derivations_refuse_context_fragments():
    _assert_refused(
        _verify_security(
            SECURITY_OPERATION_DERIVATION,
            (f"{SECURITY_OPERATION_POINTER}/security/0", {"bearerAuth": []}),
            context=(SECURITY_OPERATION_POINTER, SECURITY_OPERATION_OBJECT, "artifact-1"),
        ),
        "DERIVATION_CONTEXT_INVALID",
    )


ERROR_CODE_DERIVATION = "openapi_error_code_from_response_pointer"
ERROR_RESPONSE_OBJECT = {"description": "Bad request"}


def _verify_error_code(
    status: str = "400",
    claimed: str = "400",
    *,
    pointer: str | None = None,
    claim_kind: str = "error",
    claim_value: object = None,
):
    return _verify_security(
        ERROR_CODE_DERIVATION,
        (
            pointer or f"/paths/~1payments/post/responses/{status}",
            ERROR_RESPONSE_OBJECT,
        ),
        claim_kind=claim_kind,
        claim_value={"code": claimed, "description": "Bad request"}
        if claim_value is None
        else claim_value,
        claim_path="/code",
        derived=status,
    )


@pytest.mark.parametrize("status", ["400", "401", "403", "422", "500", "599"])
def test_response_key_proves_error_code(status):
    _assert_derived(_verify_error_code(status, status), status)


@pytest.mark.parametrize(
    "status, claimed, reason",
    [
        ("200", "200", "DERIVATION_INAPPLICABLE"),
        ("default", "default", "DERIVATION_INAPPLICABLE"),
        ("4XX", "4XX", "DERIVATION_INAPPLICABLE"),
        ("100", "100", "DERIVATION_INAPPLICABLE"),
        ("302", "302", "DERIVATION_INAPPLICABLE"),
        ("5XX", "5XX", "DERIVATION_INAPPLICABLE"),
        ("401", "400", "DERIVATION_VALUE_MISMATCH"),
    ],
    ids=["2xx", "default", "range", "1xx", "3xx", "5xx-range", "different-code"],
)
def test_error_code_refuses_non_error_keys_and_different_codes(
    status, claimed, reason
):
    _assert_refused(_verify_error_code(status, claimed), reason)


def test_error_code_refuses_a_pointer_below_the_response_key():
    _assert_refused(
        _verify_error_code(
            pointer="/paths/~1payments/post/responses/400/description"
        )
    )


def test_error_code_refuses_a_non_error_claim_kind():
    _assert_refused(
        _verify_error_code(
            claim_kind="operation", claim_value={"path": "/payments", "code": "400"}
        ),
        "CLAIM_PATH_UNKNOWN",
    )


def test_error_code_refuses_another_claim_kind_that_has_a_code_path():
    """idempotency_rule also has ``/code``; only an ``error`` claim may use it."""
    _assert_refused(
        _verify_error_code(
            claim_kind="idempotency_rule", claim_value={"code": "400"}
        )
    )


EXAMPLE_OPERATION_DERIVATION = "openapi_operation_ref_from_request_example_pointer"
EXAMPLE_POINTER = (
    "/paths/~1payments/post/requestBody/content/application~1json/examples/card-direct"
)
EXAMPLE_OBJECT = {"$ref": "#/components/examples/post-payments-card-direct"}
PAYMENTS_OPERATION = "operation:POST:/payments"
_DEFAULT_SOURCE = object()


def _verify_example_operation(
    pointer: str = EXAMPLE_POINTER,
    *,
    source_value: object = _DEFAULT_SOURCE,
    claim_kind: str = "integration_mechanic",
    claim_path: str = "/operation_refs/operation:POST:~1payments",
    derived: str = PAYMENTS_OPERATION,
):
    return _verify_security(
        EXAMPLE_OPERATION_DERIVATION,
        (pointer, EXAMPLE_OBJECT if source_value is _DEFAULT_SOURCE else source_value),
        claim_kind=claim_kind,
        claim_value={
            "name": "card-direct",
            "kind": "test_case",
            "operation_refs": [PAYMENTS_OPERATION],
        },
        claim_path=claim_path,
        derived=derived,
    )


def test_request_example_pointer_proves_the_operation_reference():
    _assert_derived(_verify_example_operation(), PAYMENTS_OPERATION)


def test_request_example_refuses_a_response_example_pointer():
    _assert_refused(
        _verify_example_operation(
            "/paths/~1payments/post/responses/200/content/application~1json"
            "/examples/card-direct"
        ),
        "DERIVATION_INAPPLICABLE",
    )


def test_request_example_refuses_a_components_example_pointer():
    _assert_refused(
        _verify_example_operation("/components/examples/post-payments-card-direct"),
        "DERIVATION_INAPPLICABLE",
    )


@pytest.mark.parametrize(
    "pointer",
    [
        "/paths/~1payments/post/requestBody/content/application~1json/example",
        EXAMPLE_POINTER + "/value",
    ],
    ids=["singular-example", "segment-beyond-key"],
)
def test_request_example_refuses_a_singular_example_or_extra_segments(pointer):
    _assert_refused(_verify_example_operation(pointer), "DERIVATION_INAPPLICABLE")


def test_request_example_refuses_a_different_operation():
    _assert_refused(
        _verify_example_operation(
            "/paths/~1payments~1details/post/requestBody/content/application~1json"
            "/examples/card-direct",
            derived="operation:POST:/payments/details",
        ),
        "DERIVATION_CLAIM_PATH_MISMATCH",
    )


@pytest.mark.parametrize(
    "source_value",
    ["card-direct", ["a"], 0, None],
    ids=["str", "list", "int", "null"],
)
def test_request_example_refuses_a_non_object_fragment_value(source_value):
    _assert_refused(
        _verify_example_operation(source_value=source_value),
        "DERIVATION_INAPPLICABLE",
    )


def test_request_example_refuses_a_non_integration_mechanic_claim_kind():
    _assert_refused(
        _verify_example_operation(claim_kind="transport_policy"),
        "DERIVATION_INAPPLICABLE",
    )


def test_request_example_refuses_a_path_key_with_surrounding_whitespace():
    _assert_refused(
        _verify_example_operation(
            "/paths/~1payments /post/requestBody/content/application~1json"
            "/examples/card-direct"
        ),
        "DERIVATION_INAPPLICABLE",
    )
