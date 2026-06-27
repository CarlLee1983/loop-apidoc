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
    SchemaEntry,
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


def test_duplicate_missing_items_deduped_in_gaps():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        missing_items=[
            MissingItem(area="03", detail="無完整錯誤碼"),
            MissingItem(area="04", detail="無完整錯誤碼"),
            MissingItem(area="05", detail="無完整錯誤碼"),
        ],
    )
    md = build_markdown(plan, _manifest())
    assert md.count("無完整錯誤碼") == 1


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


def test_endpoint_body_params_show_description_required_and_nesting():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="POST", path="/pay",
            summary="pay [NPA-F01]",
            tags=["信用卡"], security=["AES256 簽章"],
            parameters=[
                {"name": "MerchantID", "in": "body", "type": "String(15)",
                 "required": True, "description": "商店代號"},
                {"name": "OrderDetail", "in": "body", "type": "array",
                 "description": "訂單細項"},
                {"name": "OrderDetail[].ItemName", "in": "body", "type": "String(20)",
                 "required": True, "description": "品名"},
            ],
            responses=[{"status": "SUCCESS", "description": "成功",
                        "schema_ref": "PayResult"}],
        )],
    )
    md = build_markdown(plan, _manifest())
    # field descriptions are no longer dropped
    assert "商店代號" in md
    assert "品名" in md
    assert "必填" in md
    # tags + security surfaced per endpoint
    assert "信用卡" in md
    assert "AES256 簽章" in md
    # the array child renders indented with its short label, not the bracket name
    assert "  - `ItemName`" in md
    assert "OrderDetail[].ItemName" not in md
    # the response's linked component is shown
    assert "PayResult" in md


def test_query_param_shows_description():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[EndpointEntry(
            status=PlanItemStatus.SUPPORTED, method="GET", path="/u/{id}",
            parameters=[{"name": "id", "in": "path", "type": "string",
                         "required": True, "description": "使用者 id"}],
            responses=[{"status": "200", "description": "ok"}],
        )],
    )
    md = build_markdown(plan, _manifest())
    assert "使用者 id" in md
    assert "`id`" in md


def test_schema_fields_show_description_and_nesting():
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        schemas=[SchemaEntry(
            status=PlanItemStatus.SUPPORTED, name="Order",
            fields=[
                {"name": "Status", "type": "string", "description": "狀態"},
                {"name": "Items[].Sku", "type": "string", "required": True,
                 "description": "貨號"},
            ],
        )],
    )
    md = build_markdown(plan, _manifest())
    assert "狀態" in md
    assert "貨號" in md
    assert "  - `Sku`" in md
    assert "Items[].Sku" not in md


def test_empty_plan_still_has_all_sections():
    md = build_markdown(NormalizationPlan(notebook_url="https://nb/x"), _manifest())
    for section in REQUIRED_MARKDOWN_SECTIONS:
        assert section in md
