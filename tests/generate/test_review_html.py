from __future__ import annotations

from datetime import datetime

from loop_apidoc.generate.writer import generate_outputs
from loop_apidoc.manifest.models import (
    LocalSource,
    Manifest,
    ProcessingStatus,
    SourceFormat,
    UrlSource,
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
    SourceCitation,
    SourceConflict,
    SystemGroup,
    UnverifiedItem,
)

_NOW = datetime(2026, 6, 30, 10, 0, 0)


def _cite() -> SourceCitation:
    return SourceCitation(
        query_id="06-initial",
        answer_path="answers/06-initial.txt",
        manifest_source="manual.md",
        locator="p.4",
    )


def _manifest() -> Manifest:
    return Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[
            LocalSource(
                relative_path="manual.md",
                mime_type="text/markdown",
                source_format=SourceFormat.MARKDOWN,
                size_bytes=128,
                sha256="abc",
                scanned_at=_NOW,
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )


def test_review_html_visualizes_generated_artifacts_for_manual_review(tmp_path):
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        system_groups=[SystemGroup(name="Loop Pay <Review>", version="v1")],
        environments=[
            EnvironmentEntry(
                status=PlanItemStatus.SUPPORTED,
                name="prod",
                base_url="https://api.example.com",
                citations=[_cite()],
            )
        ],
        security_schemes=[
            SecuritySchemeEntry(
                status=PlanItemStatus.SUPPORTED,
                name="Api Key",
                type="apiKey",
                location="header",
                details="X-API-Key",
                citations=[_cite()],
            )
        ],
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED,
                method="POST",
                path="/pay",
                summary="建立付款",
                parameters=[{"name": "amount", "in": "body", "type": "integer"}],
                responses=[{"status": "200", "description": "ok"}],
                security=["Api Key"],
                citations=[_cite()],
            )
        ],
        schemas=[
            SchemaEntry(
                status=PlanItemStatus.SUPPORTED,
                name="Payment",
                fields=[{"name": "amount", "type": "integer", "required": True}],
                citations=[_cite()],
            )
        ],
        missing_items=[MissingItem(area="endpoint", detail="缺少退款端點")],
        source_conflicts=[SourceConflict(area="auth", detail="章節 A/B 認證名稱不同")],
        unverified_items=[UnverifiedItem(area="schema", detail="欄位 memo 未確認")],
    )
    generate_outputs(plan, _manifest(), tmp_path)

    html = (tmp_path / "review.html").read_text(encoding="utf-8")

    assert '<main class="review-dashboard">' in html
    assert "Loop Pay &lt;Review&gt;" in html
    assert 'href="openapi.yaml"' in html
    assert 'href="api-guide.zh-TW.md"' in html
    assert 'href="examples/README.md"' in html
    assert "POST" in html
    assert "/pay" in html
    assert "建立付款" in html
    assert "Payment" in html
    assert "manual.md" in html
    assert "缺少退款端點" in html
    assert "章節 A/B 認證名稱不同" in html
    assert "欄位 memo 未確認" in html


def test_review_html_renders_url_sources_without_crashing(tmp_path):
    # Regression: a manifest carrying a URL source (assemble --url ...) must not
    # crash review-page generation. UrlSource has no `status` field — its status
    # is derived from http_status.
    manifest = Manifest(
        sources_root="./sources",
        generated_at=_NOW,
        local_sources=[],
        url_sources=[
            UrlSource(
                url="https://docs.example.com/api.html",
                fetched_at=_NOW,
                http_status=200,
            ),
            UrlSource(
                url="https://docs.example.com/missing.html",
                fetched_at=_NOW,
                http_status=None,
            ),
        ],
    )
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED,
                method="GET",
                path="/ping",
                responses=[{"status": "200", "description": "ok"}],
            )
        ],
    )
    generate_outputs(plan, manifest, tmp_path)
    html = (tmp_path / "review.html").read_text(encoding="utf-8")
    assert "https://docs.example.com/api.html" in html
    assert "https://docs.example.com/missing.html" in html


def test_review_html_links_handoff(tmp_path):
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        endpoints=[
            EndpointEntry(
                status=PlanItemStatus.SUPPORTED,
                method="GET",
                path="/ping",
                responses=[{"status": "200", "description": "ok"}],
            )
        ],
    )
    generate_outputs(plan, _manifest(), tmp_path)
    html = (tmp_path / "review.html").read_text(encoding="utf-8")
    assert "handoff/integration-tasks.md" in html


def test_review_html_includes_openapi_derived_error_code_schema(tmp_path):
    plan = NormalizationPlan(
        notebook_url="https://nb/x",
        errors=[
            ErrorEntry(
                status=PlanItemStatus.SUPPORTED,
                code="1001",
                meaning="Invalid token",
                citations=[_cite()],
            )
        ],
    )

    generate_outputs(plan, _manifest(), tmp_path)
    html = (tmp_path / "review.html").read_text(encoding="utf-8")

    assert "<span>Schema</span><strong>1</strong>" in html
    assert "<code>ErrorCode</code>" in html
    assert "有來源" in html
    assert "manual.md" in html
