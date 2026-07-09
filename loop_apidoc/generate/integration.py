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


_SECTIONS = ("crypto", "callbacks", "field_conditions", "test_cases")

# field_conditions entries carry no name, so they are addressed by index.
_INDEXED_SECTIONS = frozenset({"field_conditions"})


def entry_target(section: str, idx: int, entry) -> str:
    """The provenance `target` for one contract entry.

    Single definition shared by the product file and provenance.json — a consumer
    can only join the two while these agree.
    """
    if section in _INDEXED_SECTIONS:
        return f"integration.{section}.{idx}"
    return f"integration.{section}.{getattr(entry, 'name', None) or idx}"


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
    # Swap internal bookkeeping (status/citations) for the two fields a consumer
    # needs to trace a rule back to its origin: the cited `source` string, and the
    # provenance.json key the full citation list is filed under.
    for section in _SECTIONS:
        cited_entries = getattr(contract, section)
        for idx, (entry, cited) in enumerate(zip(payload.get(section, []), cited_entries)):
            entry.pop("status", None)
            entry.pop("citations", None)
            entry["source"] = cited.citations[0].locator if cited.citations else None
            entry["provenance_target"] = entry_target(section, idx, cited)
    return payload


def integration_provenance_entries(
    contract: IntegrationContract,
) -> list[ProvenanceEntry]:
    """One provenance group per contract leaf (error_codes excluded — reused)."""
    out: list[ProvenanceEntry] = []
    for section in _SECTIONS:
        for idx, entry in enumerate(getattr(contract, section)):
            out += _entries(entry_target(section, idx, entry), entry)
    return out
