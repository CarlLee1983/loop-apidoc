from __future__ import annotations

from loop_apidoc.manifest.models import Manifest
from loop_apidoc.plan.classify import classify_item
from loop_apidoc.plan.models import (
    AmountDirection,
    Callback,
    ContractMissing,
    ContractTestCase,
    CryptoScheme,
    CryptoStep,
    CryptoVerify,
    FieldCondition,
    IdempotencyRule,
    IntegrationContract,
    KeySource,
    LineCurrencyPolicy,
    NormalizationPlan,
    TransportPolicy,
)

_QID = "integration"
_APATH = "integration.json"


def _cite(item: dict, manifest: Manifest) -> dict:
    """Return {status, citations} kwargs for a _Cited entry from its `source`."""
    status, citation = classify_item(
        item.get("source"), query_id=_QID, answer_path=_APATH, manifest=manifest,
        evidence=item.get("evidence") or (),
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


def _transport(item: dict, manifest: Manifest) -> TransportPolicy:
    return TransportPolicy(
        **_cite(item, manifest),
        name=item.get("name"),
        protocol=item.get("protocol"),
        methods=list(item.get("methods") or []),
        content_type=item.get("content_type"),
        content_type_note=item.get("content_type_note"),
        http_status=item.get("http_status"),
        timezone=item.get("timezone"),
        time_format=item.get("time_format"),
        operation_refs=list(item.get("operation_refs") or []),
    )


def _amount_direction(item: dict, manifest: Manifest) -> AmountDirection:
    return AmountDirection(
        **_cite(item, manifest),
        operation_ref=item.get("operation_ref"),
        balance_effect=item.get("balance_effect"),
        amount_sign=item.get("amount_sign"),
        precision=item.get("precision"),
    )


def _idempotency(item: dict, manifest: Manifest) -> IdempotencyRule:
    return IdempotencyRule(
        **_cite(item, manifest),
        operation_refs=list(item.get("operation_refs") or []),
        code=item.get("code"),
        meaning=item.get("meaning"),
        action=item.get("action"),
    )


def _line_currency_policy(item: dict, manifest: Manifest) -> LineCurrencyPolicy:
    return LineCurrencyPolicy(
        **_cite(item, manifest),
        scope=item.get("scope"),
        policy=item.get("policy"),
        currency_binding=item.get("currency_binding"),
        operation_refs=list(item.get("operation_refs") or []),
        note=item.get("note"),
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
        transport=[_transport(i, manifest) for i in _list("transport")],
        amount_direction=[
            _amount_direction(i, manifest) for i in _list("amount_direction")
        ],
        idempotency=[_idempotency(i, manifest) for i in _list("idempotency")],
        line_currency_policy=[
            _line_currency_policy(i, manifest)
            for i in _list("line_currency_policy")
        ],
        crypto=[_crypto(i, manifest) for i in _list("crypto")],
        callbacks=[_callback(i, manifest) for i in _list("callbacks")],
        field_conditions=[_condition(i, manifest) for i in _list("field_conditions")],
        test_cases=[_test_case(i, manifest) for i in _list("test_cases")],
        missing=[
            ContractMissing(area=str(m.get("area")), detail=str(m.get("detail")))
            for m in _list("missing")
        ],
    )
