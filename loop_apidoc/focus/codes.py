"""error_code 錨點能指到哪些碼 —— 純函式。

刻意只讀型別化的 `inventory.errors[]`:那是錯誤碼流進生成 `ErrorCode` 列舉的唯一
路徑,也是唯一經過輸入邊界定型的地方。`examples[]` 裡出現的碼與 `schemas[].enums`
是不透明資料,拿它們當錨點依據等於承認一個不會進契約的碼。
"""

from __future__ import annotations


def extraction_error_codes(inventory: dict) -> set[str]:
    return {
        entry["code"].strip()
        for entry in (inventory.get("errors") or [])
        if isinstance(entry, dict) and isinstance(entry.get("code"), str)
    }
