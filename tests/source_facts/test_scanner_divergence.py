"""兩套 Markdown 掃描器的判準分歧,逐條釘死(#83)。

`source_facts/markdown.py` 餵的是 fail-closed 的語意完整性閘門:它讀到的每一筆都會
變成「擷取必須交出來」的要求,所以一個假事實會擋掉一份正確的擷取。
`markdown_drafts/markdown.py` 產的是給人審閱的非權威草稿:它多認一個、少認一個,
代價都是審閱者多看一眼。

兩者因此在幾個判準上刻意不同。問題從來不是「哪一套比較嚴」——它們的寬鬆處是**交錯**
的,各自朝自己的用途放寬。沒有寫下來的話,下一個維護者無從判斷該把哪一套改成另一套,
而任何一次「順手統一」都會安靜地移動閘門。

這個檔案就是那份紀錄的可執行形式:每個案例的兩欄答案都是刻意的,理由見
`docs/adr/0009-the-two-markdown-scanners-stay-separate.md`。任何一格變了,要嘛是
有意的決策(連同 ADR 一起改),要嘛是一次沒被發現的漂移。
"""
from __future__ import annotations

import pytest

from loop_apidoc.markdown_drafts.markdown import scan_markdown_drafts
from loop_apidoc.source_facts.markdown import scan_markdown


def _facts(text: str) -> list[tuple[str, str]]:
    return sorted((e.method, e.path) for e in scan_markdown("doc.md", text).endpoints)


def _drafts(text: str) -> list[tuple[str, str]]:
    return sorted(
        (e.method, e.path) for e in scan_markdown_drafts("doc.md", text).endpoints
    )


_ONE = [("GET", "/a")]


@pytest.mark.parametrize(
    ("shape", "text", "facts", "drafts"),
    [
        # 閘門認、草稿不認:草稿的結構單位是「小節」,一個沒有標題的宣告行
        # 開不出小節,而閘門要的是事實在哪裡就讀哪裡。
        ("裸行", "GET /a\n", _ONE, []),
        ("反引號行", "`GET /a`\n", _ONE, []),
        ("清單項", "- `GET /a`\n", _ONE, []),
        ("粗體行", "**GET /a**\n", _ONE, []),
        # 兩者都認:標題本身就是宣告,是最沒有歧義的形狀。
        ("標題", "## GET /a\n", _ONE, _ONE),
        # 草稿認、閘門不認:閘門的比對錨在行首,草稿在整行搜尋。錨定擋掉的是
        # 「見 POST /pay 的說明」這類散文誤判,代價是漏掉有前綴的標題。
        ("標題含前綴", "## 支付 GET /a\n", [], _ONE),
        ("小寫標題", "## get /a\n", [], _ONE),
        # GitBook 把 method 與 path 寫成兩段反引號。草稿認得,閘門不認得——
        # 這是已知的辨識缺口,不是刻意的嚴格(見 ADR 0007)。
        ("GitBook 兩段反引號", "`GET` `/a`\n", [], _ONE),
        # 閘門認、草稿不認,方向與上一格相反——這正是「沒有哪一套比較嚴」的例子。
        # 標籤式宣告的 method 與 path 都是字面值(ADR 0011),但它開不出小節。
        ("標籤式宣告", "|URL|<API URL>/a|Method|GET|Return|JSON|\n", _ONE, []),
        # 兩者都不認:行內夾在散文中間的宣告,誰讀了都是在猜。
        ("散文行內", "呼叫 GET /a 取得資料\n", [], []),
        ("小寫裸行", "get /a\n", [], []),
    ],
)
def test_declaration_forms_each_scanner_recognises(shape, text, facts, drafts):
    assert (_facts(text), _drafts(text)) == (facts, drafts), shape


def test_an_unlabelled_parameter_table_is_read_by_the_gate_only():
    """草稿要靠 **Request** 這類標籤決定欄位歸到哪一節;閘門不分節,只問有沒有。"""
    text = "## GET /a\n\n| Name | Type |\n| --- | --- |\n| id | string |\n"

    assert scan_markdown("doc.md", text).endpoints[0].parameter_names == ["id"]
    assert scan_markdown_drafts("doc.md", text).endpoints[0].fields == ()


def test_a_labelled_parameter_table_is_read_by_both():
    text = (
        "## GET /a\n\n**Request**\n\n| Name | Type |\n| --- | --- |\n| id | string |\n"
    )

    assert scan_markdown("doc.md", text).endpoints[0].parameter_names == ["id"]
    assert len(scan_markdown_drafts("doc.md", text).endpoints[0].fields) == 1


@pytest.mark.parametrize("language", ["json", "bash", "java"])
def test_the_gate_counts_any_fenced_block_as_an_example(language):
    """閘門只需要「這裡有範例」這個事實;草稿要把範例貼進去,所以挑得動的語言。"""
    text = f"## GET /a\n\n```{language}\n{{}}\n```\n"

    assert scan_markdown("doc.md", text).endpoints[0].example_blocks == 1
    assert bool(scan_markdown_drafts("doc.md", text).endpoints[0].examples) is (
        language == "json"
    )


def test_only_the_draft_scanner_closes_a_fence_that_carries_an_info_string():
    """ADR 0008 的分歧:草稿寬容,閘門嚴格。

    閘門一旦寬容,兩個相鄰的開啟圍籬會被讀成一開一關,夾在中間的範例就變成事實。
    草稿寬容的代價只是審閱者多看一段。
    """
    text = "```json\n{}\n```json\n\n## GET /a\n"

    assert _facts(text) == []
    assert _drafts(text) == _ONE
