from __future__ import annotations

from openapi_spec_validator import validate as validate_openapi
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError
from referencing.exceptions import PointerToNowhere

from loop_apidoc.generate import REQUIRED_MARKDOWN_SECTIONS
from loop_apidoc.validate.models import Issue, IssueCode, Severity


def _error(code: IssueCode, location: str, evidence: str, fix: str) -> Issue:
    return Issue(
        code=code,
        severity=Severity.ERROR,
        location=location,
        evidence=evidence,
        suggested_fix=fix,
    )


def _iter_refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _iter_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_refs(value)


def _resolves(ref: str, root: dict) -> bool:
    if not ref.startswith("#/"):
        return False
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False
    return True


def check_structure(openapi: dict, markdown: str) -> list[Issue]:
    issues: list[Issue] = []
    try:
        validate_openapi(openapi)
    except (OpenAPIValidationError, PointerToNowhere) as exc:
        issues.append(_error(
            IssueCode.OPENAPI_INVALID, "openapi", str(exc)[:300],
            "修正 OpenAPI 文件使其符合 3.1 schema",
        ))
    for ref in _iter_refs(openapi):
        if ref.startswith("#/") and not _resolves(ref, openapi):
            issues.append(_error(
                IssueCode.OPENAPI_INVALID, ref, f"$ref 無法解析：{ref}",
                "補上被引用的 components 定義或移除 $ref",
            ))
    for section in REQUIRED_MARKDOWN_SECTIONS:
        if section not in markdown:
            issues.append(_error(
                IssueCode.OUTPUT_MISMATCH, f"markdown:{section}",
                f"Markdown 缺少必要章節：{section}",
                "在 Markdown 補上該章節標題",
            ))
    return issues
