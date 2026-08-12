from __future__ import annotations

from datetime import datetime, timezone

import pytest

from loop_apidoc.core.models import ClaimProposal
from loop_apidoc.core.verification import verify_claim_support
from loop_apidoc.domain.evidence import (
    ClaimSupportProposal,
    DerivationStep,
    EvidenceBundle,
    EvidenceFragment,
    FragmentPrecision,
    FragmentReconstructionRef,
    JsonPointerLocator,
    LineRangeLocator,
    SourceArtifact,
    SupportRelationshipType,
    VerificationMethod,
    canonical_json,
    fragment_digest,
)


NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def _bundle(*fragments: EvidenceFragment) -> EvidenceBundle:
    return EvidenceBundle(
        source_set_id="sources",
        source_set_version="1",
        artifacts=(
            SourceArtifact(
                id="artifact",
                source_id="manual",
                media_type="application/json",
                content_digest="a" * 64,
                acquired_at=NOW,
            ),
        ),
        fragments=fragments,
    )


def _fragment(
    fragment_id: str,
    excerpt: str = "USD",
    *,
    locator: object | None = None,
    semantic_value: object = "USD",
    semantic_role: str | None = "field.value",
    precision: FragmentPrecision = FragmentPrecision.EXACT,
    digest: str | None = None,
) -> EvidenceFragment:
    return EvidenceFragment(
        id=fragment_id,
        source_artifact_id="artifact",
        locator=locator or LineRangeLocator(start_line=1, end_line=1),
        fragment_digest=digest or fragment_digest(excerpt),
        normalized_excerpt=excerpt,
        semantic_value=semantic_value,
        semantic_role=semantic_role,
        precision=precision,
    )


def _proposal(
    value: object,
    support: ClaimSupportProposal,
    *,
    claim_kind: str = "operation",
    subject: str = "payment",
) -> ClaimProposal:
    return ClaimProposal(
        id="claim",
        claim_kind=claim_kind,
        subject=subject,
        predicate="definition",
        value=value,
        support_proposals=(support,),
        runtime_identity="test",
    )


@pytest.mark.parametrize(
    ("context", "reason"),
    [
        (None, "CONTEXT_FRAGMENT_NOT_FOUND"),
        (
            _fragment(
                "context",
                precision=FragmentPrecision.DOCUMENT,
            ),
            "CONTEXT_FRAGMENT_NOT_EXACT",
        ),
        (
            EvidenceFragment(
                id="context",
                source_artifact_id="artifact",
                locator=LineRangeLocator(start_line=2, end_line=2),
                fragment_digest=fragment_digest("USD"),
                reconstruction_ref=FragmentReconstructionRef(
                    source_artifact_id="artifact",
                    locator=LineRangeLocator(start_line=2, end_line=2),
                    expected_digest=fragment_digest("USD"),
                ),
                precision=FragmentPrecision.EXACT,
            ),
            "CONTEXT_FRAGMENT_NOT_MATERIALIZED",
        ),
        (_fragment("context", digest="0" * 64), "CONTEXT_FRAGMENT_DIGEST_MISMATCH"),
    ],
)
def test_context_evidence_must_be_exact_materialized_and_digest_checked(context, reason):
    support = ClaimSupportProposal(
        fragment_id="primary",
        context_fragment_ids=("context",),
        claim_path="/path",
        proposed_relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
        verification_method=VerificationMethod.EXACT_NORMALIZED_VALUE,
    )
    fragments = (_fragment("primary", "/payments", semantic_value="/payments"),)
    if context is not None:
        fragments += (context,)

    relationship = verify_claim_support(
        _proposal({"path": "/payments"}, support),
        _bundle(*fragments),
    )[0]

    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == reason


def _pointer_support(
    *,
    claim_path: str = "/path",
    input_digests: tuple[str, ...],
    output_value: object = "/payments",
    steps: tuple[DerivationStep, ...] | None = None,
    context_fragment_ids: tuple[str, ...] = (),
) -> ClaimSupportProposal:
    return ClaimSupportProposal(
        fragment_id="operation",
        context_fragment_ids=context_fragment_ids,
        claim_path=claim_path,
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=steps
        or (
            DerivationStep(
                name="openapi_path_from_pointer",
                version="1",
                input_digests=input_digests,
                output_digest=fragment_digest(canonical_json(output_value)),
            ),
        ),
    )


def _operation_fragment(pointer: str = "/paths/~1payments/post") -> EvidenceFragment:
    return _fragment(
        "operation",
        '{"summary":"Create payment"}',
        locator=JsonPointerLocator(pointer=pointer),
        semantic_value={"summary": "Create payment"},
        semantic_role="structured.value",
    )


