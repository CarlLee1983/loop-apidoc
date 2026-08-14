"""擷取 JSON 裡「欄位名在哪裡」的共用解析。

`source_facts` 用它判斷來源列出的欄位有沒有被擷取;`focus` 用它解析 field 錨點。
兩份各自實作會漂移,而漂移的症狀是一個閘門說欄位在、另一個說不在。
"""

from __future__ import annotations

from typing import Any

_NAME_KEYS = ("name", "field", "parameter")
_CONTAINER_KEYS = ("schema", "properties", "fields", "payload")


def schema_index(inventory: dict) -> dict[str, dict]:
    """以名稱索引 inventory 的共用 schema,供 schema_ref 解析。"""
    return {
        schema["name"]: schema
        for schema in inventory.get("schemas") or []
        if isinstance(schema, dict) and isinstance(schema.get("name"), str)
    }


def referenced_names(endpoint: dict, schemas: dict[str, dict]) -> set[str]:
    """跟著 `schema_ref` 走進 inventory 的共用 schema。

    共用 schema 是刻意的去重複,不是遺漏;不解析它,凡是把 body 抽成共用型別的
    正確擷取都會被誤擋。`seen` 擋住 schema 互相引用造成的無限遞迴。
    """
    names: set[str] = set()
    seen: set[str] = set()
    pending = collect_refs(endpoint)
    while pending:
        ref = pending.pop()
        if ref in seen:
            continue
        seen.add(ref)
        schema = schemas.get(ref)
        if schema is None:
            continue
        names |= extracted_names(schema, in_container=True)
        pending |= collect_refs(schema) - seen
    return names


def collect_refs(node: Any) -> set[str]:
    """`schema_ref`,以及自由格式的 `schema` 直接寫共用 schema 名的情況。

    `ResponseEntry.schema` 依設計是自由格式(見 input_schema.py),所以在那裡
    寫一個共用 schema 名是合法擷取,不是遺漏。
    """
    refs: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("schema_ref", "schema") and isinstance(value, str):
                refs.add(value)
            else:
                refs |= collect_refs(value)
    elif isinstance(node, list):
        for item in node:
            refs |= collect_refs(item)
    return refs


def extracted_names(node: Any, *, in_container: bool = False) -> set[str]:
    """蒐集擷取 JSON 中處於「結構位置」的欄位名。

    刻意不撈描述文字裡出現的字串:欄位名被寫進某段說明,不等於它被擷取成
    一個欄位——那正是本閘門要抓的遺漏。
    """
    names: set[str] = set()
    if isinstance(node, dict):
        if in_container:
            names |= {str(key).lower() for key in node}
        for key, value in node.items():
            if key in _NAME_KEYS and isinstance(value, str):
                names.add(value.lower())
            names |= extracted_names(value, in_container=key in _CONTAINER_KEYS)
    elif isinstance(node, list):
        for item in node:
            names |= extracted_names(item, in_container=in_container)
    return names
