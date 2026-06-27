from __future__ import annotations

from loop_apidoc.generate.models import ProvenanceEntry
from loop_apidoc.generate.provenance import _entries
from loop_apidoc.plan.models import IntegrationContract, NormalizationPlan


def _error_codes(plan: NormalizationPlan) -> list[dict]:
    return [
        {"code": e.code, "meaning": e.meaning, "http_status": e.http_status}
        for e in plan.errors
    ]


def _base_urls(plan: NormalizationPlan) -> list[dict]:
    return [
        {"name": e.name, "base_url": e.base_url, "version": e.version}
        for e in plan.environments
    ]


def build_integration_document(plan: NormalizationPlan) -> dict | None:
    """Serialize plan.integration into the integration-contract.json dict (pure).

    crypto/callbacks/field_conditions/test_cases come from the extracted
    contract; error_codes/base_urls are reused from already-structured plan data
    so the same fact is never grounded twice.
    """
    contract = plan.integration
    if contract is None:
        return None
    payload = contract.model_dump(exclude={"missing"}, exclude_none=False)
    payload["api_title"] = plan.resolved_title
    payload["base_urls"] = _base_urls(plan)
    payload["error_codes"] = _error_codes(plan)
    payload["missing"] = [m.model_dump() for m in contract.missing]
    # Drop per-entry provenance bookkeeping from the product file; provenance.json
    # carries the source mapping.
    for section in ("crypto", "callbacks", "field_conditions", "test_cases"):
        for entry in payload.get(section, []):
            entry.pop("status", None)
            entry.pop("citations", None)
    return payload


def integration_provenance_entries(
    contract: IntegrationContract,
) -> list[ProvenanceEntry]:
    """One provenance group per contract leaf (error_codes excluded — reused)."""
    out: list[ProvenanceEntry] = []
    for scheme in contract.crypto:
        out += _entries(f"integration.crypto.{scheme.name}", scheme)
    for cb in contract.callbacks:
        out += _entries(f"integration.callbacks.{cb.name}", cb)
    for idx, cond in enumerate(contract.field_conditions):
        out += _entries(f"integration.field_conditions.{idx}", cond)
    for case in contract.test_cases:
        out += _entries(f"integration.test_cases.{case.name}", case)
    return out
