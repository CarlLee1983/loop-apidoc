"""擷取答案不得以「需進一步擷取」搪塞已被引用的來源範圍。"""

from __future__ import annotations

from loop_apidoc.source_facts.deferral import deferral_violations


def test_generic_deferral_text_is_rejected() -> None:
    endpoints = [(
        "ep1.json",
        {
            "method": "GET", "path": "/games",
            "summary": (
                "detailed parameters and response schema require a further "
                "source-grounded extraction"
            ),
        },
    )]
    violations = deferral_violations(endpoints)
    assert len(violations) == 1
    assert "ep1.json" in violations[0]
    assert "summary" in violations[0]


def test_traditional_chinese_deferral_text_is_rejected() -> None:
    endpoints = [("ep1.json", {"summary": "詳細參數需進一步擷取來源後補齊"})]
    assert deferral_violations(endpoints)


def test_a_concrete_source_grounded_gap_is_not_a_deferral() -> None:
    endpoints = [(
        "ep1.json",
        {"missing": ["The source does not state the maximum length of `username`."]},
    )]
    assert deferral_violations(endpoints) == []


def test_the_offending_field_path_is_reported() -> None:
    endpoints = [(
        "ep1.json",
        {"responses": [{"status": "200", "description": "TBD, requires further extraction"}]},
    )]
    violations = deferral_violations(endpoints)
    assert "responses[0].description" in violations[0]


def test_clean_extraction_has_no_violations() -> None:
    endpoints = [(
        "ep1.json",
        {"summary": "List available games.", "parameters": [{"name": "provider"}]},
    )]
    assert deferral_violations(endpoints) == []


def test_an_abbreviation_does_not_match_inside_an_ordinary_word() -> None:
    """`tbd` 當純子字串會誤中欄位名與一般字詞,那會擋掉正確的擷取。"""
    endpoints = [(
        "ep1.json",
        {"parameters": [{"name": "statbdata", "description": "Stat batch data."}]},
    )]
    assert deferral_violations(endpoints) == []


def test_a_standalone_abbreviation_is_still_caught() -> None:
    endpoints = [("ep1.json", {"responses": [{"description": "(TBD)"}]})]
    assert deferral_violations(endpoints)


def test_legitimate_prose_containing_the_words_is_not_a_deferral() -> None:
    """真實 API 文件會寫「requires further authentication」「amount to be extracted」;
    把這些當延後就會擋掉正確的擷取。判定必須綁在「擷取這件工作」上,而非泛用英文。"""
    legitimate = [
        {"summary": "Returns the amount to be extracted from the wallet."},
        {"responses": [{"description": "Requires further authentication via 3-D Secure."}]},
        {"summary": "The merchant must require further verification for high-risk orders."},
        {"responses": [{"description": "Settlement amount to be determined at capture."}]},
    ]
    for index, endpoint in enumerate(legitimate):
        assert deferral_violations([(f"ep{index}.json", endpoint)]) == [], endpoint


def test_a_bare_placeholder_value_is_still_a_deferral() -> None:
    """整個欄位就只有一個佔位字,那沒有回答任何事。"""
    for value in ("TBD", "(TBD)", "to be determined", "待補"):
        assert deferral_violations([("ep1.json", {"summary": value})]), value


def test_extraction_work_phrases_are_caught_anywhere_in_the_value() -> None:
    endpoints = [(
        "ep1.json",
        {"summary": "The full schema requires further extraction from the PDF."},
    )]
    assert deferral_violations(endpoints)
