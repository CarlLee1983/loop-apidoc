"""來源事實掃描器:只認機械可證的東西,絕不推論。"""

from __future__ import annotations

from loop_apidoc.source_facts.markdown import scan_markdown

ATG_LIKE = """
# ATG Game API

## 遊戲列表

`GET /games`

Header

| 參數名稱 | 型態 | 必填 | 說明 |
| --- | --- | --- | --- |
| X-Token | string | Y | 認證權杖 |

Query

| 參數名稱 | 型態 | 必填 | 說明 |
| --- | --- | --- | --- |
| provider | string | N | 廠商代碼 |
| category | string | N | 分類 |
| rows | int | N | 每頁筆數 |

Response

```json
{"code": 0, "data": []}
```

## 取得餘額

`POST /game-providers/{providerId}/balance`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| username | string | Y | 玩家帳號 |
| balance | number | Y | 金額 |
| action | string | Y | 動作 |
| transferId | string | Y | 交易序號 |

## 說明章節

這一節沒有任何端點,只有一段文字。
"""


def test_scans_method_and_path_from_section_headings() -> None:
    facts = scan_markdown("doc.md", ATG_LIKE)
    assert [(f.method, f.path) for f in facts.endpoints] == [
        ("GET", "/games"),
        ("POST", "/game-providers/{providerId}/balance"),
    ]


def test_collects_parameter_names_from_every_table_in_the_section() -> None:
    facts = scan_markdown("doc.md", ATG_LIKE)
    games = facts.endpoints[0]
    assert games.parameter_names == [
        "X-Token",
        "provider",
        "category",
        "rows",
    ]


def test_recognises_english_field_headers() -> None:
    facts = scan_markdown("doc.md", ATG_LIKE)
    balance = facts.endpoints[1]
    assert balance.parameter_names == ["username", "balance", "action", "transferId"]


def test_records_fenced_example_blocks_per_section() -> None:
    facts = scan_markdown("doc.md", ATG_LIKE)
    assert facts.endpoints[0].example_blocks == 1
    assert facts.endpoints[1].example_blocks == 0


def test_sections_without_an_endpoint_are_not_facts() -> None:
    facts = scan_markdown("doc.md", ATG_LIKE)
    assert len(facts.endpoints) == 2


def test_tables_without_a_name_like_header_are_ignored() -> None:
    text = """
## Rates

`GET /rates`

| 幣別 | 匯率 |
| --- | --- |
| TWD | 1.0 |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == []


def test_heading_itself_may_carry_the_method_and_path() -> None:
    text = """
### GET /users/{id}

| Name | Type |
| --- | --- |
| id | string |
"""
    facts = scan_markdown("doc.md", text)
    assert (facts.endpoints[0].method, facts.endpoints[0].path) == ("GET", "/users/{id}")
    assert facts.endpoints[0].parameter_names == ["id"]


def test_code_fences_do_not_leak_endpoints_or_tables() -> None:
    text = """
## Example

`GET /real`

```
GET /not-an-endpoint

| Name | Type |
| --- | --- |
| ghost | string |
```
"""
    facts = scan_markdown("doc.md", text)
    assert [f.path for f in facts.endpoints] == ["/real"]
    assert facts.endpoints[0].parameter_names == []
    assert facts.endpoints[0].example_blocks == 1


def test_records_the_source_relative_path_and_section_heading() -> None:
    facts = scan_markdown("api/doc.md", ATG_LIKE)
    assert facts.relative_path == "api/doc.md"
    assert facts.endpoints[0].heading == "遊戲列表"


def test_nested_field_rows_are_normalised_to_real_field_names() -> None:
    """巢狀欄位常用縮排實體與樹狀符號排版;照字面收下就會要求一個不存在的欄位。"""
    text = """
## Balance

`POST /balance`

| Name | Type |
| --- | --- |
| user | object |
| &nbsp;&nbsp;user.id | string |
| └ name | string |
| ↳ amount | number |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == ["user", "user.id", "name", "amount"]


def test_group_label_rows_are_not_fields() -> None:
    """只有第一欄有字、其餘全空的列是分組標題,不是欄位。"""
    text = """
## Games

`GET /games`

| Name | Type | Required |
| --- | --- | --- |
| **Header** | | |
| X-Token | string | Y |
| Query | | |
| provider | string | N |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == ["X-Token", "provider"]


def test_a_single_column_table_still_yields_its_rows() -> None:
    """單欄表沒有「其餘欄位」可判空,不能被分組標題規則整張吃掉。"""
    text = """
## Games

`GET /games`

| Name |
| --- |
| provider |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == ["provider"]


def test_flattened_html_dumps_yield_no_facts() -> None:
    """把 HTML 壓平成單行的來源沒有可機械判讀的結構,掃描器必須保持沉默。

    這是刻意的:從無結構文字猜出「來源有參數表」會生出假事實,而假事實在
    fail-closed 閘門下會擋掉正確的擷取。代價是閘門對這類來源等同無效——
    這個限制寫在這裡,免得日後誤以為閘門涵蓋所有來源。
    """
    flattened = (
        "API 名稱 描述 WithBalance/Player/Deposit 存入點數 傳入參數說明 "
        "參數 型態 說明 WebId string 站台代碼 Account string 會員帳號 "
        "GET /games 回傳資訊說明 code int 錯誤代碼"
    )
    assert scan_markdown("dump.md", flattened).endpoints == []


def test_a_table_followed_by_a_fence_still_belongs_to_its_own_endpoint() -> None:
    """表格尚未結算就遇到圍籬時,不能延後歸屬到下一個端點。"""
    text = """
## A

`GET /a`

| Name | Type |
| --- | --- |
| alpha | string |
```json
{"x": 1}
```
## B

`GET /b`

| Name | Type |
| --- | --- |
| beta | string |
"""
    a, b = scan_markdown("doc.md", text).endpoints
    assert (a.parameter_names, a.example_blocks) == (["alpha"], 1)
    assert (b.parameter_names, b.example_blocks) == (["beta"], 0)
