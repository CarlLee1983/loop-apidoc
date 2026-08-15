"""field 錨點能指到哪些名字 —— 純函式。

沿用 `source_facts` 的解析器而不是另寫一份:兩個閘門對「這個欄位有沒有被擷取」
必須給出同一個答案,否則 agent 會收到互相矛盾的指示。
"""

from __future__ import annotations

from loop_apidoc.extraction.field_names import (
    extracted_names,
    referenced_names,
    schema_index,
)


def extraction_field_names(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> set[str]:
    """擷取中處於結構位置的欄位名,含沿 schema_ref 走到的共用 schema。

    描述文字裡出現的名字不算 —— 欄位名被寫進某段說明,不等於它被擷取成一個
    欄位,而那正是 focus 想確認的事。
    """
    schemas = schema_index(inventory)
    names: set[str] = set()
    for schema in schemas.values():
        names |= extracted_names(schema, in_container=True)
    for _, endpoint in endpoints:
        names |= extracted_names(endpoint)
        names |= referenced_names(endpoint, schemas)
    return names
