"""機械可證的來源事實。

這裡的每個欄位都必須能從來源位元組直接讀出——不做任何語意推論。
它存在的唯一目的,是讓「來源明明寫了、擷取卻空著」這件事變成可判定的,
而不是靠人眼或模型自陳。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EndpointFact(BaseModel):
    """來源文件中一個端點小節被機械掃描出的事實。"""

    relative_path: str
    heading: str | None
    method: str
    path: str
    line: int
    #: 小節內所有「參數表」第一欄的值,依出現順序、去重後保留。
    parameter_names: list[str] = Field(default_factory=list)
    #: 小節內圍籬程式碼區塊(```)的數量,作為「來源有範例」的證據。
    example_blocks: int = 0


class SourceFacts(BaseModel):
    """單一來源檔的事實索引。"""

    relative_path: str
    endpoints: list[EndpointFact] = Field(default_factory=list)


class FactIndex(BaseModel):
    """整份 manifest 掃描後的事實集合。"""

    sources: list[SourceFacts] = Field(default_factory=list)

    def all_endpoints(self) -> list[EndpointFact]:
        return [ep for source in self.sources for ep in source.endpoints]

    def by_identity(self) -> dict[tuple[str, str], EndpointFact]:
        """以 (METHOD, path) 索引。

        同一 identity 在多個來源重複出現時,保留事實最豐富的那一筆:
        來源常把同一端點在總覽頁與細節頁各寫一次,細節頁才是完整的。
        """
        best: dict[tuple[str, str], EndpointFact] = {}
        for ep in self.all_endpoints():
            key = (ep.method, ep.path)
            current = best.get(key)
            if current is None or _richness(ep) > _richness(current):
                best[key] = ep
        return best


def _richness(fact: EndpointFact) -> tuple[int, int]:
    return (len(fact.parameter_names), fact.example_blocks)
