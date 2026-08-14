"""端點的跨檔身份鍵 —— 一個定義,多處使用。

`cross_file` 用它比對 inventory 與端點檔;`focus` 用它解析 operation 錨點。
兩份各自實作會漂移,而漂移的症狀是「閘門說找到了、另一個閘門說沒有」。
"""

from __future__ import annotations

from typing import Any

from loop_apidoc.agentcli.extraction import _expand_methods


def entries(payload: dict | None, section: str) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    return [e for e in (payload.get(section) or []) if isinstance(e, dict)]


def normalized_summary(value: Any) -> str | None:
    """空白正規化:長敘述跨行複製容易差一個空白,除此之外要求逐字相符。"""
    if not isinstance(value, str):
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def endpoint_identity(entry: dict) -> str | None:
    """端點的跨檔身份鍵;method 大小寫不敏感。

    有 path 用 `(method, path)`。webhook/callback 的 path 為 null,身份改用
    `summary` —— generate/naming.py 的 webhook_items 早就用 summary 命名 webhook,
    所以它本來就是 webhook 的身份。

    兩者皆無時回 None:此時真正的問題是「缺 summary」,由 source_guard 以 exit 2
    報告。在這裡把鍵塌成 `POST ?` 再報「重複」會給出錯誤訊息。
    """
    method = entry.get("method")
    method = method.upper() if isinstance(method, str) else "?"
    path = entry.get("path")
    if isinstance(path, str):
        return f"{method} {path}"
    summary = normalized_summary(entry.get("summary"))
    if summary is None:
        return None
    return f"{method} (webhook) {summary}"


def extraction_identities(
    inventory: dict, endpoints: list[tuple[str, dict]]
) -> set[str]:
    """每個 inventory 條目與端點檔宣告過的身份鍵。

    聯集而非交集:兩邊不一致本身是 `cross_file` 要報的違規,不該在這裡被
    重複報成「錨點指不到」。
    """
    declared = _expand_methods(entries(inventory, "endpoints"))
    declared += [
        expanded for _, endpoint in endpoints
        for expanded in _expand_methods([endpoint])
    ]
    return {
        key for key in (endpoint_identity(entry) for entry in declared)
        if key is not None
    }
