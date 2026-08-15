"""記載錯誤碼下界:掃描器只認來源自己攤出來的錯誤碼表格。

錯誤碼幾乎都寫在文末的全域附錄,底下沒有端點宣告,所以這些事實掛在來源檔本身
而不是端點上。與參數表同一套紀律:認得出結構才判斷,認不出就沉默——寧可漏掉
一張真的錯誤碼表(等同今天的行為),也不要生出一個來源沒寫的碼。
"""

from __future__ import annotations

from loop_apidoc.source_facts.markdown import scan_markdown

GLOBAL_ERROR_TABLE = """# 支付 API

## POST /payments

| Name | Type | Required |
| --- | --- | --- |
| amount | integer | Y |

## 錯誤碼

| 錯誤碼 | 說明 |
| --- | --- |
| 1001 | 餘額不足 |
| 1002 | 商店代號無效 |
| 40001 | 簽章驗證失敗 |
"""


def test_a_global_error_code_table_yields_documented_codes() -> None:
    """附錄裡的錯誤碼表不隸屬任何端點,仍然要被認出來。"""
    facts = scan_markdown("manual.md", GLOBAL_ERROR_TABLE)

    assert [fact.code for fact in facts.error_codes] == ["1001", "1002", "40001"]


def test_each_documented_code_carries_its_line_and_table_position() -> None:
    """漏碼的罰單要能告訴 operator 去哪一行讀它,所以出處必須是事實的一部分。"""
    facts = scan_markdown("manual.md", GLOBAL_ERROR_TABLE)
    first = facts.error_codes[0]

    assert first.line == GLOBAL_ERROR_TABLE.splitlines().index("| 1001 | 餘額不足 |") + 1
    assert first.column_name == "錯誤碼"
    assert first.row_index == 0


def test_a_source_without_an_error_code_table_stays_silent() -> None:
    """沒有可辨識的結構就不下判斷——下界是「不存在」,不是「零」。"""
    text = """## POST /payments

| Name | Type | Required |
| --- | --- | --- |
| amount | integer | Y |
"""

    assert scan_markdown("manual.md", text).error_codes == []


def test_a_flattened_source_stays_silent() -> None:
    """壓平的 HTML 沒有表格結構,掃描器對它一如既往地沉默。"""
    flattened = (
        "錯誤碼 說明 1001 餘額不足 1002 商店代號無效 40001 簽章驗證失敗 "
        "訂單金額 1500 建立時間 20240101"
    )

    assert scan_markdown("dump.md", flattened).error_codes == []


def test_recognising_an_error_code_table_leaves_parameter_facts_untouched() -> None:
    """新的辨識器不得改變既有的參數表判定,否則會動到所有 run 的結局。"""
    facts = scan_markdown("manual.md", GLOBAL_ERROR_TABLE)

    assert [ep.parameter_names for ep in facts.endpoints] == [["amount"]]


def test_a_single_column_table_is_not_an_error_code_table() -> None:
    """只有碼、沒有意義欄的表多半是別的東西,不拿它當下界。"""
    text = """## 錯誤碼

| 錯誤碼 |
| --- |
| 1001 |
| 1002 |
"""

    assert scan_markdown("manual.md", text).error_codes == []


def test_one_malformed_data_row_discards_the_whole_table() -> None:
    """整表作廢而不是跳過那一列。

    跳列會安靜地把下界調低,而下界調低正是這道檢查要防的事;整表沉默只是回到
    今天的行為,是安全的那一邊。
    """
    text = """## 錯誤碼

| 錯誤碼 | 說明 |
| --- | --- |
| 1001 | 餘額不足 |
| 視情況而定 | 其他錯誤 |
| 1002 | 簽章錯誤 |
"""

    assert scan_markdown("manual.md", text).error_codes == []


def test_each_fact_carries_the_source_it_was_read_from() -> None:
    """罰單要指出哪一份來源的哪一行,所以出處跟著事實走。"""
    facts = scan_markdown("errors.md", GLOBAL_ERROR_TABLE)

    assert {fact.relative_path for fact in facts.error_codes} == {"errors.md"}
