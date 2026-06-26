from __future__ import annotations

from datetime import datetime

from openapi_spec_validator import validate

from loop_apidoc.generate import REQUIRED_MARKDOWN_SECTIONS, build_result
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
)
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    ErrorEntry,
    NormalizationPlan,
    PlanItemStatus,
    SchemaEntry,
    SecuritySchemeEntry,
    SourceCitation,
    SystemGroup,
)

_NOW = datetime(2026, 6, 25, 12, 0, 0)


def _cite() -> SourceCitation:
    return SourceCitation(query_id="06-initial", answer_path="answers/06-initial.txt",
                          manifest_source="api.md", locator="p.3")


def _manifest() -> Manifest:
    return Manifest(
        sources_root="./sources", generated_at=_NOW,
        local_sources=[LocalSource(
            relative_path="api.md", mime_type="text/markdown",
            source_format=SourceFormat.MARKDOWN, size_bytes=10, sha256="abc",
            scanned_at=_NOW, supported=True, status=ProcessingStatus.PENDING)],
    )


def _full_plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="Loop Payments API")],
        overview_note="支付 API。",
        environments=[EnvironmentEntry(
            status=PlanItemStatus.SUPPORTED, name="prod",
            base_url="https://api.example.com", version="2024-01",
            citations=[_cite()])],
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth", type="apiKey",
            location="header", details="X-API-Key", citations=[_cite()])],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List users",
            parameters=[{"name": "limit", "in": "query", "type": "integer"}],
            responses=[{"status": "200", "description": "ok",
                        "schema": {"type": "array"}}],
            citations=[_cite()])],
        schemas=[SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="User",
            fields=[{"name": "id", "type": "string", "required": True}],
            citations=[_cite()])],
        errors=[ErrorEntry(status=PlanItemStatus.SUPPORTED, code="40001",
                           meaning="參數錯誤", http_status="400", citations=[_cite()])],
    )


def test_full_plan_produces_valid_openapi():
    result = build_result(_full_plan(), _manifest())
    validate(result.openapi)  # raises on invalid 3.1 document


def test_markdown_has_all_sections():
    md = build_result(_full_plan(), _manifest()).markdown
    for section in REQUIRED_MARKDOWN_SECTIONS:
        assert section in md


def test_provenance_targets_align_with_openapi():
    result = build_result(_full_plan(), _manifest())
    targets = {e.target for e in result.provenance.entries}
    assert "paths./users.get" in targets
    assert "components.schemas.User" in targets
    assert "components.securitySchemes.ApiKeyAuth" in targets
    assert "servers[0]" in targets
    supported = next(e for e in result.provenance.entries
                     if e.target == "paths./users.get")
    assert supported.status is PlanItemStatus.SUPPORTED
    assert supported.manifest_source == "api.md"


def test_missing_source_marked_in_openapi_and_provenance():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[EndpointEntry(status=PlanItemStatus.SUPPORTED,
                                 method="GET", path="/ping")],
    )
    result = build_result(plan, _manifest())
    validate(result.openapi)
    responses = result.openapi["paths"]["/ping"]["get"]["responses"]
    assert responses["default"]["x-loop-status"] == "missing-source"
    info = result.openapi["info"]
    assert info["x-loop-status"] == "missing-source"
    statuses = {e.target: e.status for e in result.provenance.entries}
    assert statuses["info.title"] is PlanItemStatus.MISSING
