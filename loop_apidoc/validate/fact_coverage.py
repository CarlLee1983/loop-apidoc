"""語意完整性閘門對某份來源沒有作用時,把那件事說出來。

`source_facts` 只從結構良好的 Markdown 讀出端點事實,而且只認得把 method 與 path
寫在同一行的宣告(`METHOD /path`,或帶標籤的 `URL … Method …`)。掃不出端點事實的
來源有兩種:一種真的沒有可機械判讀的結構(HTML 來源、被壓平成單行的快照),一種
結構完好但端點寫成掃描器不認得的形式(例如註解裡的完整 URL、method 另起一行)。兩種的下場相同——閘門無事可判、靜默通過,產出的 run 目錄與一份真的
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
    #: 掃到檔尾仍未關閉的圍籬開在第幾行(沒有就是 None)。零事實唯一一種掃描器
    #: 自己知道確切成因的情形,知道就別叫 operator 從三種可能裡猜。
    unclosed_fence_line: int | None = None


def unscanned_sources(
    coverage: dict[str, FactCoverage] | None,
) -> list[tuple[str, FactCoverage]]:
    """閘門沒有完整判過的來源(依識別碼排序)。

    兩種:一筆事實都對不上(閘門對它完全無作用),或掃描在某一行之後就停了
    (未關閉的圍籬)。後者即使前半有事實對上也必須列入——讀到一半才失效比全篇
    未讀更危險,因為閘門看起來運作正常,而報告是乾淨的。

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
        if entry.matched == 0 or entry.unclosed_fence_line is not None
    ]


def check_fact_coverage(
    coverage: dict[str, FactCoverage] | None = None,
) -> list[Issue]:
    """未傳投影 ＝ 這項未評估(`validate_run_dir` 從 run 目錄重建報告時算不出來)。"""
    return [_issue(source, entry) for source, entry in unscanned_sources(coverage)]


def _issue(source: str, entry: FactCoverage) -> Issue:
    # 成因已知時它壓過其他措辭:掃描器知道是圍籬,就不該叫 operator 去查一個
    # 並不存在的 extraction 缺陷。
    if entry.unclosed_fence_line is not None:
        scanned = (
            "掃出 0 筆端點事實" if entry.facts == 0
            else f"圍籬之前掃出 {entry.facts} 筆端點事實"
        )
        evidence = (
            f"第 {entry.unclosed_fence_line} 行開啟的圍籬直到檔尾都沒有被關閉,"
            f"該行之後的內容全部沒有被讀到({scanned});"
            "語意完整性閘門沒有完整判過這份來源"
        )
        fix = (
            f"打開來源第 {entry.unclosed_fence_line} 行,補上關閉圍籬。"
            "常見成因是關閉行帶了 info string(例如以 ```json 結尾)——依 CommonMark "
            "那不算關閉,而是又開了一個新的圍籬。修好之後重新擷取,閘門才會讀到"
            "該行以後的內容。"
        )
    elif entry.facts == 0:
        evidence = (
            "這份來源掃出 0 筆端點事實,語意完整性閘門對它完全沒有作用;"
            "報告乾淨不代表它被逐條比對過"
        )
        fix = (
            "先打開來源看它屬於哪一種:(a) 內容被壓平成單行、沒有表格與標題結構"
            "(HTML 傾印、未轉換的 PDF/Word)——改走保留結構的前處理路徑"
            "(normalize-html-snapshot / preprocess)後重新擷取,重讀來源沒有用;"
            "(b) 結構完好,但 method 與 path 不在同一行(例如只給一個完整 URL、"
            "method 另起一行或寫在別處的散文裡,或本來就是 path 為 null 的 webhook)"
            "——同一行上的 method 掃描器會讀(`METHOD /path` 與帶標籤的 "
            "`URL … Method …`,ADR 0011),但不會跨行去湊,那是 ADR 0007 拒絕的推論,"
            "所以這筆警告會長期存在,擷取本身可能完全正確;"
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
