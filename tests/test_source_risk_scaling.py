r"""前置閘的掃描成本必須隨輸入線性成長。

這條性質原本是用 CLI 的 wall clock 證明的(`assert elapsed < 5.0`)。實測那份
176 KB 輸入只要 0.13 秒,38 倍餘裕——新加一條 O(n^1.5) 的規則在這裡跑 3 秒仍會
通過,而同一條規則在 5 MiB 的真實來源上要跑幾分鐘;反方向則是 #120 記錄過的
偽陽性:機器忙的時候,時間斷言會擋下沒有缺陷的東西。

改成量「同一份形狀在 N 與 8N 的 CPU 成本比」,取三次最小值(最小值是雜訊下最
乾淨的估計)。比值抵銷機器的常數快慢,規模退化仍然抓得到:8 倍輸入的線性成本是
8 倍,O(n^1.5) 是 22.6 倍,二次是 64 倍。門檻 16 夾在線性與 O(n^1.5) 之間——
放到 24 會把 22.6 倍放過去,而那正是這個檔案宣稱要擋的東西。

門檻確實分得開歷史上的那一版:`\b[^\s@]+@[^\s@]+\.[^\s@]+\b`(#101 之前)在同一份
minified CSS 上是 0.40s → 26.6s,比值 66.5 倍;現行的十二條規則實測全落在 8.7
倍以內。下面的 control 測試把「這個門檻擋得住二次式」也變成會失敗的斷言。
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable

import pytest

from loop_apidoc.privacy import CONTACT_PII
from loop_apidoc.source_risk.inspect import _RULES

#: 線性是 8 倍,O(n^1.5) 是 22.6 倍,二次是 64 倍。
LINEAR_RATIO_LIMIT = 16.0
GROWTH_FACTOR = 8
#: 小邊低於這個成本時,量到的是時鐘解析度與雜訊,不是演算法。
MIN_MEASURABLE_SECONDS = 0.01

#: 前置閘實際被餵過的形狀:minified CSS。無界限的網域樣式在這上面是二次時間,
#: 184 KB 要 52 秒。
CSS_UNIT = ".a{color:#fff;margin:0}"
#: 近乎命中:有 `@`、後面接一長串網域標籤的形狀,但每一段都是數字,所以永遠湊不
#: 出合法的頂級網域。回溯型的樣式在這裡最容易爆掉。
NEAR_MISS_UNIT = "user@" + "12." * 200 + " "

#: #101 之前的無界限樣式,只當作量測方法的對照組,不是生產程式碼。
QUADRATIC_CONTROL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")


def _best_cpu_seconds(scan: Callable[[str], object], text: str, runs: int = 3) -> float:
    best = float("inf")
    for _ in range(runs):
        started = time.process_time()
        result = scan(text)
        if isinstance(result, Iterable) and not isinstance(result, (str, bytes)):
            list(result)  # 產生器要走完才算成本
        best = min(best, time.process_time() - started)
    return best


def _growth(
    scan: Callable[[str], object], unit: str, base_units: int, runs: int = 3
) -> tuple[float, float]:
    small = _best_cpu_seconds(scan, unit * base_units, runs=runs)
    large = _best_cpu_seconds(scan, unit * (base_units * GROWTH_FACTOR), runs=runs)
    assert small > MIN_MEASURABLE_SECONDS, (
        f"小邊只花 {small:.4f}s,低於可量測門檻,比值沒有意義"
    )
    return small, large


def _calibrated(
    scan: Callable[[str], object], unit: str
) -> tuple[int, float] | None:
    """讓小邊的成本高過雜訊的規模,連同量到的成本一起回傳;找不到就回 None。

    量測用的估計式與 `_growth` 相同(三次取最小),而且要求高過門檻兩倍才收——
    用 runs=1 校準、再用 min-of-3 量會系統性偏低,規模落在門檻附近的規則就會
    隨機地紅。最便宜的規則(`SR-CONTROL-TOKEN-TEXT` 在 230 KB 上是 0.1 ms)要餵
    幾十 MB 才量得到比值,那不值得;它們改用絕對成本上限守,見下面的測試。
    """
    base = 6_000
    while base <= 48_000:
        small = _best_cpu_seconds(scan, unit * base)
        if small > MIN_MEASURABLE_SECONDS * 2:
            return base, small
        base *= 2
    return None


def _assert_linear(label: str, small: float, large: float) -> None:
    ratio = large / small
    assert ratio < LINEAR_RATIO_LIMIT, (
        f"{label}: {GROWTH_FACTOR}x 輸入花了 {ratio:.1f}x 成本 "
        f"({small:.4f}s → {large:.4f}s);線性 {GROWTH_FACTOR}x、"
        f"O(n^1.5) {GROWTH_FACTOR ** 1.5:.1f}x、二次 {GROWTH_FACTOR ** 2}x"
    )


#: 便宜到量不出比值的規則,改守絕對上限。8.8 MB 之下線性的實測是毫秒級,二次
#: 退化是分鐘級,所以 0.5 秒同時遠離兩者——它擋的是規模,不是常數。
CHEAP_RULE_CPU_BUDGET = 0.5


@pytest.mark.parametrize(
    "rule_id,scan", [(rule[0], rule[2]) for rule in _RULES], ids=[r[0] for r in _RULES]
)
def test_every_source_risk_rule_scales_linearly(rule_id: str, scan) -> None:
    """十二條規則各自量。舊的 CLI 時間斷言是端到端的,只守 `CONTACT_PII` 會把
    其餘十一條的複雜度守衛靜靜拿掉——那不在 #128 的範圍裡。"""
    calibrated = _calibrated(scan, CSS_UNIT)
    if calibrated is None:
        # 量不出比值的規則不是「跳過」:它便宜到二次退化仍然守得住絕對上限。
        cost = _best_cpu_seconds(scan, CSS_UNIT * (48_000 * GROWTH_FACTOR))
        assert cost < CHEAP_RULE_CPU_BUDGET, (
            f"{rule_id}: 便宜規則在 8.8 MB 上花了 {cost:.3f}s CPU"
        )
        return

    base, small = calibrated
    large = _best_cpu_seconds(scan, CSS_UNIT * (base * GROWTH_FACTOR))

    _assert_linear(rule_id, small, large)


