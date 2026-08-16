"""HTML 表格轉 Markdown 的結構保真度(#81)。

參數表是來源事實的主要來源,而來源事實會被 fail-closed 閘門當成「必須被擷取」的
證據。表格錯位一格,擷取就會被要求交出來源根本沒寫的欄位——假事實比漏掉事實貴,
因為它擋掉的是正確的擷取。

seam 是 `html_to_markdown` 這個公開純函式。
"""
from __future__ import annotations

from loop_apidoc.html_snapshot import html_to_markdown


def _rows(md: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in md.splitlines()
        if line.startswith("|") and "---" not in line
    ]


def test_colspan_keeps_the_following_columns_aligned():
    """跨欄的表頭不得把後面每一欄都往左推一格。"""
    html = (
        "<main><table>"
        "<tr><th colspan='2'>Request</th><th>Note</th></tr>"
        "<tr><td>name</td><td>string</td><td>必填</td></tr>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert rows[0] == ["Request", "Request", "Note"]
    assert rows[1] == ["name", "string", "必填"]


def test_rowspan_carries_the_cell_down_its_own_column():
    """跨列的第一欄不得讓下面每一列都少一格。"""
    html = (
        "<main><table>"
        "<tr><th>Group</th><th>Name</th><th>Type</th></tr>"
        "<tr><td rowspan='2'>cardholder</td><td>name</td><td>String</td></tr>"
        "<tr><td>email</td><td>String</td></tr>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert rows[1] == ["cardholder", "name", "String"]
    assert rows[2] == ["cardholder", "email", "String"]


def test_a_nested_table_does_not_become_rows_of_the_outer_table():
    """內層表格的列併進外層,就是把兩張表的欄位對錯位。"""
    html = (
        "<main><table>"
        "<tr><th>Name</th><th>Usage</th></tr>"
        "<tr><td>cardholder</td><td>"
        "<table><tr><th>Sub</th><th>Type</th></tr>"
        "<tr><td>phone</td><td>String</td></tr></table>"
        "</td></tr>"
        "</table></main>"
    )

    md = html_to_markdown(html)
    outer, _, nested = md.partition("\n\n| Sub | Type |")

    assert nested, "內層表格必須是自己的區塊,而不是外層表格的續列"
    assert "phone" not in outer
    assert "| Name | Usage |" in outer


def test_a_nested_table_is_still_rendered_as_its_own_table():
    """不併進外層,不等於丟掉——內層表格照樣是來源寫過的參數表。"""
    html = (
        "<main><table>"
        "<tr><th>Name</th><th>Usage</th></tr>"
        "<tr><td>cardholder</td><td>"
        "<table><tr><th>Sub</th><th>Type</th></tr>"
        "<tr><td>phone</td><td>String</td></tr></table>"
        "</td></tr>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert ["Sub", "Type"] in rows
    assert ["phone", "String"] in rows


def test_the_outer_cell_does_not_swallow_the_nested_table_text():
    """內層表格的內容不該同時以跑馬燈文字塞回外層儲存格。"""
    html = (
        "<main><table>"
        "<tr><th>Name</th><th>Usage</th></tr>"
        "<tr><td>cardholder</td><td>Holder info"
        "<table><tr><td>phone</td><td>String</td></tr></table>"
        "</td></tr>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert ["cardholder", "Holder info"] in rows


def test_a_thead_row_is_the_header_even_when_it_is_not_first_in_source_order():
    html = (
        "<main><table>"
        "<tbody><tr><td>action</td><td>Y</td></tr></tbody>"
        "<thead><tr><th>參數</th><th>必要</th></tr></thead>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert rows[0] == ["參數", "必要"]
    assert ["action", "Y"] in rows[1:]


def test_a_body_only_table_still_uses_its_first_row_as_the_header():
    """GFM 沒有無表頭的表格,既有行為維持不變。"""
    html = (
        "<main><table><tbody>"
        "<tr><td>action</td><td>Y</td></tr>"
        "<tr><td>ts</td><td>N</td></tr>"
        "</tbody></table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert rows[0] == ["action", "Y"]


def test_an_absurd_span_is_ignored_rather_than_expanded():
    """`colspan="9999"` 展開會生出一張沒人寫過的表;寧可當成 1。"""
    html = (
        "<main><table>"
        "<tr><th>Name</th><th>Type</th></tr>"
        "<tr><td colspan='9999'>name</td><td>String</td></tr>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert all(len(row) <= 8 for row in rows)


def test_a_non_numeric_span_is_treated_as_one():
    html = (
        "<main><table>"
        "<tr><th>Name</th><th>Type</th></tr>"
        "<tr><td colspan='two'>name</td><td>String</td></tr>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert rows[1] == ["name", "String"]
