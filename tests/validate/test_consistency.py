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


def test_matching_webhooks_have_no_issues():
    openapi = {
        "openapi": "3.1.0", "info": {"title": "X", "version": "1.0"},
        "paths": {},
        "webhooks": {"付款結果通知": {"post": {"responses": {"200": {"description": "ok"}}}}},
        "components": {"securitySchemes": {}},
    }
    md = (
        "## Endpoint\n"
        "### Webhook `付款結果通知`（method `POST`）\n"
        "## 驗證／授權\n"
    )
    assert check_consistency(openapi, md) == []


def test_openapi_webhook_absent_from_markdown_flagged():
    openapi = {
        "openapi": "3.1.0", "info": {"title": "X", "version": "1.0"},
        "paths": {},
        "webhooks": {"付款結果通知": {"post": {"responses": {"200": {"description": "ok"}}}}},
        "components": {"securitySchemes": {}},
    }
    issues = check_consistency(openapi, "## Endpoint\n## 驗證／授權\n")
    assert any(i.code is IssueCode.OUTPUT_MISMATCH and "webhooks.付款結果通知" in i.location
               for i in issues)


def test_security_name_mismatch_flagged():
    md = (
        "## Endpoint\n### `GET` `/users`\n"
        "## 驗證／授權\n- **OtherAuth**（type：`apiKey`）\n"
    )
    issues = check_consistency(_OPENAPI, md)
    assert any(i.code is IssueCode.OUTPUT_MISMATCH and "securitySchemes" in i.location
               for i in issues)


from loop_apidoc.validate.models import Severity


def test_declared_path_param_absent_from_template_is_conflict():
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": "X", "version": "1.0"},
        "paths": {
            "/users": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {}}
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    markdown = "## Endpoint\n### `GET` `/users`\n## 驗證／授權\n"
    conflicts = [
        i for i in check_consistency(openapi, markdown)
        if i.code is IssueCode.SOURCE_CONFLICT
    ]
    assert len(conflicts) == 1
    assert conflicts[0].severity is Severity.ERROR
    assert "id" in conflicts[0].evidence
    assert "/users" in conflicts[0].evidence


def test_path_param_matching_template_is_not_a_conflict():
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": "X", "version": "1.0"},
        "paths": {
            "/users/{id}": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {}}
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    markdown = "## Endpoint\n### `GET` `/users/{id}`\n## 驗證／授權\n"
    assert not [
        i for i in check_consistency(openapi, markdown)
        if i.code is IssueCode.SOURCE_CONFLICT
    ]
