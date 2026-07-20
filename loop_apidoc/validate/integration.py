from __future__ import annotations

import re

from loop_apidoc.generate.examples import (
    _is_runnable_crypto,
    _request_signing_schemes,
)
from loop_apidoc.generate.models import GenerateResult
from loop_apidoc.generate.naming import component_key
from loop_apidoc.plan.models import IntegrationContract, NormalizationPlan, PlanItemStatus
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_SIGNAL_WORDS = ("加密", "簽章", "AES", "HashKey", "HashIV", "SHA256")


def _issue(code: IssueCode, location: str, evidence: str, fix: str, *,
           fixable: bool = False, target_file: str | None = None,
           field_path: str | None = None,
           requery_scope: str | None = None) -> Issue:
    return Issue(
        code=code,
        severity=Severity.ERROR,
        location=location,
        evidence=evidence,
        suggested_fix=fix,
        auto_fixable=fixable,
        target_file=target_file,
        field_path=field_path,
        requery_scope=requery_scope,
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
            label = getattr(entry, "name", None) or str(idx)
            location = f"integration.{section}.{label}"
            if not entry.citations:
                issues.append(
                    _issue(
                        IssueCode.UNSUPPORTED_ASSERTION,
                        location,
                        "契約條目無任何來源引用",
                        "為此條目補上來源引用,或在無來源時移除",
                    )
                )
            elif entry.status is PlanItemStatus.CONFLICTING:
                issues.append(
                    _issue(
                        IssueCode.SOURCE_CONFLICT,
                        location,
                        "契約條目的來源彼此衝突",
                        "揭露衝突並由來源澄清",
                    )
                )
            elif entry.status is PlanItemStatus.UNVERIFIED:
                issues.append(
                    _issue(
                        IssueCode.SOURCE_UNVERIFIED,
                        location,
                        "契約條目僅有 unverified 來源,缺 supported 依據",
                        "確認來源以取得 supported 引用",
                    )
                )
    return issues


def _refs(contract: IntegrationContract, openapi: dict) -> list[Issue]:
    issues: list[Issue] = []
    paths = openapi.get("paths") or {}
    schemas = ((openapi.get("components") or {}).get("schemas")) or {}
    for cb in contract.callbacks:
        ref = cb.payload_ref
        if ref and ref.startswith("schemas."):
            ref_name = ref.split("schemas.", 1)[1]
            # payload_ref names the inventory schema; the OpenAPI component key is
            # sanitized (spaces/CJK → key-safe). Resolve via the same sanitization
            # the generator uses so a spaced name like "Backend Notify Body" matches
            # its key "Backend_Notify_Body" instead of false-flagging a mismatch.
            sanitized = component_key(ref_name, 0, prefix="schema")
            if ref_name not in schemas and sanitized not in schemas:
                issues.append(
                    _issue(
                        IssueCode.OUTPUT_MISMATCH,
                        f"integration.callbacks.{cb.name}",
                        f"payload_ref 指向不存在的 schema:{ref}",
                        "更正 payload_ref 或補上對應 schema",
                        fixable=True,
                        target_file="integration.json",
                        field_path=f"callbacks.{cb.name}.payload_ref",
                        requery_scope=f"callbacks.{cb.name}",
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
                        "更正 operation_ref 至既有 paths.{path}.{method}",
                        fixable=True,
                        target_file="integration.json",
                        field_path=f"test_cases.{case.name}.operation_ref",
                        requery_scope=f"test_cases.{case.name}",
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
                target_file="integration.json",
                field_path="crypto",
                requery_scope=f"來源中出現「{hit}」的加解密/簽章段落",
            )
        ]
    return []


def _signature_wiring(plan: NormalizationPlan, result: GenerateResult) -> list[Issue]:
    """情境 A：可跑簽章+有目標欄位，但 ts/py 範例用到該欄位卻沒接回 → OUTPUT_MISMATCH。
    情境 B：可跑簽章但來源未指明 verify.field → REQUIRED_INFO_MISSING。curl 不檢查。"""
    issues: list[Issue] = []
    examples = result.examples or {}
    for idx, s in enumerate(_request_signing_schemes(plan)):
        if not _is_runnable_crypto(s):
            continue
        label = s.name or str(idx)
        target = s.verify.field if s.verify else None
        if not target:
            issues.append(
                _issue(
                    IssueCode.REQUIRED_INFO_MISSING,
                    f"integration.crypto.{label}",
                    "可生成可跑簽章但來源未指明簽章值的目標欄位(verify.field)",
                    "重讀來源補上 verify.field 後重跑 assemble",
                )
            )
            continue
        wired = re.compile(r"\[['\"]" + re.escape(target) + r"['\"]\]\s*=\s*sign\w*\(")
        # Only examples that actually declare `target` as a request key (body /
        # header / query all render as a quoted `"name":` entry) are candidates.
        # A bare mention of the field name elsewhere (e.g. the `# 簽章 TradeInfo`
        # helper comment every endpoint renders for every scheme) must not trip
        # the check — match the quoted key form, not raw substring presence.
        declared_key = re.compile(r"['\"]" + re.escape(target) + r"['\"]\s*:")
        for path, content in examples.items():
            if not (path.endswith("request.ts") or path.endswith("request.py")):
                continue
            if not declared_key.search(content):
                continue
            if not wired.search(content):
                issues.append(
                    _issue(
                        IssueCode.OUTPUT_MISMATCH,
                        path,
                        f"範例用到欄位「{target}」但未接回簽章值(缺 {target}=sign(...))",
                        "重新產生範例使其將 sign() 結果接回該欄位",
                        fixable=True,
                    )
                )
    return issues


def check_integration(plan: NormalizationPlan, result: GenerateResult) -> list[Issue]:
    """Validate the integration contract: no-speculation + ref resolution + signal-word gap."""
    contract = plan.integration
    issues: list[Issue] = []
    if contract is not None:
        issues += _uncited(contract)
        issues += _refs(contract, result.openapi)
    issues += _signal_gap(plan, contract)
    issues += _signature_wiring(plan, result)
    return issues
