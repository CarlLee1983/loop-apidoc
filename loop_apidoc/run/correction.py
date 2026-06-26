from __future__ import annotations

from collections.abc import Callable

from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.run.models import CorrectionCategory, CorrectionOutcome, RunStatus
from loop_apidoc.validate.models import (
    Issue,
    IssueCode,
    Severity,
    ValidationReport,
)

# NOTE on AUTO_FIX (v1 limitation): generation is deterministic from the plan,
# and v1 ships no OpenAPI/output repair transform. So an AUTO_FIX issue with no
# accompanying RE_QUERY issue cannot change between rounds — the loop will
# regenerate the identical (still-invalid) output until max_rounds, then FAIL.
# This consumes no NotebookLM quota (regenerate is local), only compute. In
# practice OPENAPI_INVALID/OUTPUT_MISMATCH should not arise from a valid plan
# (the generator is validated end-to-end). A real autofix transform — or an
# identical-report short-circuit — is a deferred enhancement.
_CATEGORY: dict[IssueCode, CorrectionCategory] = {
    IssueCode.OPENAPI_INVALID: CorrectionCategory.AUTO_FIX,
    IssueCode.OUTPUT_MISMATCH: CorrectionCategory.AUTO_FIX,
    IssueCode.REQUIRED_INFO_MISSING: CorrectionCategory.RE_QUERY,
    IssueCode.SOURCE_UNVERIFIED: CorrectionCategory.UNFIXABLE,
    IssueCode.SOURCE_CONFLICT: CorrectionCategory.UNFIXABLE,
    IssueCode.UNSUPPORTED_ASSERTION: CorrectionCategory.UNFIXABLE,
}


def classify_issue(issue: Issue) -> CorrectionCategory:
    """Map a validation issue to a correction strategy (spec §10).

    Fail-closed: anything not explicitly fixable is UNFIXABLE so the loop
    never speculates over source-missing or conflicting content.
    """
    return _CATEGORY.get(issue.code, CorrectionCategory.UNFIXABLE)


def annotate_fixability(report: ValidationReport) -> ValidationReport:
    """Return a new report with auto_fixable set per classification."""
    issues = [
        issue.model_copy(
            update={"auto_fixable": classify_issue(issue) is CorrectionCategory.AUTO_FIX}
        )
        for issue in report.issues
    ]
    return ValidationReport(issues=issues)


def actionable_codes(report: ValidationReport) -> list[Issue]:
    """Error-severity issues the loop can act on (auto-fix or re-query)."""
    return [
        issue
        for issue in report.issues
        if issue.severity is Severity.ERROR
        and classify_issue(issue)
        in (CorrectionCategory.AUTO_FIX, CorrectionCategory.RE_QUERY)
    ]


def run_correction_loop(
    plan: NormalizationPlan,
    result: GenerateResult,
    *,
    regenerate: Callable[[NormalizationPlan], GenerateResult],
    requery: Callable[[NormalizationPlan, ValidationReport], NormalizationPlan],
    validate: Callable[[NormalizationPlan, GenerateResult], ValidationReport],
    max_rounds: int = 3,
) -> CorrectionOutcome:
    """Run the spec §10 correction loop over injected I/O closures.

    Rounds count post-generation correction attempts (max 3). Stops early when
    the only remaining errors are source-missing/conflict (no quota waste).
    """
    report = validate(plan, result)
    rounds = 0

    while not report.ok and rounds < max_rounds:
        actionable = actionable_codes(report)
        if not actionable:
            return CorrectionOutcome(
                plan=plan,
                result=result,
                report=annotate_fixability(report),
                rounds=rounds,
                status=RunStatus.EARLY_STOPPED,
            )

        rounds += 1
        if any(
            classify_issue(issue) is CorrectionCategory.RE_QUERY for issue in actionable
        ):
            plan = requery(plan, report)
        result = regenerate(plan)
        report = validate(plan, result)

    status = RunStatus.PASSED if report.ok else RunStatus.FAILED
    return CorrectionOutcome(
        plan=plan,
        result=result,
        report=annotate_fixability(report),
        rounds=rounds,
        status=status,
    )
