"""落空的擷取重點指令 → 驗證問題。

刻意放在 validate 而不是輸入閘:斷言落空時,人要判斷的是「來源真的沒有,還是
查得不夠」,而那需要 run 目錄、產物與應答一起留在手上。輸入閘會在建立 run 目錄
之前就中止,只留下一行訊息 —— 對這個判斷毫無幫助。

severity 只從 `kind` 讀。想要不阻斷的結局,把 directive 改寫成 Coverage,
而不是加一個覆寫旗標。
"""

from __future__ import annotations

from loop_apidoc.focus.models import FocusDirective, FocusPackage
from loop_apidoc.source_facts.models import ErrorCodeFact
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_SEVERITY = {
    "expectation": Severity.ERROR,
    "coverage": Severity.WARNING,
}


def check_focus_outcomes(
    focus: FocusPackage | None,
    error_code_floor: dict[str, list[ErrorCodeFact]] | None = None,
) -> list[Issue]:
    if focus is None:
        return []
    unmet = {
        response.id: response for response in focus.responses
        if response.outcome == "not_found"
    }
    issues = [
        _issue(directive, unmet[directive.id].searched_sources)
        for directive in focus.directives if directive.id in unmet
    ]
    return issues + _shortfall_issues(focus, error_code_floor or {})


def omitted_error_codes(
    focus: FocusPackage | None,
    floor: dict[str, list[ErrorCodeFact]] | None,
) -> list[tuple[FocusDirective, list[str]]]:
    """每個窮盡型指令漏報的錯誤碼(依碼排序);沒有漏報的指令不列入。

    公開的原因是 `verify-extraction` 的預告與 `assemble` 的驗證問題必須算出同一
    件事。兩邊各寫一份就會漂移,而預告說「你漏了三個」、驗證說「你漏了五個」
    比沒有預告更糟。
    """
    if focus is None or not floor:
        return []
    answered = {response.id: response for response in focus.responses}
    shortfalls: list[tuple[FocusDirective, list[str]]] = []
    for directive in focus.directives:
        if directive.intent != "collect_error_codes":
            continue
        response = answered.get(directive.id)
        # not_found 已經有 FOCUS_UNMET 這個結局,不該再被短少連坐一次。
        if response is None or response.outcome != "satisfied":
            continue
        # 不分大小寫:來源寫 `E1001`、答案寫 `e1001` 是同一個碼。對一個確實被
        # 回報的碼開罰單,比漏判一個沒回報的碼貴得多。
        reported = {anchor.value.strip().casefold() for anchor in response.anchors}
        omitted = sorted(
            code for code in floor if code.casefold() not in reported
        )
        if omitted:
            shortfalls.append((directive, omitted))
    return shortfalls


def _shortfall_issues(
    focus: FocusPackage,
    floor: dict[str, list[ErrorCodeFact]],
) -> list[Issue]:
    """報得比記載錯誤碼下界少的窮盡型指令。

    下界一律全域,不受 directive 文字範圍限制:`text` 導引 agent 的注意力,但閘門
    是確定性的、讀不懂散文,而 `collect_error_codes` 的字面意思就是「這家供應商的
    錯誤碼,全部」。範圍窄的需求該寫成逐條指名的 Expectation Directive。
    """
    return [
        _shortfall_issue(directive, omitted, floor)
        for directive, omitted in omitted_error_codes(focus, floor)
    ]


def _shortfall_issue(
    directive: FocusDirective,
    omitted: list[str],
    floor: dict[str, list[ErrorCodeFact]],
) -> Issue:
    cited = "、".join(f"{code}({_locations(floor[code])})" for code in omitted)
    sources = "、".join(sorted({
        fact.relative_path for code in omitted for fact in floor[code]
    }))
    return Issue(
        code=IssueCode.FOCUS_INCOMPLETE,
        severity=_SEVERITY[directive.kind],
        location=f"focus directive {directive.id}",
        evidence=(
            f"「{directive.text}」的答案少於來源記載的錯誤碼,"
            f"未回報:{cited}"
        ),
        suggested_fix=_shortfall_fix(directive),
        target_file="focus-response.json",
        field_path=f"/responses/{directive.id}",
        requery_scope=sources,
    )


def _locations(facts: list[ErrorCodeFact]) -> str:
    return "、".join(f"{fact.relative_path}:{fact.line}" for fact in facts)


def _shortfall_fix(directive: FocusDirective) -> str:
    scope = (
        "這是 coverage directive,短少不阻斷發布。"
        if directive.kind == "coverage" else
        "你斷言來源記載了它們,而來源確實記載了,是擷取沒收齊。"
    )
    return (
        f"{scope}回到上列位置把漏掉的碼補進 inventory.errors[],"
        "並為每個碼各給一個帶精確證據的 error_code 錨點。"
        "下界只是底線:回報比它多的碼仍然通過,但每個碼都必須是真的且有引用,"
        "所以灌水只會失敗得更早。"
    )


def _issue(directive: FocusDirective, searched: list[str]) -> Issue:
    sources = "、".join(searched) if searched else "(未列出任何來源)"
    return Issue(
        code=IssueCode.FOCUS_UNMET,
        severity=_SEVERITY[directive.kind],
        location=f"focus directive {directive.id}",
        evidence=(
            f"「{directive.text}」在下列來源中查無記載:{sources}"
        ),
        suggested_fix=_fix(directive),
        target_file="focus-response.json",
        field_path=f"/responses/{directive.id}",
        requery_scope=sources,
    )


def _fix(directive: FocusDirective) -> str:
    if directive.kind == "expectation":
        return (
            "你斷言來源記載了它,但擷取沒找到。重讀上列來源確認是否漏看;"
            "若供應商確實未記載,該補的是來源,不是把它改寫成別的答案 —— "
            "要讓這條不阻斷,請把它改成 coverage directive,那是承認它可能不存在。"
        )
    return (
        "這是 coverage directive,查無記載本身就是完整答案,不阻斷發布。"
        "若你認為它應該存在,改寫成 expectation directive。"
    )
