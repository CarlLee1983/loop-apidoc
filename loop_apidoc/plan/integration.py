from __future__ import annotations

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.classify import classify_item
from loop_apidoc.plan.models import (
    Callback,
    ContractMissing,
    ContractTestCase,
    CryptoScheme,
    CryptoStep,
    CryptoVerify,
    FieldCondition,
    IntegrationContract,
    KeySource,
    NormalizationPlan,
)

_QID = "integration"
_APATH = "integration.json"


def _cite(item: dict, manifest: Manifest) -> dict:
    """Return {status, citations} kwargs for a _Cited entry from its `source`."""
    status, citation = classify_item(
        item.get("source"), query_id=_QID, answer_path=_APATH, manifest=manifest
    )
    return {"status": status, "citations": [citation]}


def _crypto(item: dict, manifest: Manifest) -> CryptoScheme:
    ks = item.get("key_source") or None
    vf = item.get("verify") or None
    steps = [
        CryptoStep(
            step=s.get("step"), desc=s.get("desc"), fields=list(s.get("fields") or [])
        )
        for s in (item.get("payload_assembly") or [])
        if isinstance(s, dict)
    ]
    return CryptoScheme(
        **_cite(item, manifest),
        name=item.get("name"),
        purpose=item.get("purpose"),
        algorithm=item.get("algorithm"),
        mode=item.get("mode"),
        padding=item.get("padding"),
        encoding=item.get("encoding"),
        key_source=KeySource(**{k: ks.get(k) for k in ("key", "iv", "note")})
        if isinstance(ks, dict)
        else None,
        payload_assembly=steps,
        verify=CryptoVerify(**{k: vf.get(k) for k in ("field", "method", "desc")})
        if isinstance(vf, dict)
        else None,
    )


def _callback(item: dict, manifest: Manifest) -> Callback:
    return Callback(
        **_cite(item, manifest),
        name=item.get("name"),
        trigger=item.get("trigger"),
        transport=item.get("transport"),
        payload_ref=item.get("payload_ref"),
        verification=item.get("verification"),
        expected_response=item.get("expected_response"),
    )


def _condition(item: dict, manifest: Manifest) -> FieldCondition:
    return FieldCondition(
        **_cite(item, manifest),
        scope=item.get("scope"),
        rule=item.get("rule"),
        when=item.get("when"),
        then_required=list(item.get("then_required") or []),
    )


def _test_case(item: dict, manifest: Manifest) -> ContractTestCase:
    return ContractTestCase(
        **_cite(item, manifest),
        name=item.get("name"),
        operation_ref=item.get("operation_ref"),
        request=item.get("request"),
        response=item.get("response"),
    )


def build_integration_contract(
    integration_json: dict | None,
    plan: NormalizationPlan,
    manifest: Manifest,
) -> IntegrationContract:
    """Convert agent-written integration.json into a cited IntegrationContract.

    Pure. Reuses already-structured plan data where the contract only references
    it (errors/environments are rendered at generate time, not re-extracted).
    A None/empty payload means the sources stated no integration mechanics —
    that is a recorded absence, never a failure.
    """
    data = integration_json or {}

    def _list(key: str) -> list[dict]:
        return [i for i in (data.get(key) or []) if isinstance(i, dict)]

    return IntegrationContract(
        version=str(data.get("version") or "1.0"),
        crypto=[_crypto(i, manifest) for i in _list("crypto")],
        callbacks=[_callback(i, manifest) for i in _list("callbacks")],
        field_conditions=[_condition(i, manifest) for i in _list("field_conditions")],
        test_cases=[_test_case(i, manifest) for i in _list("test_cases")],
        missing=[
            ContractMissing(area=str(m.get("area")), detail=str(m.get("detail")))
            for m in _list("missing")
        ],
    )
