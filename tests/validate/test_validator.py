from __future__ import annotations

from datetime import datetime

from loop_apidoc.generate import build_result
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
from loop_apidoc.validate import validate_outputs

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


def test_good_outputs_validate_clean():
    plan = _good_plan()
    report = validate_outputs(plan, build_result(plan, _manifest()), _manifest())
    assert report.ok is True, [i.model_dump() for i in report.errors()]


def test_missing_method_makes_report_not_ok():
    plan = _good_plan()
    plan.endpoints[0].method = None
    report = validate_outputs(plan, build_result(plan, _manifest()), _manifest())
    assert report.ok is False


def test_unreadable_source_makes_report_not_ok():
    plan = _good_plan()
    manifest = Manifest(
        sources_root="./sources", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="broken.pdf", mime_type=None,
            source_format=SourceFormat.PDF, size_bytes=10, sha256="abc",
            scanned_at=_NOW, supported=False, status=ProcessingStatus.UNREADABLE)])
    report = validate_outputs(plan, build_result(plan, _manifest()), manifest)
    assert report.ok is False
    unverified = [i for i in report.errors() if i.location == "broken.pdf"]
    assert len(unverified) == 1


def test_unsupported_source_warns_but_report_stays_ok():
    plan = _good_plan()
    manifest = Manifest(
        sources_root="./sources", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="logo.png", mime_type=None,
            source_format=SourceFormat.UNKNOWN, size_bytes=10, sha256="abc",
            scanned_at=_NOW, supported=False, status=ProcessingStatus.UNSUPPORTED)])
    report = validate_outputs(plan, build_result(plan, _manifest()), manifest)
    assert report.ok is True
    assert any(i.location == "logo.png" for i in report.warnings())
