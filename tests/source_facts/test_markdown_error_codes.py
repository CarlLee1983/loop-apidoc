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


# --- 表頭詞彙 -------------------------------------------------------------

def _table(header: str, *rows: str) -> str:
    body = "\n".join(f"| {row} |" for row in rows)
    return f"## 附錄\n\n| {header} |\n| --- | --- |\n{body}\n"


def test_the_unambiguous_header_vocabulary_is_recognised() -> None:
    for header in ("錯誤碼 | 說明", "錯誤代碼 | 說明", "回應碼 | 說明",
                   "Error Code | Description", "ErrCode | Message"):
        facts = scan_markdown("manual.md", _table(header, "1001 | 餘額不足"))
        assert [f.code for f in facts.error_codes] == ["1001"], header


def test_an_ambiguous_header_needs_an_error_section_to_corroborate_it() -> None:
    """`代碼` / `code` / `status code` 太泛用,單看表頭無法斷定。

    一張 `| 代碼 | 幣別 |` 的幣別表(USD、TWD)完全符合碼的形狀。認錯一張表會生出
    假下界,而假事實會擋掉正確的擷取——所以模糊表頭要有章節標題佐證才算數。
    """
    currency = """## 幣別代碼

| 代碼 | 幣別 |
| --- | --- |
| USD | 美元 |
| TWD | 新臺幣 |
"""
    assert scan_markdown("manual.md", currency).error_codes == []

    errors = """## 錯誤代碼一覽

| 代碼 | 說明 |
| --- | --- |
| USD | 佔位 |
"""
    assert [f.code for f in scan_markdown("manual.md", errors).error_codes] == ["USD"]


def test_an_english_error_section_corroborates_an_ambiguous_header() -> None:
    text = """## Error Codes

| Code | Meaning |
| --- | --- |
| INVALID_REQUEST | malformed body |
"""

    facts = scan_markdown("manual.md", text)

    assert [f.code for f in facts.error_codes] == ["INVALID_REQUEST"]


# --- 碼的形狀 -------------------------------------------------------------

def test_the_supported_code_shapes_are_recognised() -> None:
    facts = scan_markdown("manual.md", _table(
        "錯誤碼 | 說明",
        "1001 | 餘額不足", "E1001 | 餘額不足", "INVALID_REQUEST | 格式錯誤",
        "ERR-001 | 逾時", "40001 | 簽章錯誤"))

    assert [f.code for f in facts.error_codes] == [
        "1001", "E1001", "INVALID_REQUEST", "ERR-001", "40001"]


def test_the_parameter_identifier_pattern_is_not_reused_for_codes() -> None:
    """`_IDENTIFIER` 禁止開頭是數字,而 `1001` 正是最常見的供應商錯誤碼形狀。"""
    from loop_apidoc.source_facts.markdown import _IDENTIFIER

    assert not _IDENTIFIER.match("1001")
    assert [f.code for f in scan_markdown(
        "manual.md", _table("錯誤碼 | 說明", "1001 | 餘額不足")).error_codes] == ["1001"]


def test_an_over_long_cell_is_not_a_code() -> None:
    """碼有長度上限;整段句子塞在碼欄時,那張表不是錯誤碼表。"""
    facts = scan_markdown("manual.md", _table(
        "錯誤碼 | 說明", f"{'9' * 40} | 這不是碼"))

    assert facts.error_codes == []


# --- 表格形狀 -------------------------------------------------------------

def test_a_group_label_row_is_skipped_without_discarding_the_table() -> None:
    """分組標題列(其餘欄位全空)不是資料列,不該讓整張表作廢。"""
    text = """## 錯誤碼

| 錯誤碼 | 說明 |
| --- | --- |
| 支付類 | |
| 1001 | 餘額不足 |
| 1002 | 簽章錯誤 |
"""

    facts = scan_markdown("manual.md", text)

    assert [f.code for f in facts.error_codes] == ["1001", "1002"]


def test_a_table_inside_a_fenced_code_sample_yields_no_floor() -> None:
    """圍籬裡的東西是範例,不是來源的主張。"""
    text = """## 錯誤碼

```markdown
| 錯誤碼 | 說明 |
| --- | --- |
| 1001 | 餘額不足 |
```
"""

    assert scan_markdown("manual.md", text).error_codes == []


