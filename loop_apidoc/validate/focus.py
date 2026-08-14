"""落空的擷取重點指令 → 驗證問題。

刻意放在 validate 而不是輸入閘:斷言落空時,人要判斷的是「來源真的沒有,還是
查得不夠」,而那需要 run 目錄、產物與應答一起留在手上。輸入閘會在建立 run 目錄
之前就中止,只留下一行訊息 —— 對這個判斷毫無幫助。

severity 只從 `kind` 讀。想要不阻斷的結局,把 directive 改寫成 Coverage,
而不是加一個覆寫旗標。
"""

from __future__ import annotations

from loop_apidoc.focus.models import FocusDirective, FocusPackage
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_SEVERITY = {
    "expectation": Severity.ERROR,
    "coverage": Severity.WARNING,
}


def check_focus_outcomes(focus: FocusPackage | None) -> list[Issue]:
    if focus is None:
        return []
    unmet = {
        response.id: response for response in focus.responses
        if response.outcome == "not_found"
    }
    return [
        _issue(directive, unmet[directive.id].searched_sources)
        for directive in focus.directives if directive.id in unmet
    ]


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
