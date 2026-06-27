from datetime import datetime, timezone

from loop_apidoc.manifest.models import LocalSource, Manifest, ProcessingStatus, SourceFormat
from loop_apidoc.plan.integration import build_integration_contract
from loop_apidoc.plan.models import NormalizationPlan, PlanItemStatus


def _manifest() -> Manifest:
    return Manifest(
        sources_root=".",
        generated_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
        local_sources=[
            LocalSource(
                relative_path="newebpay.pdf",
                mime_type="application/pdf",
                source_format=SourceFormat.PDF,
                size_bytes=1024,
                sha256="abc123",
                scanned_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
                supported=True,
                status=ProcessingStatus.PENDING,
            )
        ],
    )


def test_none_input_yields_empty_contract():
    contract = build_integration_contract(None, NormalizationPlan(notebook_url="x"), _manifest())
    assert contract.crypto == []
    assert contract.callbacks == []
    assert contract.missing == []


def test_crypto_scheme_built_and_cited():
    payload = {
        "crypto": [
            {
                "name": "TradeInfo 加密",
                "purpose": "request",
                "algorithm": "AES",
                "mode": "CBC",
                "key_source": {"key": "HashKey", "iv": "HashIV"},
                "payload_assembly": [{"step": 1, "desc": "query string 化", "fields": ["MerchantID"]}],
                "verify": {"field": "TradeSha", "method": "SHA256"},
                "source": "newebpay.pdf p.12",
            }
        ]
    }
    contract = build_integration_contract(payload, NormalizationPlan(notebook_url="x"), _manifest())
    assert len(contract.crypto) == 1
    scheme = contract.crypto[0]
    assert scheme.algorithm == "AES"
    assert scheme.key_source.key == "HashKey"
    assert scheme.payload_assembly[0].step == 1
    assert scheme.status is PlanItemStatus.SUPPORTED
    assert scheme.citations[0].locator == "newebpay.pdf p.12"


def test_explicit_missing_recorded_not_failed():
    payload = {"missing": [{"area": "crypto.padding", "detail": "來源未述 padding"}]}
    contract = build_integration_contract(payload, NormalizationPlan(notebook_url="x"), _manifest())
    assert contract.missing[0].area == "crypto.padding"
