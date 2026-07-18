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
        """以 (METHOD, path) 索引;同一 identity 出現多次時只保留**交集**。

        來源常把同一端點寫兩次:總覽索引頁與細節頁,或 v1(已棄用)與 v2。
        挑「最豐富的那一筆」會反過來要求擷取去滿足它本來就該忽略的那一節——
        索引表看起來豐富,正是因為它根本不是參數表。歧義時 fail open,
        對一道 fail-closed 閘門而言才是對的偏誤。
        """
        merged: dict[tuple[str, str], EndpointFact] = {}
        for ep in self.all_endpoints():
            key = (ep.method, ep.path)
            current = merged.get(key)
            merged[key] = ep if current is None else _intersect(current, ep)
        return merged


def _intersect(left: EndpointFact, right: EndpointFact) -> EndpointFact:
    shared = [name for name in left.parameter_names if name in right.parameter_names]
    return left.model_copy(update={
        "parameter_names": shared,
        "example_blocks": min(left.example_blocks, right.example_blocks),
    })
