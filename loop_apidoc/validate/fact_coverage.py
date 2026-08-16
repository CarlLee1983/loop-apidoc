"""語意完整性閘門對某份來源沒有作用時,把那件事說出來。

`source_facts` 只從結構良好的 Markdown 讀出端點事實,而且只認得 `METHOD /path`
形式的端點宣告。掃不出端點事實的來源有兩種:一種真的沒有可機械判讀的結構(HTML
來源、被壓平成單行的快照),一種結構完好但端點寫成掃描器不認得的形式(例如註解裡
的完整 URL)。兩種的下場相同——閘門無事可判、靜默通過,產出的 run 目錄與一份真的
被逐條比對過的 run 完全無法區分。這個範圍限制是刻意的取捨(見 ADR 0007),缺的不是
解析能力,是執行時的可見性。

嚴重度恆為 warning:純散文、本來就沒有參數表的合法來源也會落在零事實這一類,
把它擋下來等於把「量不到」誤判成「錯」。

純函式,由 `validate_outputs` 聚合。投影由呼叫端(`assemble`)一處算好傳入,
validate 不認識來源事實的內部結構,也不重掃來源 —— 同一份來源在一次 run 內被掃
兩次可能得到不同結果,那正是本檢查要消滅的自相矛盾。
"""

from __future__ import annotations

from pydantic import BaseModel

from loop_apidoc.validate.models import Issue, IssueCode, Severity


class FactCoverage(BaseModel):
    """一份來源的端點事實涵蓋:掃出幾筆、其中幾筆對得上 extraction 的端點識別。

    刻意窄:validate 只需要這兩個數字就能分辨零事實與零匹配,把 `FactIndex`
    整包遞進來反而讓 validate 認識了它不該認識的結構。錯誤碼事實不計入——
    閘門判的是端點,錯誤碼下界走的是另一條(只在 focus 指令要求時才綁)。
    """

    facts: int
    matched: int


def unscanned_sources(
    coverage: dict[str, FactCoverage] | None,
) -> list[tuple[str, FactCoverage]]:
    """閘門對之無作用的來源(依識別碼排序);有匹配的來源不列入。

    公開的原因與 `omitted_error_codes` 相同:`verify-extraction` 的預告與
    `assemble` 的驗證警告必須算出同一件事,兩邊各寫一份就會漂移。

    「有匹配 ＝ 被判過」是近似:閘門實際走 `FactIndex.by_identity()` 的跨來源
    交集,某筆事實可能對得上 extraction 卻在交集裡被削掉。近似的方向是安全的
    ——它只會少報,不會對一份確實被逐條比對過的來源開罰單。
    """
    if not coverage:
        return []
    return [
        (source, entry) for source, entry in sorted(coverage.items())
        if entry.matched == 0
    ]


def check_fact_coverage(
    coverage: dict[str, FactCoverage] | None = None,
) -> list[Issue]:
    """未傳投影 ＝ 這項未評估(`validate_run_dir` 從 run 目錄重建報告時算不出來)。"""
    return [_issue(source, entry) for source, entry in unscanned_sources(coverage)]


def _issue(source: str, entry: FactCoverage) -> Issue:
    if entry.facts == 0:
        evidence = (
            "這份來源掃出 0 筆端點事實,語意完整性閘門對它完全沒有作用;"
            "報告乾淨不代表它被逐條比對過"
        )
        fix = (
            "先打開來源看它屬於哪一種:(a) 內容被壓平成單行、沒有表格與標題結構"
            "(HTML 傾印、未轉換的 PDF/Word)——改走保留結構的前處理路徑"
            "(normalize-html-snapshot / preprocess)後重新擷取,重讀來源沒有用;"
            "(b) 結構完好,但端點不是寫成 `METHOD /path`(例如註解裡的完整 URL)"
            "——掃描器認不得這種寫法,請回報給維護者,擷取本身可能是對的;"
            "(c) 本來就是純散文、沒有參數表的合法來源——這筆警告即為預期。"
        )
    else:
        evidence = (
            f"這份來源掃出 {entry.facts} 筆端點事實,但沒有任何一筆能以端點識別"
            "(METHOD /path)對上 extraction,語意完整性閘門一次都沒判"
        )
        fix = (
            "檢查 extraction 是否漏掉這份來源記載的端點,或 method/path 是否與"
            "來源寫法不一致;補齊後閘門才會真的比對這份來源。"
        )
    return Issue(
        code=IssueCode.SOURCE_FACTS_UNSCANNED,
        severity=Severity.WARNING,
        location=source,
        evidence=evidence,
        suggested_fix=fix,
        # 刻意不填 requery_scope:那個欄位的意義是「有界的重讀提示」,而這筆
        # issue 的重點正是重讀解決不了問題。要定位是哪一份來源,看 location。
    )
