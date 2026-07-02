from __future__ import annotations

import re

from loop_apidoc.validate.models import Issue, IssueCode, Severity

_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
_ENDPOINT_RE = re.compile(r"^### `([A-Za-z]+)` `([^`]+)`")
_WEBHOOK_RE = re.compile(r"^### Webhook `([^`]+)`（method `([A-Za-z]+)`）")
_SECURITY_RE = re.compile(r"^- \*\*(.+?)\*\*（type")


def _mismatch(location: str, evidence: str) -> Issue:
    return Issue(
        code=IssueCode.OUTPUT_MISMATCH,
        severity=Severity.ERROR,
        location=location,
        evidence=evidence,
        suggested_fix="重新生成使 Markdown 與 OpenAPI inventory 一致",
    )


def _openapi_endpoints(openapi: dict) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for path, item in (openapi.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in item:
            if method.lower() in _HTTP_METHODS:
                out.add((method.lower(), path))
    return out


def _markdown_endpoints(markdown: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for line in markdown.splitlines():
        match = _ENDPOINT_RE.match(line)
        if match:
            out.add((match.group(1).lower(), match.group(2)))
    return out


def _openapi_webhooks(openapi: dict) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for name, item in (openapi.get("webhooks") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in item:
            if method.lower() in _HTTP_METHODS:
                out.add((method.lower(), name))
    return out


def _markdown_webhooks(markdown: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for line in markdown.splitlines():
        match = _WEBHOOK_RE.match(line)
        if match:
            out.add((match.group(2).lower(), match.group(1)))
    return out


def _openapi_security(openapi: dict) -> set[str]:
    schemes = (openapi.get("components") or {}).get("securitySchemes") or {}
    return set(schemes.keys())


def _markdown_security(markdown: str) -> set[str]:
    out: set[str] = set()
    for line in markdown.splitlines():
        match = _SECURITY_RE.match(line)
        if match:
            out.add(match.group(1))
    return out


def _path_parameter_conflicts(openapi: dict) -> list[Issue]:
    issues: list[Issue] = []
    for path, item in sorted((openapi.get("paths") or {}).items()):
        if not isinstance(item, dict):
            continue
        tokens = set(re.findall(r"\{([^{}/]+)\}", path))
        for method, operation in sorted(item.items()):
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            params = operation.get("parameters")
            if not isinstance(params, list):
                continue
            orphans = sorted(
                str(param.get("name"))
                for param in params
                if isinstance(param, dict)
                and param.get("in") == "path"
                and param.get("name")
                and str(param.get("name")) not in tokens
            )
            for name in orphans:
                issues.append(Issue(
                    code=IssueCode.SOURCE_CONFLICT,
                    severity=Severity.ERROR,
                    location=f"paths.{path}.{method.lower()}.parameters.{name}",
                    evidence=f"宣告的 path 參數 '{name}' 不在路徑模板 '{path}' 中",
                    suggested_fix="修正來源:改用正確的參數位置,或在路徑模板補上對應的 {token}",
                ))
    return issues


def check_consistency(openapi: dict, markdown: str) -> list[Issue]:
    issues: list[Issue] = []
    api_eps = _openapi_endpoints(openapi)
    md_eps = _markdown_endpoints(markdown)
    for method, path in sorted(api_eps - md_eps):
        issues.append(_mismatch(
            f"paths.{path}.{method}",
            f"OpenAPI 有 {method.upper()} {path} 但 Markdown 缺少"))
    for method, path in sorted(md_eps - api_eps):
        issues.append(_mismatch(
            f"paths.{path}.{method}",
            f"Markdown 有 {method.upper()} {path} 但 OpenAPI 缺少"))

    api_hooks = _openapi_webhooks(openapi)
    md_hooks = _markdown_webhooks(markdown)
    for method, name in sorted(api_hooks - md_hooks):
        issues.append(_mismatch(
            f"webhooks.{name}.{method}",
            f"OpenAPI 有 webhook {method.upper()} {name} 但 Markdown 缺少"))
    for method, name in sorted(md_hooks - api_hooks):
        issues.append(_mismatch(
            f"webhooks.{name}.{method}",
            f"Markdown 有 webhook {method.upper()} {name} 但 OpenAPI 缺少"))

    api_sec = _openapi_security(openapi)
    md_sec = _markdown_security(markdown)
    for name in sorted(api_sec ^ md_sec):
        issues.append(_mismatch(
            f"components.securitySchemes.{name}",
            f"security scheme {name} 在 Markdown 與 OpenAPI 不一致"))

    issues.extend(_path_parameter_conflicts(openapi))
    return issues
