"""標籤式端點宣告(`URL … Method …`)的辨識邊界,正反例逐條釘死(#97)。

閘門原本只認 `METHOD /path`。母體裡有一份來源(`jili-legacy-gaming-pdf`)把宣告寫成
帶標籤的一行——`|URL|<API URL>/Login|Method|GET|Return|HTML|`——method 與 path 都是
字面值,只是沒排成閘門要的順序。放寬到這個形狀不需要推論任何東西。

這個檔案存在的理由是:benchmark 只會告訴你警告消失了,不會告訴你哪些寫法被收下、
哪些被擋掉,而「窄」正是這個放寬的全部價值。任何一格變了,要嘛是有意的決策(連同
`docs/adr/0011-a-labelled-method-is-a-literal-not-an-inference.md` 一起改),要嘛是
一次沒被發現的漂移。
"""
from __future__ import annotations

import time

import pytest

from loop_apidoc.source_facts.markdown import scan_markdown


def _facts(text: str) -> list[tuple[str, str]]:
    return sorted((e.method, e.path) for e in scan_markdown("doc.md", text).endpoints)


@pytest.mark.parametrize(
    ("shape", "text", "expected"),
    [
        # 收下:標籤、method、path 三者都在同一行,而且都是字面值。
        (
            "表格列 + 佔位基底",
            "|URL|<API URL>/Login|Method|GET|Return|HTML|\n",
            [("GET", "/Login")],
        ),
        (
            "散文行 + 佔位基底",
            "URL <API URL>/CreateMember Method POST Return JSON Description 註冊。\n",
            [("POST", "/CreateMember")],
        ),
        (
            "表格列 + 完整 URL",
            "| URL | https://api.example.com/v1/pay | Method | POST |\n",
            [("POST", "/v1/pay")],
        ),
        (
            "表格列 + 裸路徑",
            "| URL | /v1/pay | Method | DELETE |\n",
            [("DELETE", "/v1/pay")],
        ),
        (
            "大括號佔位基底",
            "| URL | {host}/v1/pay | Method | PUT |\n",
            [("PUT", "/v1/pay")],
        ),
        (
            "HTTP Method 標籤",
            "| URL | /v1/pay | HTTP Method | POST |\n",
            [("POST", "/v1/pay")],
        ),
        # 佔位基底與路徑之間有空白仍然算數(jili 的 `<API URL> /GetMustHitBy`)。
        # 釘住它,否則之後把佔位規則收緊會靜默改掉一個已收下的寫法。
        (
            "佔位基底後有空白",
            "|URL|<API URL> /GetMustHitBy|Method|GET|\n",
            [("GET", "/GetMustHitBy")],
        ),
        # 擋掉:散文裡同時出現 URL 與 method 字面值。這是母體裡唯一會被
        # 「同行有 URL 又有 method」誤認的形狀,共六行,全部是假的。
        (
            "散文:句尾的 method + 連結",
            "Our server adapts [REST](https://en.wikipedia.org/wiki/REST) archetype, "
            "so all requests are sent using HTTP POST.\n",
            [],
        ),
        (
            "散文:行內路徑 + 連結",
            "Refund a capture API is only used, if you have requested Capture "
            "independenlty using [/pts/v2/payments/{id}/captures]"
            "(https://developer.cybersource.com/index.html#payments_capture) POST\n",
            [],
        ),
        # 擋掉:method 與 URL 分行寫。這正是 ADR 0007 判定為「推論 method」的那件事,
        # 這次放寬沒有改變那個立場——ecpay 的十四處宣告就是這個形狀,仍然不認。
        (
            "跨行:小節內的 URL 與 method",
            "## 介接路徑\n\n"
            "- 正式環境：https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5\n\n"
            "- HTTP Method ：POST\n",
            [],
        ),
        # 擋掉:method 在表頭、URL 在資料列(tappay 的形狀)。同樣是跨行。
        (
            "表頭 method + 資料列 URL",
            "| POST | Url |\n| --- | --- |\n| Sandbox | https://s.example.com/pay |\n",
            [],
        ),
        # 擋掉:GitBook 的兩段反引號。它仍然是 ADR 0009 記下的缺口而不是決策,
        # 本次母體量測顯示沒有任何來源使用它,觸發條件依然未成立。
        ("GitBook 兩段反引號", "`GET` `/a`\n", []),
        # 擋掉:method 不是大寫字面值。小寫要嘛是散文、要嘛是程式碼裡的鍵。
        ("小寫 method", "| URL | /v1/pay | Method | get |\n", []),
        ("程式碼風格的鍵值", 'method = "GET",\nbaseUrl = "https://x.example.com",\n', []),
        # 擋掉:標籤看似命中,但值裡沒有任何路徑可讀。寧可沉默。
        ("值不是路徑", "| URL | 參見附錄 A | Method | POST |\n", []),
        ("值只有主機", "| URL | https://api.example.com | Method | POST |\n", []),
        # 擋掉:標籤是別的字的一部分。`curl`、`URLs` 不是標籤。
        ("標籤黏在別的字裡", "Use curl to POST to /v1/pay from the URLs above\n", []),
        # 擋掉:順序相反。母體裡沒有來源這樣寫,依 ADR 0009 的先例,
        # 沒有來源使用的形狀不為它放寬 fail-closed 閘門。
        ("順序相反", "| Method | POST | URL | /v1/pay |\n", []),
        # 擋掉:首字大寫的 method。同一份 jili 文件裡有十處寫成 `Method|Get|`,
        # 仍然不認——#97 定的線是「大寫字面值」,而放寬大小寫正是 ADR 0009 記下
        # 兩套掃描器分歧的那一格。要改的話連同那兩份 ADR 一起改。
        ("首字大寫 method", "|URL|<API URL>/GetMustHitBy|Method|Get|\n", []),
        ("雙 method 格", "|URL|<API URL>/CreateFreeSpin|Method|Get/Post|\n", []),
        # 擋掉:值只是「開頭像路徑」的散文。整個值必須就是那條路徑。
        ("值後面還有散文", "URL /old was renamed, see the table. Method POST\n", []),
        ("值是靜態檔說明", "URL /images/logo.png is served statically; Method GET\n", []),
        # 擋掉:真參數表中間的設定列。它不是管線區塊的第一列——把它當宣告會
        # 生出一個假端點,並且把那張表從中切斷,其後的欄位全部消失。
        (
            "參數表中間的 URL 列",
            "## Pay\n\n`POST /pay`\n\n"
            "|Parameter|Type|Require|Description|\n"
            "|---|---|---|---|\n"
            "|MerchantID|string|Yes|商店代號|\n"
            "|URL|/callback|Method|POST|\n"
            "|Amount|int|Yes|金額|\n",
            [("POST", "/pay")],
        ),
        # 擋掉:圍籬內。範例程式碼不是宣告,這條規則不例外。
        ("圍籬內", "```json\n| URL | /v1/pay | Method | POST |\n```\n", []),
        # 擋掉:標籤之間隔了太遠的散文。長度上限讓「一行內剛好都出現」不算數。
        (
            "標籤相距過遠",
            "The URL " + "of the settlement report described in the appendix " * 4
            + " Method POST\n",
            [],
        ),
    ],
)
def test_labelled_declaration_boundary(shape, text, expected):
    assert _facts(text) == expected, shape


