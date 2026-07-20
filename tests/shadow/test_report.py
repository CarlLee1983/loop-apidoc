from __future__ import annotations

import json

import loop_apidoc.shadow.report as report_mod
from loop_apidoc.run.models import RunStatus
from loop_apidoc.shadow.report import run_shadow_safely, write_shadow_artifacts
from loop_apidoc.shadow.runner import execute_shadow
from loop_apidoc.validate.models import ValidationReport
from tests.shadow.test_runner import NOW, _manifest, _plan


EXPECTED_FILES = {
    "source-set.json",
    "evidence.json",
    "runtime-result.json",
    "claims.json",
    "contract.json",
    "decision.json",
    "workflow.json",
    "events.json",
    "comparison.json",
}


def test_report_writes_complete_stable_artifact_set(tmp_path):
    artifacts = execute_shadow(
        manifest=_manifest(),
        plan=_plan(),
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
    )

    summary = write_shadow_artifacts(artifacts, tmp_path / "core")

    assert summary.status == "ok"
    assert summary.comparison_path == str(tmp_path / "core" / "comparison.json")
    assert {path.name for path in (tmp_path / "core").iterdir()} == EXPECTED_FILES
    comparison = json.loads(
        (tmp_path / "core" / "comparison.json").read_text(encoding="utf-8")
    )
    assert comparison["core_verdict"] == "accept"
    assert (
        (tmp_path / "core" / "source-set.json").read_text(encoding="utf-8")
        .endswith("\n")
    )


def test_safe_entry_point_converts_metadata_failure_to_error_json(tmp_path):
    plan = _plan().model_copy(
        update={"system_groups": [_plan().system_groups[0].model_copy(update={"version": None})]}
    )

    summary = run_shadow_safely(
        manifest=_manifest(),
        plan=plan,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
        run_dir=tmp_path,
    )

    assert summary.status == "error"
    assert summary.stage.value == "bridge"
    assert json.loads(
        (tmp_path / "core" / "error.json").read_text(encoding="utf-8")
    ) == {
        "exception_type": "ShadowMetadataError",
        "message": "shadow contract metadata requires a source-stated title and version",
        "stage": "bridge",
        "status": "error",
    }


def test_safe_entry_point_returns_in_memory_error_when_error_report_cannot_write(
    tmp_path,
):
    (tmp_path / "core").write_text("not a directory", encoding="utf-8")
    plan = _plan().model_copy(update={"system_groups": []})

    summary = run_shadow_safely(
        manifest=_manifest(),
        plan=plan,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
        run_dir=tmp_path,
    )

    assert summary.status == "error"
    assert summary.error_path is None
    assert summary.exception_type == "ShadowMetadataError"


def test_report_failure_leaves_only_error_json(tmp_path, monkeypatch):
    original = report_mod._write_json
    calls = 0

    def fail_during_success_set(path, payload):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("simulated partial report failure")
        original(path, payload)

    monkeypatch.setattr(report_mod, "_write_json", fail_during_success_set)

    summary = run_shadow_safely(
        manifest=_manifest(),
        plan=_plan(),
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
        run_dir=tmp_path,
    )

    assert summary.status == "error"
    assert summary.stage.value == "report"
    assert {path.name for path in (tmp_path / "core").iterdir()} == {"error.json"}
