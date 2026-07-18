"""拒絕「之後再擷取」這類佔位文字。

模型在放棄時傾向交回一句語法完整、語意為零的話——例如
「detailed parameters require a further source-grounded extraction」。
那不是來源缺口,是擷取沒做完;放它過去,run 就會以 passed 收場而
產物是空的。真正的缺口必須具體指出來源沒寫什麼,那種句子不會命中這裡。
"""

from __future__ import annotations

import re
from typing import Any

# 兩層判定。第一層是明確指涉「擷取這件工作」的說法,出現在值的任何位置都算——
# 真實 API 描述不會提到自己的擷取流程。
_EXTRACTION_PHRASES = (
    "further extraction",
    "further source-grounded extraction",
    "source-grounded extraction",
    "pending extraction",
    "needs extraction",
    "not yet extracted",
    "需進一步擷取",
    "需進一步取得",
    "待擷取",
    "尚待擷取",
    "後續補齊",
)

# 第二層是泛用佔位字。"requires further authentication"、"amount to be determined
# at capture" 都是合法的 API 描述,所以這些只有在「整個欄位就只有這句」時才算
# 延後——那才代表這個欄位什麼都沒回答。
_PLACEHOLDER_PHRASES = (
    "tbd",
    "to be determined",
    "to be extracted",
    "to be confirmed",
    "待補",
    "待確認",
)

_TRIM = " \t.。,,;;::!!??()()[]【】\"'`*_-—–"


def _compile(phrase: str) -> re.Pattern[str]:
    """英文用詞界比對;CJK 沒有詞界可言,維持子字串。"""
    body = re.escape(phrase)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])" if phrase.isascii() else body)


_EXTRACTION_PATTERNS = tuple((p, _compile(p)) for p in _EXTRACTION_PHRASES)


def deferral_violations(endpoints: list[tuple[str, dict]]) -> list[str]:
    """回傳所有含佔位式延後文字的欄位位置。"""
    violations: list[str] = []
    for filename, endpoint in endpoints:
        for field_path, phrase in _offenders(endpoint):
            violations.append(
                f"{filename}: `{field_path}` defers the work instead of answering "
                f"it ({phrase!r}). The cited source scope must be re-read and the "
                "field filled, or a concrete source-grounded gap recorded in "
                "`missing` naming what the source does not state."
            )
    return violations


def _offenders(node: Any, prefix: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found += _offenders(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found += _offenders(item, f"{prefix}[{index}]")
    elif isinstance(node, str):
        lowered = node.lower()
        # `missing` 本來就是用來陳述缺口的地方,不在此判定。
        if not prefix.startswith("missing"):
            match = _match(lowered)
            if match:
                found.append((prefix, match))
    return found


def _match(lowered: str) -> str | None:
    for phrase, pattern in _EXTRACTION_PATTERNS:
        if pattern.search(lowered):
            return phrase
    stripped = lowered.strip(_TRIM)
    return stripped if stripped in _PLACEHOLDER_PHRASES else None
