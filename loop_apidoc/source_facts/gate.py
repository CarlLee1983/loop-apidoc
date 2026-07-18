"""把來源事實與擷取 JSON 對照,產出可讀的違規訊息。

只在 (METHOD, path) 能對上來源事實時判定——對不上就不判,因為那代表
掃描器沒有機械證據,而沒有證據時保持沉默比誤擋更重要。

反過來說,一旦對上了就 fail closed:來源白紙黑字列了參數表,擷取卻交回
空清單,這是靜默遺漏,不是「來源沒寫」。要主張來源沒寫,必須在
`missing` 裡具名說明——那是有據可查的缺口,不是消失。
"""

from __future__ import annotations

from typing import Any

from loop_apidoc.source_facts.models import EndpointFact, FactIndex

_NAME_KEYS = ("name", "field", "parameter")
_CONTAINER_KEYS = ("schema", "properties", "fields", "payload")


def source_fact_violations(
    index: FactIndex,
    endpoints: list[tuple[str, dict]],
    inventory: dict | None = None,
) -> list[str]:
    """回傳所有「來源證實存在、擷取卻缺席」的違規訊息。"""
    facts = index.by_identity()
    if not facts:
        return []

    inventory = inventory or {}
    schemas = _schema_fields(inventory)
    # 錯誤目錄是共用的:文件把錯誤表在每個端點重複一次,擷取卻(正確地)
    # 只收在 inventory.errors[]。看不到那裡就會逐個端點誤擋。
    catalog = _extracted_names(inventory.get("errors") or [], in_container=True)
    violations: list[str] = []
    for filename, endpoint in endpoints:
        path = endpoint.get("path")
        method = endpoint.get("method")
        if not path or not isinstance(method, str):
            continue
        fact = facts.get((method.upper(), path))
        if fact is None:
            continue
        violations += _judge(filename, endpoint, fact, schemas, catalog)
    return violations


def _schema_fields(inventory: dict) -> dict[str, dict]:
    """以名稱索引 inventory 的共用 schema,供 schema_ref 解析。"""
    return {
        schema["name"]: schema
        for schema in inventory.get("schemas") or []
        if isinstance(schema, dict) and isinstance(schema.get("name"), str)
    }


def _judge(
    filename: str,
    endpoint: dict,
    fact: EndpointFact,
    schemas: dict[str, dict],
    catalog: set[str],
) -> list[str]:
    violations: list[str] = []
    missing = _unaccounted_names(endpoint, fact, schemas, catalog)
    if missing:
        violations.append(
            f"{filename}: the source section {_where(fact)} documents "
            f"{len(fact.parameter_names)} field(s) in a parameter table, but the "
            f"extraction never mentions {', '.join(repr(n) for n in missing)}. "
            "Re-read that section and extract them, or record a source-grounded "
            "gap naming each field in `missing`."
        )
    if fact.example_blocks and not endpoint.get("examples"):
        violations.append(
            f"{filename}: the source section {_where(fact)} contains "
            f"{fact.example_blocks} example block(s), but `examples` is empty. "
            "Extract the example, or record why it cannot be used in `missing`."
        )
    return violations


def _where(fact: EndpointFact) -> str:
    heading = f" > {fact.heading}" if fact.heading else ""
    return f"{fact.relative_path}{heading} (line {fact.line})"


def _unaccounted_names(
    endpoint: dict, fact: EndpointFact, schemas: dict[str, dict], catalog: set[str]
) -> list[str]:
    if not fact.parameter_names:
        return []
    known = _extracted_names(endpoint) | _referenced_names(endpoint, schemas) | catalog
    declared = " ".join(str(item) for item in endpoint.get("missing") or []).lower()
    return [
        name for name in fact.parameter_names if not _accounted(name, known, declared)
    ]


def _accounted(name: str, known: set[str], declared: str) -> bool:
    """點號路徑以葉節點名比對:來源寫 `user.id`,擷取寫成巢狀的 `id`,是同一件事。"""
    candidates = {name.lower()}
    if "." in name:
        candidates.add(name.rsplit(".", 1)[-1].lower())
    return any(c in known or c in declared for c in candidates)


def _referenced_names(endpoint: dict, schemas: dict[str, dict]) -> set[str]:
    """跟著 `schema_ref` 走進 inventory 的共用 schema。

    共用 schema 是刻意的去重複,不是遺漏;不解析它,凡是把 body 抽成共用型別的
    正確擷取都會被誤擋。`seen` 擋住 schema 互相引用造成的無限遞迴。
    """
    names: set[str] = set()
    seen: set[str] = set()
    pending = _collect_refs(endpoint)
    while pending:
        ref = pending.pop()
        if ref in seen:
            continue
        seen.add(ref)
        schema = schemas.get(ref)
        if schema is None:
            continue
        names |= _extracted_names(schema, in_container=True)
        pending |= _collect_refs(schema) - seen
    return names


def _collect_refs(node: Any) -> set[str]:
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
                refs |= _collect_refs(value)
    elif isinstance(node, list):
        for item in node:
            refs |= _collect_refs(item)
    return refs


def _extracted_names(node: Any, *, in_container: bool = False) -> set[str]:
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
            names |= _extracted_names(value, in_container=key in _CONTAINER_KEYS)
    elif isinstance(node, list):
        for item in node:
            names |= _extracted_names(item, in_container=in_container)
    return names
