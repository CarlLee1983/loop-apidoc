"""來源事實涵蓋投影 —— `assemble` 與 `verify-extraction` 共用的那一份。

住在 `agentcli/` 而不是 `validate/`:算這份投影要同時認識 `FactIndex` 的內部結構
與端點的跨檔身份鍵,而那兩樣都是擷取閘的詞彙。`validate/` 只收算好的窄投影,
維持它不認識來源事實的立場,相依方向也就不會反過來。
"""

from __future__ import annotations

from loop_apidoc.agentcli.identity import endpoint_identity
from loop_apidoc.manifest.models import Manifest, SourceFormat
from loop_apidoc.source_facts.models import FactIndex
from loop_apidoc.validate.fact_coverage import FactCoverage

#: 機器可讀的規格來源不歸這道閘門管:它的內容由 OpenAPI 解析路徑逐欄位吃進來,
#: 「掃不出來源事實」對它不代表任何失能。
_MACHINE_READABLE = (SourceFormat.OPENAPI_JSON, SourceFormat.OPENAPI_YAML)


def build_fact_coverage(
    manifest: Manifest,
    facts: FactIndex,
    identities: set[str],
) -> dict[str, FactCoverage]:
    """以 manifest source 識別碼為鍵的端點事實涵蓋投影。

    `identities` 是 extraction 宣告過的跨檔身份鍵(`agentcli/identity.py`),
    端點識別因此與 cross-file 不變式、focus 錨點解析用的是同一個定義。
    """
    scanned = {source.relative_path: source for source in facts.sources}
    coverage: dict[str, FactCoverage] = {}
    for source in manifest.readable_local_sources():
        if source.source_format in _MACHINE_READABLE:
            continue
        entry = scanned.get(source.relative_path)
        endpoints = entry.endpoints if entry is not None else []
        matched = sum(
            1 for fact in endpoints
            if endpoint_identity({"method": fact.method, "path": fact.path})
            in identities
        )
        coverage[source.relative_path] = FactCoverage(
            facts=len(endpoints),
            matched=matched,
            unclosed_fence_line=(
                entry.unclosed_fence_line if entry is not None else None
            ),
        )
    return coverage
