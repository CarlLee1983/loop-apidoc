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
    # 圍籬內是虛擬碼而非 payload,依 payload-only 規則不計為範例。
    assert facts.endpoints[0].example_blocks == 0


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


# --- 以下皆為 code review 實證回報的缺陷回歸(issue #14 後續) ---

def test_a_deeper_subheading_does_not_disarm_the_endpoint() -> None:
    """最常見的版面是端點標題下再開「### 請求參數」;若被當成換段,
    整張參數表就不會歸屬任何端點,閘門對這種文件等於沒開火。"""
    text = """
## GET /games

### Request Parameters

| Name | Type |
| --- | --- |
| provider | string |

### 回應參數

| Name | Type |
| --- | --- |
| code | int |
"""
    facts = scan_markdown("doc.md", text)
    assert [(e.method, e.path) for e in facts.endpoints] == [("GET", "/games")]
    assert facts.endpoints[0].parameter_names == ["provider", "code"]


def test_a_sibling_heading_still_ends_the_endpoint_section() -> None:
    text = """
## GET /games

### Request Parameters

| Name | Type |
| --- | --- |
| provider | string |

## Error codes

| Name | Meaning |
| --- | --- |
| E001 | bad |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == ["provider"]


def test_a_setext_heading_ends_the_endpoint_section() -> None:
    """setext 標題(底線式)不帶 #,漏認就會把下一節的錯誤碼表併進端點。"""
    text = """
## Games

`GET /games`

| Name | Type |
| --- | --- |
| provider | string |

Error codes
-----------

| Name | Meaning |
| --- | --- |
| E001 | bad |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == ["provider"]


def test_a_fence_between_two_tables_keeps_them_separate() -> None:
    """圍籬前後各一張表時,未結算的表會跨過圍籬與下一張合併,
    把第二張的表頭列(`Name`)變成一個無人能滿足的必要欄位。"""
    text = """
## Games

`GET /games`

| Name | Type |
| --- | --- |
| provider | string |
```json
{"a": 1}
```
| Name | Type |
| --- | --- |
| page | int |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == ["provider", "page"]


def test_a_label_first_table_uses_the_wire_name_column() -> None:
    """中文文件常把第一欄寫成人看的標籤、第二欄才是實際欄位名。
    照第一欄要求,正確的擷取永遠過不了。"""
    text = """
## POST /pay

| 參數名稱 | 英文名稱 | 型態 |
| --- | --- | --- |
| 商店代號 | MerchantID | string |
| 交易金額 | Amount | int |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == ["MerchantID", "Amount"]


def test_a_cjk_only_table_keeps_its_own_names() -> None:
    """沒有英文欄可選時,中文鍵就是真的鍵,不能因為非 ASCII 就丟掉。"""
    text = """
## POST /pay

| 參數名稱 | 型態 |
| --- | --- |
| 商店代號 | string |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == ["商店代號"]


def test_annotations_and_links_are_stripped_from_the_name_cell() -> None:
    text = """
## Games

`GET /games`

| Name | Type |
| --- | --- |
| username(必填) | string |
| X-Token (required) | string |
| amount<br>金額 | int |
| [provider](#provider) | string |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == [
        "username", "X-Token", "amount", "provider",
    ]


def test_a_constant_value_table_is_not_a_parameter_table() -> None:
    """`Content-Type: application/json` 是常數對照表;正確的擷取會把它
    模型成 media type,而不是一個參數。"""
    text = """
## Games

`GET /games`

| Header Name | Value |
| --- | --- |
| Content-Type | application/json |
| X-Sign | abc |
"""
    facts = scan_markdown("doc.md", text)
    assert facts.endpoints[0].parameter_names == []


def test_only_payload_like_fences_count_as_examples() -> None:
    """簽章章節滿是虛擬碼圍籬;把它們當範例會逼出一個來源沒有的 examples。"""
    text = """
## Sign

`POST /pay`

```
sha256(a + b)
```

```text
hex encode
```
"""
    assert scan_markdown("doc.md", text).endpoints[0].example_blocks == 0


def test_json_and_xml_fences_still_count_as_examples() -> None:
    text = """
## Pay

`POST /pay`

```json
{"a": 1}
```

```
<root/>
```
"""
    assert scan_markdown("doc.md", text).endpoints[0].example_blocks == 2
