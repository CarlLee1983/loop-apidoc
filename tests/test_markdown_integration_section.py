from datetime import datetime, timezone

from loop_apidoc.generate.markdown import REQUIRED_MARKDOWN_SECTIONS, build_markdown
from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.models import (
    AmountDirection,
    CryptoScheme,
    IdempotencyRule,
    IntegrationContract,
    LineCurrencyPolicy,
    NormalizationPlan,
    PlanItemStatus,
    TransportPolicy,
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


def test_section_renders_source_grounded_domain_semantics():
    plan = NormalizationPlan(
        notebook_url="x",
        integration=IntegrationContract(
            transport=[
                TransportPolicy(
                    status=PlanItemStatus.SUPPORTED,
                    name="HTTP defaults",
                    protocol="HTTPS",
                    http_status="Business failures also return HTTP 200.",
                )
            ],
            amount_direction=[
                AmountDirection(
                    status=PlanItemStatus.SUPPORTED,
                    operation_ref="POST /deposit",
                    balance_effect="credit",
                    amount_sign="positive",
                )
            ],
            idempotency=[
                IdempotencyRule(
                    status=PlanItemStatus.SUPPORTED,
                    code="9",
                    action="Treat the original transaction as processed.",
                )
            ],
            line_currency_policy=[
                LineCurrencyPolicy(
                    status=PlanItemStatus.SUPPORTED,
                    scope="Agent line",
                    policy="single",
                    currency_binding="agent",
                )
            ],
        ),
    )

    md = build_markdown(plan, _manifest())

    assert "傳輸政策：HTTP defaults" in md
    assert "Business failures also return HTTP 200." in md
    assert "金額方向：POST /deposit" in md
    assert "`credit`" in md and "`positive`" in md
    assert "冪等規則：9" in md
    assert "Treat the original transaction as processed." in md
    assert "線路幣別政策：Agent line" in md
    assert "`single`" in md and "`agent`" in md
