from __future__ import annotations

from loop_apidoc.run.correction import run_correction_loop
from loop_apidoc.run.models import RunStatus
from loop_apidoc.generate.models import GenerateResult, ProvenanceDocument
from loop_apidoc.plan.models import NormalizationPlan
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def _plan() -> NormalizationPlan:
    return NormalizationPlan(notebook_url="nb://x")


def _result() -> GenerateResult:
    return GenerateResult(
        openapi={"openapi": "3.1.0"},
        markdown="# doc",
        provenance=ProvenanceDocument(notebook_url="nb", entries=[]),
    )


def _missing_report() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.REQUIRED_INFO_MISSING,
                severity=Severity.ERROR,
                location="paths./x.get",
                evidence="no responses",
                suggested_fix="add responses",
            )
        ]
    )


def _conflict_report() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.SOURCE_CONFLICT,
                severity=Severity.ERROR,
                location="paths./x.get",
                evidence="two sources disagree",
                suggested_fix="resolve at source",
            )
        ]
    )


def test_passes_on_first_validation() -> None:
    outcome = run_correction_loop(
        _plan(),
        _result(),
        regenerate=lambda p: _result(),
        requery=lambda p, r: p,
        validate=lambda p, r: ValidationReport(issues=[]),
    )
    assert outcome.status is RunStatus.PASSED
    assert outcome.rounds == 0


def test_recovers_within_three_rounds() -> None:
    reports = [_missing_report(), _missing_report(), ValidationReport(issues=[])]
    calls = {"n": 0}

    def validate(p, r):
        report = reports[calls["n"]]
        calls["n"] += 1
        return report

    requeries = {"n": 0}

    def requery(p, r):
        requeries["n"] += 1
        return p

    outcome = run_correction_loop(
        _plan(), _result(), regenerate=lambda p: _result(), requery=requery, validate=validate
    )
    assert outcome.status is RunStatus.PASSED
    assert outcome.rounds == 2
    assert requeries["n"] == 2


def test_final_failure_after_three_rounds() -> None:
    outcome = run_correction_loop(
        _plan(),
        _result(),
        regenerate=lambda p: _result(),
        requery=lambda p, r: p,
        validate=lambda p, r: _missing_report(),
    )
    assert outcome.status is RunStatus.FAILED
    assert outcome.rounds == 3


def test_early_stop_on_unfixable_only() -> None:
    requeries = {"n": 0}

    def requery(p, r):
        requeries["n"] += 1
        return p

    outcome = run_correction_loop(
        _plan(),
        _result(),
        regenerate=lambda p: _result(),
        requery=requery,
        validate=lambda p, r: _conflict_report(),
    )
    assert outcome.status is RunStatus.EARLY_STOPPED
    assert outcome.rounds == 0
    assert requeries["n"] == 0  # no NotebookLM quota wasted


def test_auto_fix_only_does_not_requery() -> None:
    auto_fix_report = ValidationReport(
        issues=[
            Issue(
                code=IssueCode.OPENAPI_INVALID,
                severity=Severity.ERROR,
                location="paths",
                evidence="invalid schema",
                suggested_fix="fix schema",
            )
        ]
    )
    requeries = {"n": 0}

    def requery(p, r):
        requeries["n"] += 1
        return p

    outcome = run_correction_loop(
        _plan(),
        _result(),
        regenerate=lambda p: _result(),
        requery=requery,
        validate=lambda p, r: auto_fix_report,
    )
    assert outcome.status is RunStatus.FAILED
    assert outcome.rounds == 3
    assert requeries["n"] == 0  # AUTO_FIX-only never triggers requery
