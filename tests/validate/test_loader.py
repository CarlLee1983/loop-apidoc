from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from loop_apidoc.generate import generate_outputs
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    NormalizationPlan,
    OperationalEntry,
    PlanItemStatus,
    SecuritySchemeEntry,
    SourceCitation,
    SystemGroup,
)
from loop_apidoc.validate import validate_run_dir
from loop_apidoc.validate.models import IssueCode

_NOW = datetime(2026, 6, 26, 12, 0, 0)


def _cite() -> SourceCitation:
    return SourceCitation(query_id="06", answer_path="answers/06.txt",
                          manifest_source="api.md", locator="p.1")


def _manifest() -> Manifest:
    return Manifest(
        sources_root="./sources", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="api.md", mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=10, sha256="abc",
            scanned_at=_NOW, supported=True, status=ProcessingStatus.PENDING)])


def _plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="Loop API")],
        overview_note="API。",
        environments=[EnvironmentEntry(
            status=PlanItemStatus.SUPPORTED, name="prod",
            base_url="https://api.example.com", version="2024-01", citations=[_cite()])],
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth", type="apiKey",
            location="header", details="X-API-Key", citations=[_cite()])],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List", responses=[{"status": "200", "description": "ok"}],
            examples=[{"body": "{}"}], citations=[_cite()])],
        operational=[OperationalEntry(status=PlanItemStatus.SUPPORTED,
                                      topic="rate", detail="60/min", citations=[_cite()])])


def _write_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    manifest = _manifest()
    generate_outputs(_plan(), manifest, run_dir)
    (run_dir / "plan").mkdir(parents=True, exist_ok=True)
    (run_dir / "plan" / "normalization-plan.json").write_text(
        _plan().model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8")
    return run_dir


def test_good_run_dir_validates_clean(tmp_path):
    report = validate_run_dir(_write_run_dir(tmp_path))
    assert report.ok is True, [i.model_dump() for i in report.errors()]


def test_unparseable_yaml_is_openapi_invalid(tmp_path):
    run_dir = _write_run_dir(tmp_path)
    (run_dir / "openapi.yaml").write_text("a: b:\n  - [unclosed", encoding="utf-8")
    report = validate_run_dir(run_dir)
    assert report.ok is False
    assert any(i.code is IssueCode.OPENAPI_INVALID for i in report.issues)


def test_invalid_provenance_json_is_output_mismatch(tmp_path):
    run_dir = _write_run_dir(tmp_path)
    (run_dir / "provenance.json").write_text('{"bad": true}', encoding="utf-8")
    report = validate_run_dir(run_dir)
    assert report.ok is False
    assert any(i.code is IssueCode.OUTPUT_MISMATCH for i in report.issues)


def test_unreadable_file_does_not_crash(tmp_path):
    import pytest
    run_dir = _write_run_dir(tmp_path)
    openapi_file = run_dir / "openapi.yaml"

    # Make the file unreadable by removing all permissions
    openapi_file.chmod(0o000)

    try:
        # Check if we can actually make it unreadable (not effective as root)
        if os.access(openapi_file, os.R_OK):
            pytest.skip("cannot make file unreadable as current user")

        # Call validate_run_dir; it must not raise OSError, must return ValidationReport
        report = validate_run_dir(run_dir)

        # Verify it returns a valid ValidationReport with an error
        assert report.ok is False
        assert any(i.code is IssueCode.OUTPUT_MISMATCH for i in report.issues)
    finally:
        # Restore permissions so pytest cleanup of tmp_path can remove it
        openapi_file.chmod(0o644)
