from __future__ import annotations

import json

from loop_apidoc.domain.evidence import SupportRelationshipType
from loop_apidoc.evaluation.models import (
    ExpectedClaim,
    ExpectedRelationship,
    MetricReport,
)


def evaluate_claims(
    expected: tuple[ExpectedClaim, ...],
    observed: tuple[ExpectedClaim, ...],
    *,
    expected_conflicts: tuple[str, ...] = (),
    observed_conflicts: tuple[str, ...] = (),
) -> MetricReport:
    expected_map = {_key(claim): claim for claim in expected}
    observed_map = {_key(claim): claim for claim in observed}
    matches = set(expected_map) & set(observed_map)
    precision = (
        len(matches) / len(observed_map)
        if observed_map
        else (1.0 if not expected_map else 0.0)
    )
    recall = len(matches) / len(expected_map) if expected_map else 1.0
    evidence_checks = [
        set(observed_map[key].evidence_refs) == set(expected_map[key].evidence_refs)
        for key in matches
        if expected_map[key].evidence_refs
    ]
    evidence_correctness = (
        sum(evidence_checks) / len(evidence_checks) if evidence_checks else 1.0
    )
    expected_conflict_set = set(expected_conflicts)
    conflict_recall = (
        len(expected_conflict_set & set(observed_conflicts))
        / len(expected_conflict_set)
        if expected_conflict_set
        else 1.0
    )
    return MetricReport(
        claim_precision=precision,
        claim_recall=recall,
        unsupported_assertion_rate=1.0 - precision,
        evidence_reference_correctness=evidence_correctness,
        field_omission_rate=1.0 - recall,
        conflict_detection_recall=conflict_recall,
    )


def evaluate_relationships(
    expected: tuple[ExpectedRelationship, ...],
    observed: tuple[ExpectedRelationship, ...],
    *,
    base_report: MetricReport | None = None,
) -> MetricReport:
    support_kinds = {
        SupportRelationshipType.EXPLICIT_SUPPORT,
        SupportRelationshipType.DERIVED_SUPPORT,
    }
    expected_support = {
        _relationship_key(item)
        for item in expected
        if item.relationship in support_kinds
    }
    observed_support = {
        _relationship_key(item)
        for item in observed
        if item.relationship in support_kinds
    }
    matches = expected_support & observed_support
    support_precision = (
        len(matches) / len(observed_support)
        if observed_support
        else (1.0 if not expected_support else 0.0)
    )
    support_recall = (
        len(matches) / len(expected_support) if expected_support else 1.0
    )

    expected_paths = {
        (item.claim_identity, item.claim_path)
        for item in expected
        if item.relationship in support_kinds
    }
    observed_paths = {
        (item.claim_identity, item.claim_path)
        for item in observed
        if item.relationship in support_kinds
    }
    path_coverage = (
        len(expected_paths & observed_paths) / len(expected_paths)
        if expected_paths
        else 1.0
    )

    expected_contradictions = {
        _relationship_key(item)
        for item in expected
        if item.relationship is SupportRelationshipType.CONTRADICTS
    }
    observed_contradictions = {
        _relationship_key(item)
        for item in observed
        if item.relationship is SupportRelationshipType.CONTRADICTS
    }
    contradiction_recall = (
        len(expected_contradictions & observed_contradictions)
        / len(expected_contradictions)
        if expected_contradictions
        else 1.0
    )

    # Support-only metrics cannot reveal a verifier that downgrades a
    # contradiction to insufficient evidence, or incorrectly promotes an
    # insufficient reference to support. Compare the complete typed
    # relationship set and penalize any unexpected result.
    expected_relationships = {_relationship_key(item) for item in expected}
    observed_relationships = {_relationship_key(item) for item in observed}
    relationship_classification_accuracy = (
        len(expected_relationships & observed_relationships)
        / len(expected_relationships | observed_relationships)
        if expected_relationships or observed_relationships
        else 1.0
    )

    report = base_report or MetricReport(
        claim_precision=1.0,
        claim_recall=1.0,
        unsupported_assertion_rate=0.0,
        evidence_reference_correctness=1.0,
        field_omission_rate=0.0,
        conflict_detection_recall=1.0,
    )
    return report.model_copy(
        update={
            "semantic_support_precision": support_precision,
            "semantic_support_recall": support_recall,
            "claim_path_coverage": path_coverage,
            "contradiction_detection_recall": contradiction_recall,
            "relationship_classification_accuracy": (
                relationship_classification_accuracy
            ),
        }
    )


def _key(claim: ExpectedClaim) -> tuple[str, str]:
    value = json.dumps(
        claim.value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return claim.identity, value


def _relationship_key(
    relationship: ExpectedRelationship,
) -> tuple[str, str, str, str]:
    return (
        relationship.claim_identity,
        relationship.claim_path,
        relationship.fragment_id,
        relationship.relationship.value,
    )