def _derivation_input(fragment: EvidenceFragment) -> str:
    return fragment_digest(
        canonical_json(
            {"locator": fragment.locator, "semantic_value": fragment.semantic_value}
        )
    )


@pytest.mark.parametrize(
    ("support_builder", "proposal_value", "extra_fragments", "reason"),
    [
        (
            lambda fragment: _pointer_support(
                input_digests=(_derivation_input(fragment),),
                steps=(
                    DerivationStep(
                        name="openapi_path_from_pointer",
                        version="1",
                        input_digests=(_derivation_input(fragment),),
                        output_digest=fragment_digest(canonical_json("/payments")),
                    ),
                    DerivationStep(
                        name="canonical_json",
                        version="1",
                        input_digests=("a" * 64,),
                        output_digest=fragment_digest(canonical_json("/payments")),
                    ),
                ),
            ),
            {"path": "/payments"},
            (),
            "DERIVATION_CHAIN_INVALID",
        ),
        (
            lambda fragment: _pointer_support(
                input_digests=(_derivation_input(fragment),),
                claim_path="/method",
            ),
            {"method": "POST", "path": "/payments"},
            (),
            "DERIVATION_CLAIM_PATH_MISMATCH",
        ),
        (
            lambda fragment: _pointer_support(
                input_digests=(_derivation_input(fragment),),
                context_fragment_ids=("context",),
            ),
            {"path": "/payments"},
            (_fragment("context", "related operation"),),
            "DERIVATION_CONTEXT_INVALID",
        ),
        (
            lambda fragment: _pointer_support(input_digests=("0" * 64,)),
            {"path": "/payments"},
            (),
            "DERIVATION_INPUT_MISMATCH",
        ),
        (
            lambda fragment: _pointer_support(
                input_digests=(_derivation_input(fragment),), output_value="/wrong"
            ),
            {"path": "/payments"},
            (),
            "DERIVATION_OUTPUT_MISMATCH",
        ),
        (
            lambda fragment: _pointer_support(
                input_digests=(_derivation_input(fragment),)
            ),
            {"path": "/charges"},
            (),
            "DERIVATION_VALUE_MISMATCH",
        ),
    ],
)
def test_openapi_derivation_mismatches_fail_closed(
    support_builder, proposal_value, extra_fragments, reason
):
    fragment = _operation_fragment()

    relationship = verify_claim_support(
        _proposal(proposal_value, support_builder(fragment)),
        _bundle(fragment, *extra_fragments),
    )[0]

    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == reason


@pytest.mark.parametrize(
    (
        "step_name",
        "pointer",
        "semantic_value",
        "claim_value",
        "claim_path",
        "claim_kind",
        "subject",
    ),
    [
        (
            "openapi_path_from_pointer",
            "/paths/payments/post",
            {"summary": "bad pointer"},
            {"path": "/payments"},
            "/path",
            "operation",
            "payment",
        ),
        (
            "openapi_schema_name_from_pointer",
            "/components/schemas/PaymentRequest",
            {"type": "object"},
            {"name": "Other", "fields": []},
            "/name",
            "schema",
            "Other",
        ),
        (
            "openapi_schema_property_type_from_pointer",
            "/components/schemas/PaymentRequest/properties/amount",
            {},
            {"name": "PaymentRequest", "fields": [{"name": "amount", "type": "integer"}]},
            "/fields/amount/type",
            "schema",
            "PaymentRequest",
        ),
    ],
)
def test_openapi_pointer_and_schema_derivations_reject_inapplicable_evidence(
    step_name, pointer, semantic_value, claim_value, claim_path, claim_kind, subject
):
    fragment = _fragment(
        "operation",
        canonical_json(semantic_value),
        locator=JsonPointerLocator(pointer=pointer),
        semantic_value=semantic_value,
        semantic_role="structured.value",
    )
    support = ClaimSupportProposal(
        fragment_id=fragment.id,
        claim_path=claim_path,
        proposed_relationship=SupportRelationshipType.DERIVED_SUPPORT,
        verification_method=VerificationMethod.STRUCTURED_FIELD_PATH,
        derivation_steps=(
            DerivationStep(
                name=step_name,
                version="1",
                input_digests=(_derivation_input(fragment),),
                output_digest=fragment_digest(canonical_json("ignored")),
            ),
        ),
    )

    relationship = verify_claim_support(
        _proposal(
            claim_value,
            support,
            claim_kind=claim_kind,
            subject=subject,
        ),
        _bundle(fragment),
    )[0]

    assert relationship.relationship is SupportRelationshipType.INSUFFICIENT
    assert relationship.reason_code == "DERIVATION_INAPPLICABLE"
