"""語意完整性閘門對某份來源沒有作用時,把那件事說出來。

`source_facts` 只掃結構良好的 Markdown。HTML 來源與被壓平成單行純文字的快照掃出
零筆事實,閘門於是無事可判、靜默通過 —— 產出的 run 目錄與一份真的被逐條比對過的
run 完全無法區分。這個範圍限制是刻意的取捨(見 ADR 0007),缺的不是解析能力,是
執行時的可見性。

嚴重度恆為 warning:純散文、本來就沒有參數表的合法來源也會落在零事實這一類,
把它擋下來等於把「量不到」誤判成「錯」。

純函式,由 `validate_outputs` 聚合。投影由呼叫端(`assemble`)一處算好傳入,
validate 不認識來源事實的內部結構,也不重掃來源 —— 同一份來源在一次 run 內被掃
兩次可能得到不同結果,那正是本檢查要消滅的自相矛盾。
"""

from __future__ import annotations

from pydantic import BaseModel

from loop_apidoc.agentcli.identity import endpoint_identity
from loop_apidoc.manifest.models import Manifest, SourceFormat
from loop_apidoc.source_facts.models import FactIndex
from loop_apidoc.validate.models import Issue, IssueCode, Severity

#: 機器可讀的規格來源不歸這道閘門管:它的內容由 OpenAPI 解析路徑逐欄位吃進來,
#: 「掃不出來源事實」對它不代表任何失能。
_MACHINE_READABLE = (SourceFormat.OPENAPI_JSON, SourceFormat.OPENAPI_YAML)


class FactCoverage(BaseModel):
    """一份來源的事實涵蓋:掃出幾筆、其中幾筆對得上 extraction 的端點識別。

    刻意窄:validate 只需要這兩個數字就能分辨零事實與零匹配,把 `FactIndex`
    整包遞進來反而讓 validate 認識了它不該認識的結構。
    """

    facts: int
    matched: int


def build_fact_coverage(
    manifest: Manifest,
    facts: FactIndex,
    identities: set[str],
) -> dict[str, FactCoverage]:
    """以 manifest source 識別碼為鍵的事實涵蓋投影。

    `identities` 是 extraction 宣告過的跨檔身份鍵(`agentcli/identity.py`),
    端點識別因此與 cross-file 不變式、focus 錨點解析用的是同一個定義。
    """
    scanned = {source.relative_path: source for source in facts.sources}
    coverage: dict[str, FactCoverage] = {}
    for source in manifest.readable_local_sources():
        if source.source_format in _MACHINE_READABLE:
            continue
        endpoints = getattr(scanned.get(source.relative_path), "endpoints", [])
        matched = sum(
            1 for fact in endpoints
            if endpoint_identity({"method": fact.method, "path": fact.path})
            in identities
        )
        coverage[source.relative_path] = FactCoverage(
            facts=len(endpoints), matched=matched)
    return coverage


def unscanned_sources(
    coverage: dict[str, FactCoverage] | None,
) -> list[tuple[str, FactCoverage]]:
    """閘門對之無作用的來源(依識別碼排序);有匹配的來源不列入。

    公開的原因與 `omitted_error_codes` 相同:`verify-extraction` 的預告與
    `assemble` 的驗證警告必須算出同一件事,兩邊各寫一份就會漂移。
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
            "這份來源掃出 0 筆來源事實,語意完整性閘門對它完全沒有作用;"
            "報告乾淨不代表它被逐條比對過"
        )
        fix = (
            "改走保留表格結構的前處理路徑(HTML 快照用 normalize-html-snapshot,"
            "PDF/Word 用 preprocess),不要重讀來源填 JSON —— 壓平成單行的內容"
            "沒有可機械判讀的結構,重讀多少次都掃不出事實。"
            "若這份來源本來就是純散文、沒有參數表,這筆警告即為預期。"
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
        requery_scope=source,
    )
