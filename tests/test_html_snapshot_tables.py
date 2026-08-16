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

    # 文字只留在它自己的位置,跨到的欄位補空:重複它會毀掉「其餘欄位全空」這個
    # 下游用來認出分組標題列的訊號(見 source_facts/markdown.py)。
    assert rows[0] == ["Request", "", "Note"]
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

    assert rows[1] == ["name", "String"]


def test_a_non_numeric_span_is_treated_as_one():
    html = (
        "<main><table>"
        "<tr><th>Name</th><th>Type</th></tr>"
        "<tr><td colspan='two'>name</td><td>String</td></tr>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert rows[1] == ["name", "String"]


def test_a_colspan_group_title_row_stays_recognisable_as_a_group_title():
    """跨欄的分組標題列不得變成一個叫「Header」的參數。

    `source_facts/markdown.py` 認分組標題列的判準是「其餘欄位全空」。把跨欄儲存格
    的文字重複填進每一欄會毀掉那個訊號,於是來源根本沒寫的欄位變成來源事實,而
    假事實在 fail-closed 閘門下會擋掉正確的擷取——正是這張票要防的傷害。
    """
    from loop_apidoc.source_facts.markdown import scan_markdown

    html = (
        "<main><h2>POST /pay</h2><table>"
        "<tr><th>參數</th><th>型別</th><th>必要</th></tr>"
        "<tr><td colspan='3'>Header</td></tr>"
        "<tr><td>api_key</td><td>String</td><td>Y</td></tr>"
        "</table></main>"
    )

    facts = scan_markdown("doc.md", html_to_markdown(html))

    assert facts.endpoints[0].parameter_names == ["api_key"]


def test_a_spanning_section_row_does_not_void_an_error_code_table():
    """錯誤碼表的分組列同理:訊號一毀,整張表被作廢,記載下界靜靜歸零。"""
    from loop_apidoc.source_facts.markdown import scan_markdown

    html = (
        "<main><h2>錯誤碼</h2><table>"
        "<tr><th>錯誤碼</th><th>說明</th></tr>"
        "<tr><td colspan='2'>支付類</td></tr>"
        "<tr><td>1001</td><td>餘額不足</td></tr>"
        "</table></main>"
    )

    facts = scan_markdown("doc.md", html_to_markdown(html))

    assert [fact.code for fact in facts.error_codes] == ["1001"]


def test_rows_survive_a_missing_closing_tr_tag():
    """`<tr>` 未閉合時解析器會把下一列變成上一列的子節點,那些列不得消失。"""
    html = (
        "<main><table>"
        "<tr><td>a</td><td>b</td>"
        "<tr><td>c</td><td>d</td>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert rows == [["a", "b"], ["c", "d"]]


def test_overlapping_spans_discard_the_whole_table():
    """對不齊就整張放棄,與錯誤碼表「一列壞掉作廢整張」的既有偏誤一致。

    靜靜讓後寫的儲存格蓋掉前一列帶下來的,會產出一張看起來正常、內容卻錯位的表。
    """
    html = (
        "<main><table>"
        "<tr><td>A</td><td rowspan='2'>B</td></tr>"
        "<tr><td colspan='3'>C</td></tr>"
        "</table></main>"
    )

    assert _rows(html_to_markdown(html)) == []


def test_a_tfoot_written_before_tbody_still_renders_after_it():
    """HTML 允許 tfoot 寫在 tbody 之前,但它是表尾。"""
    html = (
        "<main><table>"
        "<thead><tr><th>Name</th><th>Type</th></tr></thead>"
        "<tfoot><tr><td>f1</td><td>f2</td></tr></tfoot>"
        "<tbody><tr><td>b1</td><td>b2</td></tr></tbody>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert rows == [["Name", "Type"], ["b1", "b2"], ["f1", "f2"]]


def test_a_two_row_thead_merges_into_one_header():
    """GFM 只有一列表頭。第二列降級成資料列會變成一個叫「Name」的參數。"""
    html = (
        "<main><table>"
        "<thead><tr><th>Request</th><th>Request</th></tr>"
        "<tr><th>Name</th><th>Type</th></tr></thead>"
        "<tbody><tr><td>api_key</td><td>String</td></tr></tbody>"
        "</table></main>"
    )

    rows = _rows(html_to_markdown(html))

    assert rows[0] == ["Request Name", "Request Type"]
    assert rows[1] == ["api_key", "String"]
