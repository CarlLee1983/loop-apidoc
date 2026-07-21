from __future__ import annotations

import pytest

from loop_apidoc.markdown_drafts.markdown import scan_markdown_drafts
from loop_apidoc.markdown_drafts.models import MarkdownDraftIndex


def test_project_scaffold_orders_endpoint_files_and_preserves_literal_fields():
    from loop_apidoc.extraction_scaffold.project import project_scaffold

    drafts = MarkdownDraftIndex(
        sources=(
            scan_markdown_drafts("z.md", "## POST /z\n"),
            scan_markdown_drafts(
                "a.md",
                "## GET /a\n### Query\n| Name | Required |\n| --- | --- |\n| limit | yes |\n",
            ),
        ),
    )

    bundle = project_scaffold(drafts, {"a.md": "# A\n", "z.md": "# Z\n"}, "sources")

    assert [item.filename for item in bundle.endpoints] == ["ep00.json", "ep01.json"]
    assert bundle.inventory["version"] is None
    assert bundle.inventory["overview"] == ""
    assert bundle.endpoints[0].body["parameters"] == [
        {"name": "limit", "in": "query", "type": None, "required": True, "description": None},
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("是", True), ("必填", True), ("yes", True), ("Y", True),
        ("否", False), ("選填", False), ("no", False), ("N", False),
        ("", None), ("depends", None),
    ],
)
def test_project_scaffold_parses_only_unambiguous_required_values(value: str, expected: bool | None):
    from loop_apidoc.extraction_scaffold.project import project_scaffold

    source = (
        "## POST /pay\n"
        "### Request Body\n"
        "| Name | Type | Required | Description |\n"
        "| --- | --- | --- | --- |\n"
        f"| token | string | {value} | Token |\n"
    )
    bundle = project_scaffold(
        MarkdownDraftIndex(sources=(scan_markdown_drafts("pay.md", source),)),
        {"pay.md": source},
        "sources",
    )

    endpoint = bundle.endpoints[0].body
    assert endpoint["parameters"][0]["required"] is expected
    assert ("required flag missing for token" in endpoint["missing"]) is (expected is None)


def test_project_scaffold_records_invalid_or_non_json_examples_without_projecting_them():
    from loop_apidoc.extraction_scaffold.project import project_scaffold

    source = (
        "## POST /pay\n"
        "### Request\n"
        "```json\n"
        "{bad}\n"
        "```\n"
        "### Response\n"
        "```xml\n"
        "<ok/>\n"
        "```\n"
    )
    bundle = project_scaffold(
        MarkdownDraftIndex(sources=(scan_markdown_drafts("pay.md", source),)),
        {"pay.md": source},
        "sources",
    )

    endpoint = bundle.endpoints[0].body
    assert endpoint["examples"] == []
    assert endpoint["request"] == {
        "content_type": "application/json", "schema": None, "required": None, "description": None,
    }
    assert endpoint["responses"] == [{"status": "default", "description": None, "schema": None, "schema_ref": None}]
    assert any("unparsed JSON example lines 3-5" == gap for gap in endpoint["missing"])
    assert any("non-JSON example lines 7-9" == gap for gap in endpoint["missing"])


def test_project_scaffold_uses_entry_h1_and_harvests_appendix_errors_without_host_inference():
    from loop_apidoc.extraction_scaffold.project import project_scaffold

    index = "# Wallet API\n\n## Error codes\n| Code | 說明 |\n| --- | --- |\n| 1001 | Invalid token |\n| 1001 | Later duplicate |\n"
    endpoint = "## GET /balance\n"
    bundle = project_scaffold(
        MarkdownDraftIndex(sources=(
            scan_markdown_drafts("sources.md", index),
            scan_markdown_drafts("api/balance.md", endpoint),
        )),
        {"sources.md": index, "api/balance.md": endpoint},
        "sources",
    )

    assert bundle.inventory["title"] == "Wallet API"
    assert bundle.inventory["errors"] == [{
        "code": "1001", "meaning": "Invalid token", "http_status": None,
        "applicable_to": [], "source": "sources.md lines 6-6 # Error codes",
    }]
    assert "API base URL not stated in scanned sources" in bundle.inventory["missing"]
