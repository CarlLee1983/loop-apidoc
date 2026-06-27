from datetime import datetime, timezone

from loop_apidoc.generate.markdown import REQUIRED_MARKDOWN_SECTIONS, build_markdown
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import (
    CryptoScheme,
    IntegrationContract,
    NormalizationPlan,
    PlanItemStatus,
)


def _manifest() -> Manifest:
    return Manifest(sources_root=".", generated_at=datetime(2026, 6, 28, tzinfo=timezone.utc))


def test_section_header_registered():
    assert "## 整合機制" in REQUIRED_MARKDOWN_SECTIONS


def test_section_renders_crypto():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            crypto=[CryptoScheme(status=PlanItemStatus.SUPPORTED, name="TradeInfo 加密", algorithm="AES")]
        ),
    )
    md = build_markdown(plan, _manifest())
    assert "## 整合機制" in md
    assert "TradeInfo 加密" in md
    assert "AES" in md


def test_section_placeholder_when_absent():
    plan = NormalizationPlan(notebook_url="x")
    md = build_markdown(plan, _manifest())
    assert "## 整合機制" in md
    assert "來源未提供整合機制資訊" in md