def test_a_labelled_declaration_row_opens_a_section_for_the_tables_below_it():
    """整個放寬的目的:宣告被認出來之後,底下的參數表才有端點可歸屬。

    jili 的形狀是宣告寫在一張小表的表頭列,參數表跟在後面。宣告如果不算數,
    那些參數表就沒有端點可依附,整份來源掃出零個事實。
    """
    text = (
        "## 2.1.1 登入\n\n"
        "|URL|<API URL>/Login|Method|GET|Return|HTML|\n"
        "|---|---|---|---|---|---|\n"
        "|Description|將會員導向進入遊戲。|||||\n\n"
        "Request : \n\n"
        "|Parameter|Type|Require|Description|\n"
        "|---|---|---|---|\n"
        "|Account|string|Yes|會員唯一識別值|\n"
        "|GameId|int|Yes|遊戲唯一識別值|\n"
    )

    facts = scan_markdown("doc.md", text)

    assert [(e.method, e.path) for e in facts.endpoints] == [("GET", "/Login")]
    assert facts.endpoints[0].parameter_names == ["Account", "GameId"]


@pytest.mark.parametrize(
    ("padding", "line"),
    [
        # 對齊排版的純文字(`pdftotext -layout` 的正常輸出)。
        (
            "空白",
            "URL" + " " * 60 + "<API URL>/Login" + " " * 60 + "Method" + " " * 60 + "Get",
        ),
        # 分隔符裡的冒號同時是合法的值起點,所以它自己就是一組候選分岔。
        ("冒號", "URL" + ": " * 3000 + "Method X"),
    ],
)
def test_a_near_miss_on_a_padded_line_does_not_take_exponential_time(padding, line):
    """近乎命中的長行不能讓掃描器停住。

    這條線釘的是回溯行為,不是輸出。分隔符一旦有多條路徑吃掉同一個字元,
    近乎命中的長行就會指數回溯:拆成三段量詞時十六個空白要兩秒,值的開頭
    容許冒號時四千字元要七秒半。母體裡最長的一行是 38,011 字元,所以這
    完全在掃描器已經要處理的尺寸之內,而它讀的是操作者給的任意文件。
    正確性測試看不見這一類 bug,所以這裡直接量時間。
    """
    start = time.perf_counter()
    result = scan_markdown("doc.md", line + "\n").endpoints
    elapsed = time.perf_counter() - start

    assert result == [], padding
    assert elapsed < 0.5, padding


