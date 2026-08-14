"""focus 的結構閘門:純函式,不做檔案 I/O。

只回答「應答的形狀對不對、錨點指不指得到東西」。語意結局 —— Expectation 落空
—— 不在這裡,它走 ValidationReport,那樣 run 目錄與產物才會留下來給人看。
"""

from __future__ import annotations

from loop_apidoc.agentcli.identity import extraction_identities
from loop_apidoc.extraction.evidence import ExtractionEvidenceReference
from loop_apidoc.focus.models import FocusDirective, FocusPackage, FocusResponse


def focus_violations(
    focus: FocusPackage | None,
    inventory: dict,
    endpoints: list[tuple[str, dict]],
) -> list[str]:
    if focus is None:
        return []
    out = _correspondence_violations(focus)
    identities = extraction_identities(inventory, endpoints)
    by_id = {directive.id: directive for directive in focus.directives}
    for response in focus.responses:
        directive = by_id.get(response.id)
        if directive is None:
            continue  # 已由 _correspondence_violations 報過
        out += _response_violations(directive, response, identities)
    return out


def focus_evidence_references(
    focus: FocusPackage | None,
) -> list[tuple[str, ExtractionEvidenceReference]]:
    """把錨點證據交給既有的 exact-evidence 驗證器 —— 一條驗證路徑,不另開。"""
    if focus is None:
        return []
    return [
        (f"focus-response.json[{response.id}].anchors[{index}]", reference)
        for response in focus.responses
        for index, anchor in enumerate(response.anchors)
        for reference in anchor.evidence
    ]


def falsified_expectations(focus: FocusPackage | None) -> list[str]:
    """回報哪些 Expectation Directive 落空 —— 純預告,不是違規。

    `verify-extraction` 用它讓人在跑完整 assemble 之前就知道要不要回頭補來源。
    它**不得**影響 exit code:落空的斷言該留下 run 目錄與產物,那是 validation
    的結局,不是輸入閘的。
    """
    if focus is None:
        return []
    unmet = {
        response.id for response in focus.responses
        if response.outcome == "not_found"
    }
    return [
        directive.id for directive in focus.directives
        if directive.kind == "expectation" and directive.id in unmet
    ]


def _correspondence_violations(focus: FocusPackage) -> list[str]:
    declared = {directive.id for directive in focus.directives}
    answered = {response.id for response in focus.responses}
    out = [
        f"focus-response.json: directive {missing!r} 沒有應答"
        "(每條 directive 都必須恰好答一次)"
        for missing in sorted(declared - answered)
    ]
    out += [
        f"focus-response.json: 應答 {extra!r} 不對應 focus.json 裡的任何 directive"
        for extra in sorted(answered - declared)
    ]
    return out


def _response_violations(
    directive: FocusDirective,
    response: FocusResponse,
    identities: set[str],
) -> list[str]:
    if response.outcome == "not_found":
        return [
            f"focus-response.json[{directive.id}]: not_found 不得附帶錨點"
        ] if response.anchors else []

    if not response.anchors:
        return [
            f"focus-response.json[{directive.id}]: satisfied 必須至少帶一個錨點"
        ]

    out: list[str] = []
    for anchor in response.anchors:
        if anchor.type != directive.anchor_type:
            out.append(
                f"focus-response.json[{directive.id}]: intent {directive.intent} "
                f"要的是 {directive.anchor_type} 錨點,卻收到 {anchor.type}"
            )
            continue
        if anchor.type == "operation" and anchor.value not in identities:
            out.append(
                f"focus-response.json[{directive.id}]: 錨點 {anchor.value!r} "
                "不對應任何已擷取的端點身份"
                "(有 path 用 `METHOD /path`;webhook 用 `METHOD (webhook) <summary>`)"
            )
    return out
