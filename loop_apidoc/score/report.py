from __future__ import annotations

from pathlib import Path

from loop_apidoc.score.models import ScoreFinding, ScoreReport


def _finding_bullet(finding: ScoreFinding) -> str:
    return (
        f"- **{finding.code}** ({finding.severity}) @ `{finding.location}`\n"
        f"  - Category: `{finding.category.value}`\n"
        f"  - Score impact: {finding.score_impact}\n"
        f"  - Evidence: {finding.evidence}\n"
        f"  - Suggested fix: {finding.suggested_fix}"
    )


def render_markdown(report: ScoreReport) -> str:
    status = report.status.value.upper()
    lines = [
        "# API Documentation Score Report",
        "",
        f"Status: **{status}**",
        f"Score: **{report.score} / 100**",
        f"Profile: `{report.profile.value}`",
        f"Minimum score: `{report.min_score}`",
        "",
        "## Category Scores",
        "",
        "| Category | Score |",
        "| --- | ---: |",
    ]
    for category, score in report.category_scores.items():
        lines.append(f"| {category} | {score} |")

    lines.extend(
        [
            "",
            "## Artifact Links",
            "",
            "- Validation report: `../validation/report.md`",
            "- Offline review page: `../review.html`",
            "- OpenAPI contract: `../openapi.yaml`",
            "- Provenance: `../provenance.json`",
            "",
            "## Blocking Findings",
            "",
        ]
    )
    if report.blocking_findings:
        lines.extend(_finding_bullet(finding) for finding in report.blocking_findings)
    else:
        lines.append("_No blocking findings._")

    non_blocking = [finding for finding in report.findings if not finding.blocking]
    lines.extend(["", "## Non-Blocking Findings", ""])
    if non_blocking:
        lines.extend(_finding_bullet(finding) for finding in non_blocking)
    else:
        lines.append("_No non-blocking findings._")

    lines.extend(["", "## Recommended Fixes", ""])
    if report.findings:
        for finding in sorted(report.findings, key=lambda item: item.score_impact, reverse=True):
            lines.append(f"- `{finding.location}`: {finding.suggested_fix}")
    else:
        lines.append("_No fixes recommended._")

    return "\n".join(lines).rstrip() + "\n"


def write_reports(report: ScoreReport, score_dir: Path) -> None:
    score_dir.mkdir(parents=True, exist_ok=True)
    (score_dir / "score.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (score_dir / "score.md").write_text(render_markdown(report), encoding="utf-8")
