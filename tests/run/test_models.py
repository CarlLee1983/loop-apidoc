from __future__ import annotations

from loop_apidoc.run.models import RunResult, RunStatus
from loop_apidoc.validate.models import ValidationReport


def test_run_result_ok_only_when_passed() -> None:
    report = ValidationReport(issues=[])
    passed = RunResult(
        run_id="r1", run_dir="/tmp/r1", report=report, rounds=0, status=RunStatus.PASSED
    )
    failed = RunResult(
        run_id="r1", run_dir="/tmp/r1", report=report, rounds=3, status=RunStatus.FAILED
    )
    assert passed.ok is True
    assert failed.ok is False
