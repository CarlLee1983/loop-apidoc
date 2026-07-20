from __future__ import annotations

import json

from loop_apidoc.evaluation.models import ExpectedClaim, MetricReport


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


def _key(claim: ExpectedClaim) -> tuple[str, str]:
    value = json.dumps(
        claim.value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return claim.identity, value