def test_a_declaration_before_any_heading_ends_at_the_first_heading():
    """宣告出現在任何標題之前時,那一節必須在第一個標題結束。

    PDF 轉出來的文件正常就是先給宣告再開章節。少了這個分支,沒有標題層級
    小於等於 0,整份文件其後的參數表都會被算成這個端點的欄位。
    """
    text = (
        "|URL|<API URL>/Login|Method|GET|\n"
        "|---|---|\n\n"
        "# 另一章\n\n"
        "## 別的端點\n\n"
        "|Parameter|Type|Description|\n"
        "|---|---|---|\n"
        "|Unrelated|string|不是 Login 的參數|\n"
    )

    facts = scan_markdown("doc.md", text)

    assert [(e.method, e.path) for e in facts.endpoints] == [("GET", "/Login")]
    assert facts.endpoints[0].parameter_names == []


def test_a_pre_heading_declaration_gives_up_its_own_sub_headed_tables():
    """上一條的代價,明著釘出來:標題之前的宣告連 `## Request` 也帶不走。

    這裡本來讀得到 `Amount`。要留住它得讓層級 1 以外的標題不結束該節,但那樣
    一份全部用 `##` 當章節的文件又會整份被吃掉。在 fail-closed 閘門下漏一筆
    事實只是少跑一次檢查,多一筆假事實會擋掉正確的擷取,所以選漏的那一邊。
    """
    text = (
        "`POST /pay`\n\n"
        "## Request\n\n"
        "| Name | Type |\n| --- | --- |\n| Amount | int |\n"
    )

    assert scan_markdown("doc.md", text).endpoints[0].parameter_names == []


def test_the_declaration_row_does_not_also_become_a_parameter_table():
    """宣告列被抽走之後,剩下的分隔列與說明列湊不成表格,不會生出假欄位。"""
    text = (
        "|URL|<API URL>/Login|Method|GET|Return|HTML|\n"
        "|---|---|---|---|---|---|\n"
        "|Description|將會員導向進入遊戲。|||||\n"
    )

    assert scan_markdown("doc.md", text).endpoints[0].tables == ()
