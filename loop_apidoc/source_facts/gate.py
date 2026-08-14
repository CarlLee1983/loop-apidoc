"""把來源事實與擷取 JSON 對照,產出可讀的違規訊息。

只在 (METHOD, path) 能對上來源事實時判定——對不上就不判,因為那代表
掃描器沒有機械證據,而沒有證據時保持沉默比誤擋更重要。

反過來說,一旦對上了就 fail closed:來源白紙黑字列了參數表,擷取卻交回
空清單,這是靜默遺漏,不是「來源沒寫」。要主張來源沒寫,必須在
`missing` 裡具名說明——那是有據可查的缺口,不是消失。
"""

from __future__ import annotations


from loop_apidoc.extraction.field_names import (
    extracted_names as _extracted_names,
    referenced_names as _referenced_names,
    schema_index as _schema_fields,
)
from loop_apidoc.source_facts.models import EndpointFact, FactIndex



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
