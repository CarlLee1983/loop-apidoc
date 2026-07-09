"""把多筆同源 issue 收斂成一次修完的根因(issue #4)。

一個根因(例如 integration.json 的 source 格式不合)會在 issues[] 裡展開成數十筆
各自獨立的 entry,evidence 全是同一句話。orchestrator 依 location 逐一重讀 scope
的話,會把 O(1) 的修法變成 O(n) 的 requery。

純加法:issues[] 一字不動,ValidationReport.ok 不受影響。純函式,不做檔案 I/O。
"""

from __future__ import annotations

from loop_apidoc.validate.models import Issue, IssueCode, RootCause

# 只填有實證的 code。查不到就沿用組內共同的 suggested_fix —— 憑空編一句
# 「一次修完」的動作,反而會把 correction loop 導向錯的地方。
_FIX_ONCE: dict[IssueCode, str] = {
    IssueCode.SOURCE_UNVERIFIED: (
        "統一改寫該檔所有 source 為 '<relative_path> p.<N>' 或 "
        "'<relative_path>#<anchor>' 格式,一次修完;不需逐筆重讀來源"
    ),
}


def derive_root_causes(issues: list[Issue]) -> list[RootCause]:
    """依 (code, severity, target_file) 分組。

    只在 `target_file` 非 None 且組內 ≥2 筆時產出根因:
    - `target_file` 為 None → 沒有可靠的一次修完目標,硬分組只會製造假的根因。
    - 單筆 → 逐筆 issue 已經夠精確,不需要收斂。
    - `severity` 進分組鍵 → 混合嚴重度的組無法給出單一 fix_once。

    分組順序依首次出現順序,組內 location 依原始順序 —— 決定性輸出。
    """
    groups: dict[tuple[IssueCode, str, str], list[Issue]] = {}
    for issue in issues:
        if issue.target_file is None:
            continue
        key = (issue.code, issue.severity.value, issue.target_file)
        groups.setdefault(key, []).append(issue)

    return [
        RootCause(
            code=code,
            severity=members[0].severity,
            target_file=target_file,
            fix_once=_FIX_ONCE.get(code, members[0].suggested_fix),
            affected_locations=[m.location for m in members],
        )
        for (code, _severity, target_file), members in groups.items()
        if len(members) > 1
    ]
