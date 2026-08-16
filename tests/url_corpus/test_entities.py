"""錯誤碼實體要有語境,不能只看形狀(#86)。

這些實體只餵相關頁面評分,不進 provenance、不進來源事實,所以壞掉的方式是噪音而非
錯誤主張:兩個頁面因為都提到「2024」而被判為相關,真正相關的頁面就被擠下去。
精確度才是這裡值得要的東西——漏掉一個碼只損失一個弱訊號。

量測:benchmark 語料裡四到五位數字命中 761 次,只有兩成落在任何一個把它稱為「碼」
的字附近;被丟掉最多的值是 2020、2021、2024、2023 這些年份與 1000 這種整數金額。
"""
from __future__ import annotations

from loop_apidoc.url_corpus import extract_page_metadata


def _entities(body: str) -> list[str]:
    return extract_page_metadata(
        "https://docs.example.com/page",
        f"<html><body><main><h1>T</h1><p>{body}</p></main></body></html>",
    ).entities


def test_a_number_introduced_as_an_error_code_is_kept():
    assert _entities("Error 9005 means the request expired.") == ["error:9005"]


def test_a_chinese_error_code_table_row_is_kept():
    assert _entities("錯誤碼 1104 商店代號錯誤") == ["error:1104"]


def test_a_year_in_prose_is_not_an_error_code():
    """`Updated Dec 29, 2023` —— 舊規則會把它登記成一個錯誤碼實體。"""
    assert _entities("AWC API Documents Updated Dec 29, 2023 More actions") == []


def test_an_amount_is_not_an_error_code():
    assert _entities("單筆交易上限為 50000 元,超過請分批送出。") == []


def test_a_year_shaped_value_is_never_registered():
    """「錯誤碼表更新於 2024」讀起來就像在介紹一個碼,語境分不出來。

    因此年份一律不登記。真的把碼編成 2024 的供應商損失一個弱訊號,比整份語料的
    每一頁都共享「今年」這個實體便宜。
    """
    assert _entities("錯誤碼表更新於 2024,請重新下載。") == []
    assert _entities("error code 2024 is reserved.") == []


def test_a_page_that_merely_mentions_errors_does_not_turn_every_number_into_a_code():
    body = (
        "This page explains error handling. "
        + "Rate limit is 6000 requests per hour. " * 3
    )

    assert _entities(body) == []


def test_action_entities_are_unaffected():
    assert _entities("Use Action 19 for the transfer.") == ["action:19"]
