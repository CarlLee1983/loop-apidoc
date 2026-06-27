from __future__ import annotations

from datetime import datetime

from loop_apidoc.generate.markdown import REQUIRED_MARKDOWN_SECTIONS, build_markdown
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
    MissingItem,
    NormalizationPlan,
    PlanItemStatus,
    SecuritySchemeEntry,
    SystemGroup,
)

_NOW = datetime(2026, 6, 25, 12, 0, 0)


def _manifest() -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="api.md", mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN, size_bytes=10,
                sha256="abc", scanned_at=_NOW, supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )


def _full_plan() -> NormalizationPlan:
    return NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="Loop Payments API")],
        overview_note="這是支付 API。",
        environments=[EnvironmentEntry(
            status=PlanItemStatus.SUPPORTED, name="prod",
            base_url="https://api.example.com", version="2024-01")],
        security_schemes=[SecuritySchemeEntry(
            status=PlanItemStatus.SUPPORTED, name="ApiKeyAuth",
            type="apiKey", location="header", details="X-API-Key")],
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/users",
            summary="List users",
            examples=[{"title": "list", "body": "GET /users"}])],
        errors=[ErrorEntry(status=PlanItemStatus.SUPPORTED, code="40001",
                           meaning="參數錯誤", http_status="400")],
        missing_items=[MissingItem(area="09", detail="未提供 rate limit")],
    )


def test_all_required_sections_present_and_ordered():
    md = build_markdown(_full_plan(), _manifest())
    positions = [md.find(section) for section in REQUIRED_MARKDOWN_SECTIONS]
    assert all(p >= 0 for p in positions)
    assert positions == sorted(positions)


def test_title_heading_first_line():
    md = build_markdown(_full_plan(), _manifest())
    assert md.splitlines()[0] == "# Loop Payments API"


def test_original_api_names_preserved():
    md = build_markdown(_full_plan(), _manifest())
    assert "`/users`" in md
    assert "`GET`" in md
    assert "`X-API-Key`" in md
    assert "`40001`" in md


def test_source_listed_in_scope_section():
    md = build_markdown(_full_plan(), _manifest())
    assert "api.md" in md


def test_missing_item_surfaced():
    md = build_markdown(_full_plan(), _manifest())
    assert "未提供 rate limit" in md


def test_webhook_endpoint_rendered_as_webhook_not_path():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path=None,
            summary="付款結果通知（callback）",
            responses=[{"status": "200", "description": "1|OK"}])],
    )
    md = build_markdown(plan, _manifest())
    assert "### Webhook `付款結果通知`（method `POST`）" in md
    # must NOT emit a phantom path endpoint for the null path
    assert "### `POST` `-`" not in md


def test_empty_plan_still_has_all_sections():
    md = build_markdown(NormalizationPlan(notebook_url="https://nb/x"), _manifest())
    for section in REQUIRED_MARKDOWN_SECTIONS:
        assert section in md