def test_the_constant_table_rejection_does_not_swallow_an_error_code_table() -> None:
    """`| X | Value |` 的常數表判定只管參數表,不得連錯誤碼表一起丟掉。"""
    text = """## 錯誤碼

| 錯誤碼 | Value |
| --- | --- |
| 1001 | 餘額不足 |
"""

    assert [f.code for f in scan_markdown("manual.md", text).error_codes] == ["1001"]


def test_an_error_code_table_inside_an_endpoint_section_leaves_parameters_alone(
) -> None:
    """兩種表共存於同一個端點小節時,各自認各自的,互不污染。"""
    text = """## POST /payments

| Name | Type | Required |
| --- | --- | --- |
| amount | integer | Y |

### 錯誤碼

| 錯誤碼 | 說明 |
| --- | --- |
| 1001 | 餘額不足 |
"""

    facts = scan_markdown("manual.md", text)

    assert facts.endpoints[0].parameter_names == ["amount"]
    assert [f.code for f in facts.error_codes] == ["1001"]


# --- 誤判與漏判的邊界 -----------------------------------------------------

def test_a_row_whose_meaning_cell_is_blank_is_still_a_documented_code() -> None:
    """`| 1001 | |` 是說明留白的真資料列,不是分組標題。

    把它當標題跳過會安靜地把下界調低——正好是這道檢查存在的理由。
    """
    text = """## 錯誤碼

| 錯誤碼 | 說明 |
| --- | --- |
| 1001 | |
| 1002 | 簽章錯誤 |
"""

    facts = scan_markdown("manual.md", text)

    assert [f.code for f in facts.error_codes] == ["1001", "1002"]


def test_an_ambiguous_header_matches_only_as_a_whole_cell() -> None:
    """「國家代碼」「幣別代碼」都包含「代碼」;放寬成包含會整批認錯。"""
    text = """## 錯誤處理與代碼附錄

| 國家代碼 | 國家 |
| --- | --- |
| TW | 臺灣 |
| US | 美國 |
"""

    assert scan_markdown("manual.md", text).error_codes == []


def test_an_english_substring_does_not_promote_a_column() -> None:
    """`"code" in "encoded"` —— 包含比對在英文上更容易誤中。"""
    text = """## Error Handling

| Encoded Value | Note |
| --- | --- |
| A1 | x |
"""

    assert scan_markdown("manual.md", text).error_codes == []


def test_an_exact_header_wins_over_a_column_that_merely_contains_it() -> None:
    """碼欄是第二欄;照「第一個命中」會挑到分類欄,整張表跟著作廢。"""
    text = """## 附錄

| 錯誤碼分類 | 錯誤碼 | 說明 |
| --- | --- | --- |
| 支付 | 1001 | 餘額不足 |
| 退款 | 2001 | 訂單不存在 |
"""

    facts = scan_markdown("manual.md", text)

    assert [f.code for f in facts.error_codes] == ["1001", "2001"]


def test_an_enclosing_heading_corroborates_a_grouped_error_table() -> None:
    """`## 錯誤碼` → `### 支付類` → 表格是主流寫法,只看最近一層會全部漏掉。"""
    text = """## 錯誤碼

### 支付類

| 代碼 | 說明 |
| --- | --- |
| 1001 | 餘額不足 |

### 退款類

| 代碼 | 說明 |
| --- | --- |
| 2001 | 訂單不存在 |
"""

    facts = scan_markdown("manual.md", text)

    assert [f.code for f in facts.error_codes] == ["1001", "2001"]


def test_a_sibling_section_does_not_inherit_the_error_heading() -> None:
    """離開錯誤章節之後,同層的下一節不該還被它佐證。"""
    text = """## 錯誤碼

| 錯誤碼 | 說明 |
| --- | --- |
| 1001 | 餘額不足 |

## 幣別

| 代碼 | 幣別 |
| --- | --- |
| TWD | 新臺幣 |
"""

    facts = scan_markdown("manual.md", text)

    assert [f.code for f in facts.error_codes] == ["1001"]
