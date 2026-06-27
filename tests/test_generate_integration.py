from loop_apidoc.generate.integration import (
    build_integration_document,
    integration_provenance_entries,
)
from loop_apidoc.plan.models import (
    Callback,
    CryptoScheme,
    ErrorEntry,
    IntegrationContract,
    NormalizationPlan,
    PlanItemStatus,
    SourceCitation,
)


def _plan_with_contract() -> NormalizationPlan:
    contract = IntegrationContract(
        crypto=[
            CryptoScheme(
                status=PlanItemStatus.SUPPORTED,
                name="TradeInfo 加密",
                algorithm="AES",
                citations=[SourceCitation(query_id="integration", answer_path="integration.json", locator="p.12")],
            )
        ],
        callbacks=[Callback(status=PlanItemStatus.SUPPORTED, name="NotifyURL")],
    )
    return NormalizationPlan(
        notebook_url="x",
        errors=[ErrorEntry(status=PlanItemStatus.SUPPORTED, code="4001", meaning="參數錯誤")],
        integration=contract,
    )


def test_document_none_when_no_contract():
    assert build_integration_document(NormalizationPlan(notebook_url="x")) is None


def test_document_renders_sections_and_reuses_errors():
    doc = build_integration_document(_plan_with_contract())
    assert doc["version"] == "1.0"
    assert doc["crypto"][0]["algorithm"] == "AES"
    assert doc["error_codes"][0]["code"] == "4001"  # reused from plan.errors


def test_provenance_targets_for_contract():
    contract = _plan_with_contract().integration
    targets = {e.target for e in integration_provenance_entries(contract)}
    assert "integration.crypto.TradeInfo 加密" in targets
    assert "integration.callbacks.NotifyURL" in targets
    # error_codes must NOT get an integration.* target
    assert not any(t.startswith("integration.error") for t in targets)


def test_unnamed_crypto_target_does_not_contain_none():
    """An unnamed (name=None) crypto entry must use its index, not the literal 'None'."""
    contract = IntegrationContract(
        crypto=[CryptoScheme(status=PlanItemStatus.SUPPORTED, name=None,
                             citations=[SourceCitation(query_id="i", answer_path="i")])]
    )
    targets = [e.target for e in integration_provenance_entries(contract)]
    assert all(".None" not in t for t in targets), f"Found .None in targets: {targets}"
    assert any("integration.crypto." in t for t in targets)
