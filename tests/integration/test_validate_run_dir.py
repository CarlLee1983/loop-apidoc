from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from loop_apidoc.cli import app
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

runner = CliRunner()
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


def _good_plan() -> NormalizationPlan:
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


def _setup_run_dir(tmp_path, plan):
    run_dir = tmp_path / "run"
    manifest = _manifest()
    generate_outputs(plan, manifest, run_dir)
    (run_dir / "plan").mkdir(parents=True, exist_ok=True)
    (run_dir / "plan" / "normalization-plan.json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8")
    return run_dir


def test_validate_command_passes_and_writes_reports(tmp_path):
    run_dir = _setup_run_dir(tmp_path, _good_plan())
    result = runner.invoke(app, ["validate", "--output", str(run_dir)])
    assert result.exit_code == 0, result.output
    assert (run_dir / "validation" / "report.json").exists()
    assert (run_dir / "validation" / "report.md").exists()


def test_validate_command_fails_on_missing_method(tmp_path):
    plan = _good_plan()
    plan.endpoints[0].method = None
    run_dir = _setup_run_dir(tmp_path, plan)
    result = runner.invoke(app, ["validate", "--output", str(run_dir)])
    assert result.exit_code == 1
    assert (run_dir / "validation" / "report.json").exists()
