from __future__ import annotations

from loop_apidoc.run.correction import run_correction_loop
from loop_apidoc.run.models import RunStatus
from loop_apidoc.generate.models import GenerateResult, ProvenanceDocument
from loop_apidoc.plan.models import EndpointEntry, NormalizationPlan, SourceCitation
from loop_apidoc.validate.models import Issue, IssueCode, Severity, ValidationReport


def _result() -> GenerateResult:
    return GenerateResult(
        openapi={"openapi": "3.1.0", "paths": {}},
        markdown="# doc",
        provenance=ProvenanceDocument(notebook_url="nb", entries=[]),
    )


def _missing() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.REQUIRED_INFO_MISSING,
                severity=Severity.ERROR,
                location="paths./x.get",
                evidence="missing responses",
                suggested_fix="re-query stage 06",
            )
        ]
    )


def _ok() -> ValidationReport:
    return ValidationReport(issues=[])


def _conflict() -> ValidationReport:
    return ValidationReport(
        issues=[
            Issue(
                code=IssueCode.SOURCE_CONFLICT,
                severity=Severity.ERROR,
                location="paths./x.get",
                evidence="sources disagree",
                suggested_fix="resolve at source",
            )
        ]
    )


def test_three_round_success() -> None:
    # Fails round 1 and 2, passes on round 3 (rounds==2 since round 0 is initial).
    seq = [_missing(), _missing(), _ok()]
    i = {"n": 0}

    def validate(p, r):
        rep = seq[i["n"]]
        i["n"] += 1
        return rep

    outcome = run_correction_loop(
        NormalizationPlan(notebook_url="nb"),
        _result(),
        regenerate=lambda p: _result(),
        requery=lambda p, r: p,
        validate=validate,
    )
    assert outcome.status is RunStatus.PASSED
    assert outcome.rounds == 2


def test_final_failure_persists_artifacts_state() -> None:
    outcome = run_correction_loop(
        NormalizationPlan(notebook_url="nb"),
        _result(),
        regenerate=lambda p: _result(),
        requery=lambda p, r: p,
        validate=lambda p, r: _missing(),
    )
    assert outcome.status is RunStatus.FAILED
    assert outcome.rounds == 3
    # Report carries fixability annotation for downstream rendering.
    assert outcome.report.issues[0].auto_fixable is False


def test_early_stop_conflict_only_no_rounds() -> None:
    outcome = run_correction_loop(
        NormalizationPlan(notebook_url="nb"),
        _result(),
        regenerate=lambda p: _result(),
        requery=lambda p, r: p,
        validate=lambda p, r: _conflict(),
    )
    assert outcome.status is RunStatus.EARLY_STOPPED
    assert outcome.rounds == 0
