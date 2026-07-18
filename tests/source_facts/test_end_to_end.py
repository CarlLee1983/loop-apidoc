"""真實 markdown → 掃描 → 閘門的端到端測試。

單元測試手工建 `EndpointFact`,因此掃描器與閘門之間的接縫沒有任何覆蓋——
而 code review 找到的缺陷全部住在那條接縫上。基準語料也幫不上忙:唯一的
.md 來源是壓平的 HTML 傾印,掃出零筆事實,所以「基準全綠」對這道閘門不構成
任何證據。這個檔案就是那道安全網,每個案例都釘住「不得誤擋正確擷取」。
"""

from __future__ import annotations

from loop_apidoc.source_facts.gate import source_fact_violations
from loop_apidoc.source_facts.markdown import scan_markdown
from loop_apidoc.source_facts.models import FactIndex


def _gate(markdown: str, endpoint: dict, inventory: dict | None = None) -> list[str]:
    index = FactIndex(sources=[scan_markdown("doc.md", markdown)])
    return source_fact_violations(index, [("ep1.json", endpoint)], inventory)


def _ep(**overrides) -> dict:
    return {"method": "GET", "path": "/games", "parameters": [], **overrides}


def test_a_correct_extraction_clears_a_subheading_layout() -> None:
    markdown = """
## GET /games

### Request Parameters

| Name | Type |
| --- | --- |
| provider | string |
"""
    assert _gate(markdown, _ep(parameters=[{"name": "provider"}])) == []


def test_an_empty_extraction_is_blocked_on_a_subheading_layout() -> None:
    """這是 issue #14 的形狀,而且是最常見的版面——閘門必須在這裡開火。"""
    markdown = """
## GET /games

### Request Parameters

| Name | Type |
| --- | --- |
| provider | string |
"""
    assert "provider" in _gate(markdown, _ep())[0]


def test_an_error_code_table_in_a_sibling_section_is_not_demanded() -> None:
    markdown = """
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
    assert _gate(markdown, _ep(parameters=[{"name": "provider"}])) == []


def test_a_fence_between_tables_does_not_demand_a_header_cell() -> None:
    markdown = """
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
    endpoint = _ep(
        parameters=[{"name": "provider"}, {"name": "page"}],
        examples=[{"body": "{}"}],
    )
    assert _gate(markdown, endpoint) == []


def test_a_label_first_table_is_satisfied_by_the_wire_names() -> None:
    markdown = """
## POST /pay

| 參數名稱 | 英文名稱 | 型態 |
| --- | --- | --- |
| 商店代號 | MerchantID | string |
| 交易金額 | Amount | int |
"""
    endpoint = {
        "method": "POST", "path": "/pay",
        "parameters": [{"name": "MerchantID"}, {"name": "Amount"}],
    }
    assert _gate(markdown, endpoint) == []


def test_a_signature_section_of_pseudocode_demands_no_example() -> None:
    markdown = """
## Sign

`POST /pay`

```
sha256(a + b)
```

| Name | Type |
| --- | --- |
| sign | string |
"""
    endpoint = {
        "method": "POST", "path": "/pay",
        "parameters": [{"name": "sign"}], "examples": [],
    }
    assert _gate(markdown, endpoint) == []


def test_a_documented_payload_example_is_still_demanded() -> None:
    markdown = """
## Pay

`POST /pay`

```json
{"amount": 1}
```

| Name | Type |
| --- | --- |
| amount | int |
"""
    endpoint = {
        "method": "POST", "path": "/pay",
        "parameters": [{"name": "amount"}], "examples": [],
    }
    assert "example" in _gate(markdown, endpoint)[0].lower()


def test_a_header_constant_table_is_not_demanded_as_a_parameter() -> None:
    markdown = """
## Games

`GET /games`

| Header Name | Value |
| --- | --- |
| Content-Type | application/json |
"""
    assert _gate(markdown, _ep()) == []


def test_an_overview_page_does_not_widen_the_detail_page_requirement() -> None:
    overview = """
## GET /games

| Name | Description |
| --- | --- |
| games | list games |
| balance | read balance |
"""
    detail = """
## GET /games

| Name | Type |
| --- | --- |
| provider | string |
"""
    index = FactIndex(sources=[
        scan_markdown("overview.md", overview),
        scan_markdown("detail.md", detail),
    ])
    endpoint = _ep(parameters=[{"name": "provider"}])
    assert source_fact_violations(index, [("ep1.json", endpoint)]) == []