def test_contact_pii_scales_linearly_on_its_adversarial_shape() -> None:
    """近乎命中的網域是這條規則的天敵形狀,單獨再量一次。"""
    small, large = _growth(CONTACT_PII.findall, NEAR_MISS_UNIT, base_units=300)

    _assert_linear("near-miss-domain", small, large)


def test_contact_pii_still_matches_a_real_address() -> None:
    """成本測試不能靠「什麼都不比對」通過。"""
    assert CONTACT_PII.findall("寄到 support@example.com 即可") == [
        "support@example.com"
    ]
    assert CONTACT_PII.findall(CSS_UNIT * 10) == []
    assert CONTACT_PII.findall(NEAR_MISS_UNIT * 10) == []


def test_the_ratio_limit_separates_quadratic_from_linear() -> None:
    """量測方法本身要能失敗。

    對照組是 #101 之前的無界限樣式,規模縮小讓這條測試維持在一秒級;比值不隨
    規模改變,所以縮小不影響結論。
    """
    # 二次成本讓大邊本身就是秒級,所以取兩次而不是三次。
    quadratic_small, quadratic_large = _growth(
        QUADRATIC_CONTROL.findall, CSS_UNIT, base_units=200, runs=2
    )
    quadratic_ratio = quadratic_large / quadratic_small

    assert quadratic_ratio > LINEAR_RATIO_LIMIT, (
        f"對照組只成長 {quadratic_ratio:.1f}x,門檻擋不住二次式就沒有意義"
    )
