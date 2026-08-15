"""focus 的結構閘門:純函式,不做檔案 I/O。

只回答「應答的形狀對不對、錨點指不指得到東西」。語意結局 —— Expectation 落空
—— 不在這裡,它走 ValidationReport,那樣 run 目錄與產物才會留下來給人看。
"""

from __future__ import annotations

from loop_apidoc.agentcli.identity import extraction_identities
from loop_apidoc.extraction.evidence import ExtractionEvidenceReference
from loop_apidoc.focus.codes import extraction_error_codes
from loop_apidoc.focus.fields import extraction_field_names
from loop_apidoc.focus.models import FocusDirective, FocusPackage, FocusResponse
from loop_apidoc.manifest.models import Manifest


def focus_violations(
    focus: FocusPackage | None,
    inventory: dict,
    endpoints: list[tuple[str, dict]],
    manifest: Manifest,
) -> list[str]:
    if focus is None:
        return []
    out = _correspondence_violations(focus)
    identities = extraction_identities(inventory, endpoints)
    field_names = extraction_field_names(inventory, endpoints)
    codes = extraction_error_codes(inventory)
    readable = manifest.readable_source_identities()
    known = manifest.all_source_identities()
    by_id = {directive.id: directive for directive in focus.directives}
    for response in focus.responses:
        directive = by_id.get(response.id)
        if directive is None:
            continue  # 已由 _correspondence_violations 報過
        out += _response_violations(
            directive, response, identities, field_names, codes,
            readable, known)
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


def _searched_source_violations(
    directive: FocusDirective,
    response: FocusResponse,
    readable: set[str],
    known: set[str],
) -> list[str]:
    """`not_found` 宣稱的是「它不在任何一份來源裡」,列一份證明不了那件事。

    Coverage 與 Expectation 同標準:`kind` 降低的是結局的 severity,不是達成那個
    結局所需的答案品質。讀不到的來源(unsupported / unreadable / duplicate /
    ignored)不要求列出 —— agent 無法查它沒辦法讀的東西 —— 但列了也不算錯,
    manifest 覆蓋率本來就會另外報告它們。
    """
    searched = set(response.searched_sources)
    out: list[str] = []
    missing = sorted(readable - searched)
    if missing:
        out.append(
            f"focus-response.json[{directive.id}]: not_found 必須交代每一份可讀來源,"
            f"未列出:{'、'.join(missing)}"
            "(宣稱「來源都沒寫」就必須查過全部,查一份證明不了)"
        )
    unknown = sorted(searched - known)
    if unknown:
        out.append(
            f"focus-response.json[{directive.id}]: searched_sources 列出 manifest "
            f"沒有的來源:{'、'.join(unknown)}"
        )
    return out


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
    field_names: set[str],
    codes: set[str],
    readable: set[str],
    known: set[str],
) -> list[str]:
    if response.outcome == "not_found":
        out = [
            f"focus-response.json[{directive.id}]: not_found 不得附帶錨點"
        ] if response.anchors else []
        return out + _searched_source_violations(
            directive, response, readable, known)

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
        elif anchor.type == "error_code" and anchor.value.strip() not in codes:
            out.append(
                f"focus-response.json[{directive.id}]: 錨點 {anchor.value!r} "
                "不在 inventory.errors[] 的錯誤碼目錄裡"
                "(錯誤碼只認型別化的 errors[],不認範例或 enum 裡的數字)"
            )
        elif anchor.type == "field" and not _field_resolves(
                anchor.value, field_names):
            out.append(
                f"focus-response.json[{directive.id}]: 錨點 {anchor.value!r} "
                "不對應任何已擷取的欄位"
                "(可寫 `Schema.field` 或裸欄位名;解析會沿 schema_ref 走進共用 schema)"
            )
    return out


def _field_resolves(value: str, field_names: set[str]) -> bool:
    """以葉節點名比對,與 source_facts 的欄位覆蓋判準相同。

    來源寫 `user.id`、擷取寫成巢狀的 `id`,是同一件事;兩個閘門對「這個欄位有沒有
    被擷取」必須給出同一個答案,否則 agent 會收到互相矛盾的指示。
    """
    candidates = {value.strip().lower()}
    if "." in value:
        candidates.add(value.rsplit(".", 1)[-1].strip().lower())
    return bool(candidates & field_names)
