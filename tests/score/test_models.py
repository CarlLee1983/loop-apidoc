from __future__ import annotations

from loop_apidoc.score.models import (
    CATEGORY_WEIGHTS,
    DEFAULT_MIN_SCORES,
    ScoreCategory,
    ScoreFinding,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
    resolved_min_score,
)


def test_category_weights_sum_to_100() -> None:
    assert sum(CATEGORY_WEIGHTS.values()) == 100
    assert set(CATEGORY_WEIGHTS) == {category.value for category in ScoreCategory}


def test_resolved_min_score_uses_profile_default_or_override() -> None:
    assert DEFAULT_MIN_SCORES[ScoreProfile.CI] == 85
    assert DEFAULT_MIN_SCORES[ScoreProfile.REVIEW] == 70
    assert resolved_min_score(ScoreProfile.CI, None) == 85
    assert resolved_min_score(ScoreProfile.REVIEW, 63) == 63


def test_score_report_serializes_stable_json_keys() -> None:
    finding = ScoreFinding(
        code="REQUIRED_INFO_MISSING",
        severity="warning",
        location="paths./ping.get.responses",
        evidence="response example absent",
        suggested_fix="Re-read endpoint source and add the missing response example.",
        category=ScoreCategory.COMPLETENESS,
        blocking=False,
        score_impact=12,
    )
    report = ScoreReport(
        status=ScoreStatus.NEEDS_ATTENTION,
        score=88,
        profile=ScoreProfile.CI,
        min_score=85,
        category_scores={
            "openapi_validity": 100,
            "completeness": 88,
            "consistency": 100,
            "source_grounding": 100,
            "reviewability": 100,
        },
        blocking_findings=[],
        findings=[finding],
    )

    payload = report.model_dump(mode="json")

    assert payload["status"] == "needs_attention"
    assert payload["profile"] == "ci"
    assert payload["category_scores"]["completeness"] == 88
    assert payload["findings"][0]["category"] == "completeness"
