from __future__ import annotations

import json

import loop_apidoc.shadow.report as report_mod
import loop_apidoc.shadow.runner as runner_mod
import pytest
from loop_apidoc.run.models import RunStatus
from loop_apidoc.shadow.report import run_shadow_safely, write_shadow_artifacts
from loop_apidoc.shadow.runner import execute_shadow
from loop_apidoc.source_facts.models import FactIndex
from loop_apidoc.validate.models import ValidationReport
from tests.shadow.test_runner import NOW, _manifest, _plan


EXPECTED_FILES = {
    "source-set.json",
    "evidence.json",
    "runtime-result.json",
    "claims.json",
    "relationships.json",
    "contract.json",
    "decision.json",
    "workflow.json",
    "events.json",
    "comparison.json",
    "projections",
}

EXPECTED_PROJECTIONS = {
    "openapi.json",
    "review-data.json",
    "provenance.json",
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
    assert {
        path.name for path in (tmp_path / "core" / "projections").iterdir()
    } == EXPECTED_PROJECTIONS
    comparison = json.loads(
        (tmp_path / "core" / "comparison.json").read_text(encoding="utf-8")
    )
    assert comparison["core_verdict"] == "accept"
    relationships = json.loads(
        (tmp_path / "core" / "relationships.json").read_text(encoding="utf-8")
    )
    assert relationships
    assert {
        relationship["relationship"] for relationship in relationships
    } == {"insufficient"}
    assert "entries" in json.loads(
        (tmp_path / "core" / "projections" / "provenance.json").read_text(
            encoding="utf-8"
        )
    )
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


def test_safe_entry_point_classifies_acquisition_failure(tmp_path, monkeypatch):
    def fail_acquisition(*_args, **_kwargs):
        raise OSError("source read failed")

    monkeypatch.setattr(
        runner_mod,
        "acquire_fragment_bundle",
        fail_acquisition,
    )

    summary = run_shadow_safely(
        manifest=_manifest(),
        plan=_plan(),
        facts=FactIndex(),
        sources_root=tmp_path,
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
        run_dir=tmp_path,
    )

    assert summary.status == "error"
    assert summary.stage.value == "acquisition"


def test_safe_entry_point_classifies_verification_failure(tmp_path, monkeypatch):
    def fail_verification(*_args, **_kwargs):
        raise ValueError("verification failed")

    monkeypatch.setattr(
        runner_mod.EvidenceToContractService,
        "reconcile",
        fail_verification,
    )

    summary = run_shadow_safely(
        manifest=_manifest(),
        plan=_plan(),
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
        run_dir=tmp_path,
    )

    assert summary.status == "error"
    assert summary.stage.value == "verification"


def test_safe_entry_point_classifies_projection_failure(tmp_path, monkeypatch):
    def fail_projection(*_args, **_kwargs):
        raise ValueError("projection failed")

    monkeypatch.setattr(
        runner_mod.OpenApiProjectionCompiler,
        "compile",
        fail_projection,
    )

    summary = run_shadow_safely(
        manifest=_manifest(),
        plan=_plan(),
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
        run_dir=tmp_path,
    )

    assert summary.status == "error"
    assert summary.stage.value == "projection"


@pytest.mark.parametrize(
    ("target", "attribute", "expected_stage"),
    [
        (runner_mod, "build_source_set", "bridge"),
        (
            runner_mod.EvidenceToContractService,
            "register_source_set",
            "service",
        ),
        (
            runner_mod.EvidenceToContractService,
            "build_contract",
            "service",
        ),
        (runner_mod, "compare_results", "comparison"),
    ],
)
def test_safe_entry_point_isolates_remaining_shadow_stage_failures(
    tmp_path,
    monkeypatch,
    target,
    attribute,
    expected_stage,
):
    def fail_stage(*_args, **_kwargs):
        raise RuntimeError("injected shadow failure")

    monkeypatch.setattr(target, attribute, fail_stage)

    summary = run_shadow_safely(
        manifest=_manifest(),
        plan=_plan(),
        legacy_report=ValidationReport(),
        legacy_status=RunStatus.PASSED,
        generated_at=NOW,
        run_dir=tmp_path,
    )

    assert summary.status == "error"
    assert summary.stage.value == expected_stage
    assert json.loads(
        (tmp_path / "core" / "error.json").read_text(encoding="utf-8")
    )["stage"] == expected_stage
