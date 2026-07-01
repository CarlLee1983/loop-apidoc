from __future__ import annotations

from loop_apidoc.score.loop import classify_findings
from loop_apidoc.score.models import ScoreCategory, ScoreFinding


def _finding(code: str, severity: str) -> ScoreFinding:
    return ScoreFinding(
        code=code,
        severity=severity,
        location="loc",
        evidence="ev",
        suggested_fix="fix",
        category=ScoreCategory.COMPLETENESS,
        blocking=False,
        score_impact=10,
    )


def test_error_openapi_invalid_is_reducible():
    reducible, irreducible = classify_findings([_finding("OPENAPI_INVALID", "error")])
    assert len(reducible) == 1
    assert irreducible == []


def test_error_required_info_missing_is_reducible():
    reducible, irreducible = classify_findings(
        [_finding("REQUIRED_INFO_MISSING", "error")]
    )
    assert len(reducible) == 1
    assert irreducible == []


def test_error_output_mismatch_and_source_unverified_are_reducible():
    reducible, irreducible = classify_findings([
        _finding("OUTPUT_MISMATCH", "error"),
        _finding("SOURCE_UNVERIFIED", "error"),
    ])
    assert len(reducible) == 2
    assert irreducible == []


def test_source_conflict_error_is_irreducible():
    reducible, irreducible = classify_findings([_finding("SOURCE_CONFLICT", "error")])
    assert reducible == []
    assert len(irreducible) == 1


def test_unsupported_assertion_error_is_irreducible():
    reducible, irreducible = classify_findings(
        [_finding("UNSUPPORTED_ASSERTION", "error")]
    )
    assert reducible == []
    assert len(irreducible) == 1


def test_any_warning_is_irreducible():
    reducible, irreducible = classify_findings([
        _finding("REQUIRED_INFO_MISSING", "warning"),
        _finding("SOURCE_UNVERIFIED", "warning"),
        _finding("REVIEW_HTML_MISSING", "warning"),
    ])
    assert reducible == []
    assert len(irreducible) == 3


def test_order_is_preserved_within_buckets():
    reducible, irreducible = classify_findings([
        _finding("OPENAPI_INVALID", "error"),
        _finding("SOURCE_CONFLICT", "error"),
        _finding("OUTPUT_MISMATCH", "error"),
    ])
    assert [f.code for f in reducible] == ["OPENAPI_INVALID", "OUTPUT_MISMATCH"]
    assert [f.code for f in irreducible] == ["SOURCE_CONFLICT"]
