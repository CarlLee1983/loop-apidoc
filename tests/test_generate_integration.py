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


def test_document_entries_keep_source_and_provenance_target():
    """integration-contract.json 的每筆條目保留 source 與可反查的 provenance_target。"""
    doc = build_integration_document(_plan_with_contract())
    crypto = doc["crypto"][0]
    assert crypto["source"] == "p.12"
    assert crypto["provenance_target"] == "integration.crypto.TradeInfo 加密"
    # 無 citation 的條目 source 為 None（記錄缺漏，不臆測）
    assert doc["callbacks"][0]["source"] is None
    assert doc["callbacks"][0]["provenance_target"] == "integration.callbacks.NotifyURL"
    # 內部簿記仍不外流
    assert "citations" not in crypto and "status" not in crypto


def test_document_provenance_target_matches_provenance_entries():
    """product 檔的 provenance_target 必須與 provenance.json 的 target 完全一致。"""
    plan = _plan_with_contract()
    doc = build_integration_document(plan)
    targets = {e.target for e in integration_provenance_entries(plan.integration)}
    for section in ("crypto", "callbacks", "field_conditions", "test_cases"):
        for entry in doc[section]:
            assert entry["provenance_target"] in targets


def test_field_condition_target_uses_index():
    from loop_apidoc.plan.models import FieldCondition

    contract = IntegrationContract(
        field_conditions=[
            FieldCondition(status=PlanItemStatus.SUPPORTED, rule="A",
                           citations=[SourceCitation(query_id="i", answer_path="i",
                                                     locator="doc.pdf p.10")]),
        ]
    )
    plan = NormalizationPlan(notebook_url="x", integration=contract)
    doc = build_integration_document(plan)
    assert doc["field_conditions"][0]["source"] == "doc.pdf p.10"
    assert doc["field_conditions"][0]["provenance_target"] == "integration.field_conditions.0"
