from __future__ import annotations

import re

from loop_apidoc.manifest.models import ProcessingStatus
from loop_apidoc.score.models import (
    CATEGORY_WEIGHTS,
    ScoreCategory,
    ScoreFinding,
    ScoreInputs,
    ScoreProfile,
    ScoreReport,
    ScoreStatus,
    resolved_min_score,
)
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_ISSUE_CATEGORY: dict[IssueCode, ScoreCategory] = {
    IssueCode.OPENAPI_INVALID: ScoreCategory.OPENAPI_VALIDITY,
    IssueCode.REQUIRED_INFO_MISSING: ScoreCategory.COMPLETENESS,
    IssueCode.OUTPUT_MISMATCH: ScoreCategory.CONSISTENCY,
    IssueCode.SOURCE_UNVERIFIED: ScoreCategory.SOURCE_GROUNDING,
    IssueCode.SOURCE_CONFLICT: ScoreCategory.SOURCE_GROUNDING,
    IssueCode.UNSUPPORTED_ASSERTION: ScoreCategory.SOURCE_GROUNDING,
}

_WARNING_PENALTY = 12
_ERROR_PENALTY = 40
_CODE_ERROR_PENALTY: dict[IssueCode, int] = {
    IssueCode.OPENAPI_INVALID: 100,
    IssueCode.UNSUPPORTED_ASSERTION: 50,
    IssueCode.SOURCE_CONFLICT: 50,
}

_REVIEW_BLOCKING_CODES = {
    IssueCode.OPENAPI_INVALID,
    IssueCode.OUTPUT_MISMATCH,
    IssueCode.SOURCE_CONFLICT,
    IssueCode.UNSUPPORTED_ASSERTION,
}

_EXAMPLE_DETAIL_PATTERN = re.compile(r"\bexamples?\b", re.IGNORECASE)


def _issue_penalty(issue: Issue) -> int:
    if issue.severity is Severity.WARNING:
        return _WARNING_PENALTY
    return _CODE_ERROR_PENALTY.get(issue.code, _ERROR_PENALTY)


def _is_blocking(issue: Issue, profile: ScoreProfile) -> bool:
    if issue.severity is not Severity.ERROR:
        return False
    if profile is ScoreProfile.CI:
        return True
    return issue.code in _REVIEW_BLOCKING_CODES


def _declared_example_gap(issue: Issue, plan: dict | None) -> bool:
    if issue.code is not IssueCode.REQUIRED_INFO_MISSING or issue.field_path != "examples":
        return False
    return any(
        item.get("operation_location") == issue.location
        and _is_example_detail(item.get("detail", ""))
        for item in (plan or {}).get("missing_items", [])
        if isinstance(item, dict)
    )


def _is_example_detail(detail: object) -> bool:
    text = str(detail)
    return "範例" in text or _EXAMPLE_DETAIL_PATTERN.search(text) is not None


def _finding_from_issue(
    issue: Issue,
    profile: ScoreProfile,
    *,
    score_impact: int | None = None,
) -> ScoreFinding:
    return ScoreFinding(
        code=issue.code.value,
        severity=issue.severity.value,
        location=issue.location,
        evidence=issue.evidence,
        suggested_fix=issue.suggested_fix,
        category=_ISSUE_CATEGORY[issue.code],
        blocking=_is_blocking(issue, profile),
        score_impact=_issue_penalty(issue) if score_impact is None else score_impact,
    )


def _synthetic_finding(
    *,
    code: str,
    location: str,
    evidence: str,
    suggested_fix: str,
    score_impact: int,
) -> ScoreFinding:
    return ScoreFinding(
        code=code,
        severity=Severity.WARNING.value,
        location=location,
        evidence=evidence,
        suggested_fix=suggested_fix,
        category=ScoreCategory.REVIEWABILITY,
        blocking=False,
        score_impact=score_impact,
    )


def _reviewability_findings(inputs: ScoreInputs) -> list[ScoreFinding]:
    findings: list[ScoreFinding] = []
    if not inputs.review_html_exists:
        findings.append(
            _synthetic_finding(
                code="REVIEW_HTML_MISSING",
                location="review.html",
                evidence="run directory does not contain review.html",
                suggested_fix="Re-run assemble so the offline review page is generated.",
                score_impact=20,
            )
        )
    if not inputs.validation_markdown_exists:
        findings.append(
            _synthetic_finding(
                code="VALIDATION_MARKDOWN_MISSING",
                location="validation/report.md",
                evidence="run directory does not contain validation/report.md",
                suggested_fix="Re-run validation report writing for this run directory.",
                score_impact=10,
            )
        )
    for source in inputs.manifest.local_sources:
        if source.status is ProcessingStatus.UNSUPPORTED:
            findings.append(
                _synthetic_finding(
                    code="SOURCE_UNSUPPORTED",
                    location=f"manifest.json:{source.relative_path}",
                    evidence=f"{source.relative_path} is marked unsupported",
                    suggested_fix="Convert the unsupported input or remove it from the run.",
                    score_impact=10,
                )
            )
        elif source.status is ProcessingStatus.UNREADABLE:
            findings.append(
                _synthetic_finding(
                    code="SOURCE_UNREADABLE",
                    location=f"manifest.json:{source.relative_path}",
                    evidence=f"{source.relative_path} is marked unreadable",
                    suggested_fix="Fix permissions or replace the unreadable source.",
                    score_impact=15,
                )
            )
    return findings


def _category_scores(findings: list[ScoreFinding]) -> dict[str, int]:
    scores = {category.value: 100 for category in ScoreCategory}
    for finding in findings:
        key = finding.category.value
        scores[key] = max(0, scores[key] - finding.score_impact)
    return scores


def _weighted_total(category_scores: dict[str, int]) -> int:
    weighted = sum(
        category_scores[category] * weight
        for category, weight in CATEGORY_WEIGHTS.items()
    )
    return int(round(weighted / 100))


def _status(
    *,
    findings: list[ScoreFinding],
    category_scores: dict[str, int],
    score: int,
    min_score: int,
    profile: ScoreProfile,
) -> ScoreStatus:
    if any(finding.blocking for finding in findings):
        return ScoreStatus.FAIL
    if score < min_score:
        return ScoreStatus.FAIL
    category_gate = 70 if profile is ScoreProfile.CI else 60
    if any(value < category_gate for value in category_scores.values()):
        return ScoreStatus.NEEDS_ATTENTION
    if findings:
        return ScoreStatus.NEEDS_ATTENTION
    return ScoreStatus.PASS


def evaluate_score(
    inputs: ScoreInputs,
    *,
    profile: ScoreProfile = ScoreProfile.CI,
    min_score: int | None = None,
) -> ScoreReport:
    threshold = resolved_min_score(profile, min_score)
    findings = [
        _finding_from_issue(
            issue,
            profile,
            score_impact=0 if _declared_example_gap(issue, inputs.plan) else None,
        )
        for issue in inputs.validation.issues
    ]
    findings.extend(_reviewability_findings(inputs))
    category_scores = _category_scores(findings)
    score = _weighted_total(category_scores)
    blocking_findings = [finding for finding in findings if finding.blocking]
    return ScoreReport(
        status=_status(
            findings=findings,
            category_scores=category_scores,
            score=score,
            min_score=threshold,
            profile=profile,
        ),
        score=score,
        profile=profile,
        min_score=threshold,
        category_scores=category_scores,
        blocking_findings=blocking_findings,
        findings=findings,
    )
