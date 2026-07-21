from __future__ import annotations

from loop_apidoc.markdown_drafts.markdown import scan_markdown_drafts


def test_scan_markdown_drafts_keeps_explicit_endpoint_tables_and_examples():
    source = """# Transfer

## POST /api/transfer

### Headers
| Name | Type | Required | Description |
| --- | --- | --- | --- |
| X-Token | string | yes | Access token |

### Query Parameters
| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| notify | boolean | no | Send notification |

### Request Body
```json
{"amount": 10}
```

### Response
```xml
<ok>true</ok>
```
"""

    draft = scan_markdown_drafts("api/transfer.md", source)

    assert draft.relative_path == "api/transfer.md"
    assert len(draft.endpoints) == 1
    endpoint = draft.endpoints[0]
    assert (endpoint.method, endpoint.path, endpoint.start_line) == ("POST", "/api/transfer", 3)
    assert [(field.label, field.name, field.type, field.required, field.description, field.start_line) for field in endpoint.fields] == [
        ("headers", "X-Token", "string", "yes", "Access token", 8),
        ("query", "notify", "boolean", "no", "Send notification", 13),
    ]
    assert [(example.language, example.label, example.start_line, example.end_line, example.content) for example in endpoint.examples] == [
        ("json", "request", 16, 18, '{"amount": 10}'),
        ("xml", "response", 21, 23, "<ok>true</ok>"),
    ]


def test_scan_markdown_drafts_supports_chinese_labels_and_omits_ambiguous_tables():
    source = """## GET /v1/balance

### 請求標頭
| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| X-Client | string | 是 | Client id |

### 常數
| Name | Value |
| --- | --- |
| currency | TWD |

| Name | Type |
| --- | --- |
| leaked | string |
"""

    draft = scan_markdown_drafts("balance.md", source)

    assert [(field.label, field.name) for field in draft.endpoints[0].fields] == [
        ("headers", "X-Client"),
    ]


def test_scan_markdown_drafts_supports_gitbook_marked_method_and_bold_labels():
    source = """# Register

<mark style="color:green;">`POST`</mark> `/vg/sign-up`

**Headers**
| Name | Value |
| --- | --- |
| Content-Type | `application/json` |

**Body**
| Name | Type | Description |
| --- | --- | --- |
| `agent` | string | Agent name |

**Response**
```json
{"code": 1000}
```
"""

    draft = scan_markdown_drafts("sign-up.md", source)

    endpoint = draft.endpoints[0]
    assert (endpoint.method, endpoint.path, endpoint.start_line) == ("POST", "/vg/sign-up", 3)
    assert [(field.label, field.name) for field in endpoint.fields] == [
        ("headers", "Content-Type"),
        ("request", "agent"),
    ]
    assert [(example.label, example.start_line, example.end_line) for example in endpoint.examples] == [
        ("response", 16, 18),
    ]
