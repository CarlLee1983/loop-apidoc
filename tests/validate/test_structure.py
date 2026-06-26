from __future__ import annotations

from loop_apidoc.generate import REQUIRED_MARKDOWN_SECTIONS
from loop_apidoc.validate.models import IssueCode, Severity
from loop_apidoc.validate.structure import check_structure

_GOOD_OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "X", "version": "1.0"},
    "paths": {},
}
_GOOD_MARKDOWN = "\n".join(REQUIRED_MARKDOWN_SECTIONS)


def test_valid_structure_has_no_issues():
    assert check_structure(_GOOD_OPENAPI, _GOOD_MARKDOWN) == []


def test_invalid_openapi_flagged():
    bad = {"openapi": "3.1.0", "info": {"title": "X"}, "paths": {}}  # missing version
    issues = check_structure(bad, _GOOD_MARKDOWN)
    assert any(i.code is IssueCode.OPENAPI_INVALID for i in issues)
    assert all(i.severity is Severity.ERROR for i in issues)


def test_missing_markdown_section_flagged():
    md = _GOOD_MARKDOWN.replace(REQUIRED_MARKDOWN_SECTIONS[0], "")
    issues = check_structure(_GOOD_OPENAPI, md)
    mismatches = [i for i in issues if i.code is IssueCode.OUTPUT_MISMATCH]
    assert len(mismatches) == 1
    assert REQUIRED_MARKDOWN_SECTIONS[0] in mismatches[0].location


def test_unresolvable_ref_flagged():
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "X", "version": "1.0"},
        "paths": {
            "/u": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Ghost"}
                                }
                            },
                        }
                    }
                }
            }
        },
        "components": {"schemas": {}},
    }
    issues = check_structure(doc, _GOOD_MARKDOWN)
    assert any(i.code is IssueCode.OPENAPI_INVALID for i in issues)
