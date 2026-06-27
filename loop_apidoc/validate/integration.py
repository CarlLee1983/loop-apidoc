from __future__ import annotations

from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.plan.models import IntegrationContract, NormalizationPlan
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_SIGNAL_WORDS = ("加密", "簽章", "AES", "HashKey", "HashIV", "SHA256")


def _issue(code: IssueCode, location: str, evidence: str, fix: str, *, fixable: bool = False) -> Issue:
    return Issue(
        code=code,
        severity=Severity.ERROR,
        location=location,
        evidence=evidence,
        suggested_fix=fix,
        auto_fixable=fixable,
    )


def _uncited(contract: IntegrationContract) -> list[Issue]:
    issues: list[Issue] = []
    groups = (
        ("crypto", contract.crypto),
        ("callbacks", contract.callbacks),
        ("field_conditions", contract.field_conditions),
        ("test_cases", contract.test_cases),
    )
    for section, entries in groups:
        for idx, entry in enumerate(entries):
            if not entry.citations:
                label = getattr(entry, "name", None) or str(idx)
                issues.append(
                    _issue(
                        IssueCode.UNSUPPORTED_ASSERTION,
                        f"integration.{section}.{label}",
                        "契約條目無任何來源引用",
                        "為此條目補上來源引用,或在無來源時移除",
                    )
                )
    return issues


def _refs(contract: IntegrationContract, openapi: dict) -> list[Issue]:
    issues: list[Issue] = []
    paths = openapi.get("paths") or {}
    schemas = ((openapi.get("components") or {}).get("schemas")) or {}
    for cb in contract.callbacks:
        ref = cb.payload_ref
        if ref and ref.startswith("schemas.") and ref.split("schemas.", 1)[1] not in schemas:
            issues.append(
                _issue(
                    IssueCode.OUTPUT_MISMATCH,
                    f"integration.callbacks.{cb.name}",
                    f"payload_ref 指向不存在的 schema:{ref}",
                    "更正 payload_ref 或補上對應 schema",
                    fixable=True,
                )
            )
    for case in contract.test_cases:
        ref = case.operation_ref
        if ref and ref.startswith("paths."):
            body = ref.split("paths.", 1)[1]
            path, _, method = body.rpartition(".")
            if path not in paths or method not in (paths.get(path) or {}):
                issues.append(
                    _issue(
                        IssueCode.OUTPUT_MISMATCH,
                        f"integration.test_cases.{case.name}",
                        f"operation_ref 指向不存在的 operation:{ref}",
                        "更正 operation_ref 至既有 paths.{{path}}.{{method}}",
                        fixable=True,
                    )
                )
    return issues


def _signal_gap(plan: NormalizationPlan, contract: IntegrationContract | None) -> list[Issue]:
    text = " ".join(
        [e.detail or "" for e in plan.operational]
        + [s.details or "" for s in plan.security_schemes]
    )
    hit = next((w for w in _SIGNAL_WORDS if w in text), None)
    has_crypto = bool(contract and contract.crypto)
    if hit and not has_crypto:
        return [
            _issue(
                IssueCode.REQUIRED_INFO_MISSING,
                "integration.crypto",
                f"來源出現「{hit}」訊號詞,但契約未抽到任何加解密/簽章機制",
                "重讀相關來源段落,補上 crypto 細節後重跑 assemble",
            )
        ]
    return []


def check_integration(plan: NormalizationPlan, result: GenerateResult) -> list[Issue]:
    """Validate the integration contract: no-speculation + ref resolution + signal-word gap."""
    contract = plan.integration
    issues: list[Issue] = []
    if contract is not None:
        issues += _uncited(contract)
        issues += _refs(contract, result.openapi)
    issues += _signal_gap(plan, contract)
    return issues
