from loop_apidoc.plan.models import (
    CryptoScheme,
    CryptoStep,
    IntegrationContract,
    NormalizationPlan,
    PlanItemStatus,
)


def test_crypto_scheme_defaults_and_cited():
    scheme = CryptoScheme(status=PlanItemStatus.SUPPORTED, name="TradeInfo 加密")
    assert scheme.algorithm is None
    assert scheme.payload_assembly == []
    assert scheme.citations == []
    assert scheme.status is PlanItemStatus.SUPPORTED


def test_crypto_step_order_preserved():
    steps = [CryptoStep(step=2, desc="b"), CryptoStep(step=1, desc="a")]
    contract = IntegrationContract(
        crypto=[CryptoScheme(status=PlanItemStatus.SUPPORTED, payload_assembly=steps)]
    )
    assert [s.step for s in contract.crypto[0].payload_assembly] == [2, 1]


def test_plan_integration_defaults_none():
    plan = NormalizationPlan(notebook_url="x")
    assert plan.integration is None
    plan2 = plan.model_copy(update={"integration": IntegrationContract()})
    assert plan2.integration.version == "1.0"
