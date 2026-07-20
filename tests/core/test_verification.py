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
