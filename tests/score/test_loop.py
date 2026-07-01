from __future__ import annotations

import pytest

from loop_apidoc.score.loop import LoopReport, LoopVerdict, classify_findings, loop_verdict
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


def _rim(severity: str = "error"):  # one reducible finding by default
    return [_finding("REQUIRED_INFO_MISSING", severity)]


def test_converged_when_at_or_above_target():
    report = loop_verdict(
        prev_score=80, curr_score=85, target=85,
        round_index=3, max_rounds=6, findings=_rim(),
    )
    assert report.verdict is LoopVerdict.CONVERGED


def test_converged_takes_precedence_on_final_round():
    report = loop_verdict(
        prev_score=80, curr_score=88, target=85,
        round_index=6, max_rounds=6, findings=[],
    )
    assert report.verdict is LoopVerdict.CONVERGED


def test_exhausted_when_round_cap_reached_below_target():
    report = loop_verdict(
        prev_score=70, curr_score=80, target=85,
        round_index=6, max_rounds=6, findings=_rim(),
    )
    assert report.verdict is LoopVerdict.EXHAUSTED


def test_plateau_when_no_reducible_findings():
    report = loop_verdict(
        prev_score=None, curr_score=70, target=85,
        round_index=1, max_rounds=6,
        findings=[_finding("SOURCE_CONFLICT", "error")],
    )
    assert report.verdict is LoopVerdict.PLATEAU
    assert report.actionable == []
    assert len(report.irreducible) == 1


def test_plateau_when_score_does_not_improve():
    report = loop_verdict(
        prev_score=80, curr_score=80, target=85,
        round_index=3, max_rounds=6, findings=_rim(),
    )
    assert report.verdict is LoopVerdict.PLATEAU


def test_continue_when_improving_with_actionable():
    report = loop_verdict(
        prev_score=70, curr_score=80, target=85,
        round_index=2, max_rounds=6, findings=_rim(),
    )
    assert report.verdict is LoopVerdict.CONTINUE
    assert len(report.actionable) == 1


def test_round1_empty_actionable_is_plateau():
    report = loop_verdict(
        prev_score=None, curr_score=80, target=85,
        round_index=1, max_rounds=6, findings=[],
    )
    assert report.verdict is LoopVerdict.PLATEAU


def test_report_carries_round_metadata():
    report = loop_verdict(
        prev_score=72, curr_score=80, target=85,
        round_index=2, max_rounds=6, findings=_rim(),
    )
    assert isinstance(report, LoopReport)
    assert (report.target, report.prev_score, report.curr_score) == (85, 72, 80)
    assert (report.round_index, report.max_rounds) == (2, 6)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"prev_score": None, "curr_score": 101, "target": 85, "round_index": 1, "max_rounds": 6},
        {"prev_score": None, "curr_score": 80, "target": 101, "round_index": 1, "max_rounds": 6},
        {"prev_score": -1, "curr_score": 80, "target": 85, "round_index": 1, "max_rounds": 6},
        {"prev_score": None, "curr_score": 80, "target": 85, "round_index": 0, "max_rounds": 6},
        {"prev_score": None, "curr_score": 80, "target": 85, "round_index": 1, "max_rounds": 0},
    ],
)
def test_out_of_range_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        loop_verdict(findings=[], **kwargs)
