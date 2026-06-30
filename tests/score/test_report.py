from __future__ import annotations

from loop_apidoc.score.models import (
    ScoreCategory,
    ScoreFinding,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
)
from loop_apidoc.score.report import render_markdown, write_reports


def _report() -> ScoreReport:
    blocking = ScoreFinding(
        code="OPENAPI_INVALID",
        severity="error",
        location="openapi.yaml",
        evidence="openapi.yaml cannot be parsed",
        suggested_fix="Regenerate openapi.yaml.",
        category=ScoreCategory.OPENAPI_VALIDITY,
        blocking=True,
        score_impact=100,
    )
    warning = ScoreFinding(
        code="REVIEW_HTML_MISSING",
        severity="warning",
        location="review.html",
        evidence="review page is absent",
        suggested_fix="Re-run assemble.",
        category=ScoreCategory.REVIEWABILITY,
        blocking=False,
        score_impact=20,
    )
    return ScoreReport(
        status=ScoreStatus.FAIL,
        score=78,
        profile=ScoreProfile.CI,
        min_score=85,
        category_scores={
            "openapi_validity": 0,
            "completeness": 100,
            "consistency": 100,
            "source_grounding": 100,
            "reviewability": 80,
        },
        blocking_findings=[blocking],
        findings=[blocking, warning],
    )


def test_render_markdown_includes_summary_categories_and_findings() -> None:
    md = render_markdown(_report())

    assert "# API Documentation Score Report" in md
    assert "Status: **FAIL**" in md
    assert "Score: **78 / 100**" in md
    assert "| openapi_validity | 0 |" in md
    assert "## Blocking Findings" in md
    assert "**OPENAPI_INVALID**" in md
    assert "## Recommended Fixes" in md
    assert "../validation/report.md" in md
    assert "../review.html" in md


def test_write_reports_emits_score_json_and_markdown(tmp_path) -> None:
    out = tmp_path / "score"
    write_reports(_report(), out)

    loaded = ScoreReport.model_validate_json((out / "score.json").read_text())

    assert loaded == _report()
    assert "API Documentation Score Report" in (out / "score.md").read_text(
        encoding="utf-8"
    )
