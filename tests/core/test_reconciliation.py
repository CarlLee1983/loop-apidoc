from __future__ import annotations

from datetime import datetime, timezone

from loop_apidoc.core.models import ClaimProposal
from loop_apidoc.core.reconciliation import reconcile_claims
from loop_apidoc.domain.claim_paths import material_claim_paths
from loop_apidoc.domain.evidence import (
    ClaimSupportProposal,
    EvidenceBundle,
    EvidenceFragment,
    FragmentPrecision,
    LineRangeLocator,
    SourceArtifact,
    SupportRelationshipType,
    VerificationMethod,
    WholeDocumentLocator,
    fragment_digest,
)
from loop_apidoc.domain.models import ClaimStatus


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def _artifact() -> SourceArtifact:
    return SourceArtifact(
        id="artifact-1",
        source_id="manual",
        media_type="text/markdown",
        content_digest="a" * 64,
        acquired_at=NOW,
    )


def _bundle(*fragments: EvidenceFragment) -> EvidenceBundle:
    return EvidenceBundle(
        source_set_id="sources",
        source_set_version="1",
        artifacts=(_artifact(),),
        fragments=fragments,
    )


def _fragment(fragment_id: str, value: object) -> EvidenceFragment:
    excerpt = (
        value
        if isinstance(value, str)
        else __import__("json").dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return EvidenceFragment(
        id=fragment_id,
        source_artifact_id="artifact-1",
        locator=LineRangeLocator(start_line=1, end_line=1),
        fragment_digest=fragment_digest(excerpt),
        normalized_excerpt=excerpt,
        semantic_value=value,
        semantic_role="field.value",
        precision=FragmentPrecision.EXACT,
    )


def _support(fragment_id: str, claim_path: str = "") -> ClaimSupportProposal:
    return ClaimSupportProposal(
        fragment_id=fragment_id,
        claim_path=claim_path,
        proposed_relationship=SupportRelationshipType.EXPLICIT_SUPPORT,
        verification_method=VerificationMethod.EXACT_NORMALIZED_VALUE,
    )


def _proposal(
    proposal_id: str,
    value: object,
    *,
    supports: tuple[ClaimSupportProposal, ...] = (),
    legacy_refs: tuple[str, ...] = (),
    confidence: float | None = None,
    claim_kind: str = "scalar",
) -> ClaimProposal:
    return ClaimProposal(
        id=proposal_id,
        claim_kind=claim_kind,
        subject="payment",
        predicate="definition",
        value=value,
        evidence_refs=legacy_refs,
        support_proposals=supports,
        runtime_identity=f"runtime-{proposal_id}",
        confidence=confidence,
    )


def _supported_scalar(
    proposal_id: str,
    value: str,
    fragment_id: str,
) -> ClaimProposal:
    return _proposal(
        proposal_id,
        value,
        supports=(_support(fragment_id),),
    )


def _operation() -> dict[str, object]:
    return {
        "method": "POST",
        "path": "/payments",
        "summary": "Create payment",
        "parameters": [
            {"name": "amount", "location": "query", "required": True}
        ],
        "responses": [{"status_code": "200", "description": "OK"}],
    }


def _fully_supported_operation() -> tuple[ClaimProposal, EvidenceBundle]:
    value = _operation()
    paths = material_claim_paths("operation", value)
    fragments = tuple(
        _fragment(f"fragment-{index}", _claim_value(value, path))
        for index, path in enumerate(paths)
    )
    supports = tuple(
        _support(fragment.id, path) for path, fragment in zip(paths, fragments, strict=True)
    )
    return (
        _proposal(
            "operation-1",
            value,
            supports=supports,
            claim_kind="operation",
        ),
        _bundle(*fragments),
    )


def _claim_value(value: dict[str, object], path: str) -> object:
    from loop_apidoc.domain.claim_paths import claim_value_at

    return claim_value_at("operation", value, path)


def test_document_reference_exists_but_claim_remains_unverified():
    whole = EvidenceFragment(
        id="fragment-whole",
        source_artifact_id="artifact-1",
        locator=WholeDocumentLocator(),
        fragment_digest="a" * 64,
        precision=FragmentPrecision.DOCUMENT,
    )

    claim = reconcile_claims(
        (
            _proposal(
                "p1",
                True,
                legacy_refs=("fragment-whole",),
            ),
        ),
        evidence_bundle=_bundle(whole),
    )[0]

    assert claim.status is ClaimStatus.UNVERIFIED
    assert claim.support_relationships == ()


def test_matching_support_for_every_material_path_is_supported():
    proposal, bundle = _fully_supported_operation()

    claim = reconcile_claims((proposal,), evidence_bundle=bundle)[0]

    assert claim.status is ClaimStatus.SUPPORTED
    assert {
        relationship.claim_path for relationship in claim.support_relationships
    } == set(material_claim_paths("operation", proposal.value))


def test_partial_path_coverage_is_unverified():
    value = _operation()
    fragment = _fragment("fragment-method", "POST")
    proposal = _proposal(
        "operation-1",
        value,
        supports=(_support("fragment-method", "/method"),),
        claim_kind="operation",
    )

    claim = reconcile_claims(
        (proposal,),
        evidence_bundle=_bundle(fragment),
    )[0]

    assert claim.status is ClaimStatus.UNVERIFIED
    assert any(
        item.reason_code == "CLAIM_PATH_UNCOVERED"
        for item in claim.support_relationships
    )


def test_multiple_fragments_supporting_same_value_merge():
    claims = reconcile_claims(
        (
            _supported_scalar("p1", "USD", "fragment-a"),
            _supported_scalar("p2", "USD", "fragment-b"),
        ),
        evidence_bundle=_bundle(
            _fragment("fragment-a", "USD"),
            _fragment("fragment-b", "USD"),
        ),
    )

    assert claims[0].status is ClaimStatus.SUPPORTED
    assert claims[0].evidence_refs == ("fragment-a", "fragment-b")


def test_supported_different_values_are_conflicting():
    claim = reconcile_claims(
        (
            _supported_scalar("p1", "USD", "fragment-a"),
            _supported_scalar("p2", "TWD", "fragment-b"),
        ),
        evidence_bundle=_bundle(
            _fragment("fragment-a", "USD"),
            _fragment("fragment-b", "TWD"),
        ),
    )[0]

    assert claim.status is ClaimStatus.CONFLICTING
    assert claim.value == ("TWD", "USD")


def test_claim_value_different_from_source_is_conflicting():
    claim = reconcile_claims(
        (_supported_scalar("p1", "USD", "fragment-a"),),
        evidence_bundle=_bundle(_fragment("fragment-a", "TWD")),
    )[0]

    assert claim.status is ClaimStatus.CONFLICTING
    assert any(
        item.relationship is SupportRelationshipType.CONTRADICTS
        for item in claim.support_relationships
    )


def test_runtime_confidence_does_not_change_status():
    low = _proposal("p1", "USD", confidence=0.01)
    high = _proposal("p2", "USD", confidence=0.99)

    claim = reconcile_claims(
        (low, high),
        evidence_bundle=_bundle(),
    )[0]

    assert claim.status is ClaimStatus.UNVERIFIED


def test_exact_fragment_in_legacy_refs_only_remains_unverified():
    claim = reconcile_claims(
        (
            _proposal(
                "p1",
                "USD",
                legacy_refs=("fragment-a",),
            ),
        ),
        evidence_bundle=_bundle(_fragment("fragment-a", "USD")),
    )[0]

    assert claim.status is ClaimStatus.UNVERIFIED
