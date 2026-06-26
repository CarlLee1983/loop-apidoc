from __future__ import annotations

from loop_apidoc.validate.consistency import check_consistency
from loop_apidoc.validate.models import IssueCode

_OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "X", "version": "1.0"},
    "paths": {"/users": {"get": {"responses": {"200": {"description": "ok"}}}}},
    "components": {"securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X"}}},
}
_MARKDOWN_MATCH = (
    "## Endpoint\n"
    "### `GET` `/users`\n"
    "## 驗證／授權\n"
    "- **ApiKeyAuth**（type：`apiKey`，位置：`header`，名稱：`X`）\n"
)


def test_matching_inventory_has_no_issues():
    assert check_consistency(_OPENAPI, _MARKDOWN_MATCH) == []


def test_openapi_endpoint_absent_from_markdown_flagged():
    issues = check_consistency(_OPENAPI, "## Endpoint\n## 驗證／授權\n"
                               "- **ApiKeyAuth**（type：`apiKey`）\n")
    assert any(i.code is IssueCode.OUTPUT_MISMATCH and "/users" in i.location
               for i in issues)


def test_markdown_endpoint_absent_from_openapi_flagged():
    md = _MARKDOWN_MATCH + "### `POST` `/ghost`\n"
    issues = check_consistency(_OPENAPI, md)
    assert any(i.code is IssueCode.OUTPUT_MISMATCH and "/ghost" in i.location
               for i in issues)


def test_security_name_mismatch_flagged():
    md = (
        "## Endpoint\n### `GET` `/users`\n"
        "## 驗證／授權\n- **OtherAuth**（type：`apiKey`）\n"
    )
    issues = check_consistency(_OPENAPI, md)
    assert any(i.code is IssueCode.OUTPUT_MISMATCH and "securitySchemes" in i.location
               for i in issues)
