from __future__ import annotations

from pydantic import ValidationError
import pytest

from loop_apidoc.domain.evidence import (
    ClaimEvidenceRelationship,
    EvidenceFragment,
    FragmentPrecision,
    LineRangeLocator,
    SupportRelationshipType,
    TableCellLocator,
    VerificationMethod,
    fragment_digest,
    make_fragment_id,
    make_relationship_id,
    normalize_excerpt,
)


def _legacy_fragment(locator: str) -> dict[str, object]:
    return {
        "id": "fragment-legacy",
        "source_artifact_id": "artifact-1",
        "locator": locator,
        "fragment_digest": "a" * 64,
    }


def test_fragment_digest_uses_normalized_fragment_content():
    normalized = normalize_excerpt("\r\nAmount  \r\n100\r\n")

    assert normalized == "Amount\n100"
    assert fragment_digest(normalized) == (
        "a8b72a7dc25c65357c83d7b1763d7032326615c36933bc8eb07f60603af4be87"
    )


def test_locator_and_fragment_id_are_stable():
    locator = TableCellLocator(
        table_index=1,
        row_index=2,
        column_index=3,
        row_key="amount",
        column_name="Required",
    )

    first = make_fragment_id(
        source_artifact_id="artifact-1",
        locator=locator,
        fragment_digest="a" * 64,
        parent_fragment_id="fragment-parent",
    )
    second = make_fragment_id(
        source_artifact_id="artifact-1",
        locator=locator.model_copy(),
        fragment_digest="a" * 64,
        parent_fragment_id="fragment-parent",
    )

    assert first == second
    assert first.startswith("fragment-")


def test_exact_fragment_requires_content_or_reconstruction_reference():
    with pytest.raises(ValidationError, match="exact fragment requires"):
        EvidenceFragment(
            id="fragment-x",
            source_artifact_id="artifact-1",
            locator=LineRangeLocator(start_line=2, end_line=3),
            fragment_digest="a" * 64,
            precision=FragmentPrecision.EXACT,
        )


def test_legacy_string_locator_deserializes_without_becoming_exact():
    whole = EvidenceFragment.model_validate(_legacy_fragment(locator="whole"))
    ambiguous = EvidenceFragment.model_validate(_legacy_fragment(locator="p.2"))

    assert whole.locator.kind == "whole_document"
    assert whole.precision is FragmentPrecision.DOCUMENT
    assert ambiguous.locator.kind == "unresolved"
    assert ambiguous.precision is FragmentPrecision.UNRESOLVED


def test_exact_fragment_rejects_document_locator():
    with pytest.raises(ValidationError, match="exact fragment requires an exact locator"):
        EvidenceFragment.model_validate(
            {
                **_legacy_fragment(locator="whole"),
                "normalized_excerpt": "content",
                "fragment_digest": fragment_digest("content"),
                "precision": "exact",
            }
        )


def test_relationship_id_is_stable_for_canonical_payload():
    relationship = ClaimEvidenceRelationship(
        id="temporary",
        claim_identity="claim:operation:POST /payments:definition",
        claim_path="/parameters/query/amount/required",
        fragment_id="fragment-required",
        relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
        verification_method=VerificationMethod.TABLE_CELL_MAPPING,
        claim_value_digest=fragment_digest("true"),
        evidence_value_digest=fragment_digest("true"),
        observed_value=True,
        reason_code="TABLE_CELL_VALUE_MATCH",
    )

    first = make_relationship_id(relationship)
    second = make_relationship_id(relationship.model_copy(update={"id": "different"}))

    assert first == second
    assert first.startswith("relationship-")
