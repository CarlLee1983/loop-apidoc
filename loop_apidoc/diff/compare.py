from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from loop_apidoc.diff.loader import RunArtifacts
from loop_apidoc.diff.models import DiffFinding, DiffImpact, DiffReport

_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
_IMPACT_ORDER = {
    DiffImpact.BREAKING: 0,
    DiffImpact.ADDITIVE: 1,
    DiffImpact.CHANGED: 2,
    DiffImpact.SOURCE_ONLY: 3,
}
_SUMMARY_KEYS = [impact.value for impact in DiffImpact]


def _finding(
    impact: DiffImpact,
    area: str,
    location: str,
    summary: str,
    before: Any | None = None,
    after: Any | None = None,
) -> DiffFinding:
    return DiffFinding(
        impact=impact,
        area=area,
        location=location,
        summary=summary,
        before=before,
        after=after,
    )


def _sorted_findings(findings: Iterable[DiffFinding]) -> list[DiffFinding]:
    return sorted(
        findings,
        key=lambda f: (_IMPACT_ORDER[f.impact], f.area, f.location, f.summary),
    )


def _summary(findings: list[DiffFinding]) -> dict[str, int]:
    counts = {key: 0 for key in _SUMMARY_KEYS}
    for finding in findings:
        counts[finding.impact.value] += 1
    return counts


def _operation_map(openapi: dict) -> dict[str, dict]:
    paths = openapi.get("paths")
    if not isinstance(paths, dict):
        return {}
    out: dict[str, dict] = {}
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            method_l = str(method).lower()
            if method_l in _METHODS and isinstance(operation, dict):
                out[f"{method_l.upper()} {path}"] = operation
    return out


def _schema_signature(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    keys = ("type", "$ref", "enum", "oneOf", "anyOf", "allOf", "format")
    return {key: schema.get(key) for key in keys if key in schema}


def _content_schemas(container: dict | None) -> dict[str, dict]:
    if not isinstance(container, dict):
        return {}
    content = container.get("content")
    if not isinstance(content, dict):
        return {}
    out: dict[str, dict] = {}
    for media_type, media in content.items():
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            out[str(media_type)] = media["schema"]
    return out


def _request_schemas(operation: dict) -> dict[str, dict]:
    return _content_schemas(operation.get("requestBody"))


def _response_schemas(response: dict) -> dict[str, dict]:
    return _content_schemas(response)


def _properties(schema: dict) -> dict[str, dict]:
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


def _required(schema: dict) -> set[str]:
    raw = schema.get("required")
    return {str(item) for item in raw} if isinstance(raw, list) else set()


def _compare_schema(
    base: dict,
    head: dict,
    *,
    area: str,
    location: str,
    findings: list[DiffFinding],
    added_required_is_breaking: bool,
    removed_property_is_breaking: bool,
) -> None:
    base_sig = _schema_signature(base)
    head_sig = _schema_signature(head)
    if base_sig != head_sig:
        findings.append(
            _finding(
                DiffImpact.BREAKING,
                area,
                location,
                "schema changed",
                base_sig,
                head_sig,
            )
        )

    base_props = _properties(base)
    head_props = _properties(head)
    base_required = _required(base)
    head_required = _required(head)

    for name in sorted(head_props.keys() - base_props.keys()):
        is_required = name in head_required
        if is_required and added_required_is_breaking:
            impact = DiffImpact.BREAKING
            summary = "required property added"
        else:
            impact = DiffImpact.ADDITIVE
            summary = "optional property added"
        findings.append(
            _finding(impact, area, f"{location}.{name}", summary, None, head_props[name])
        )

    for name in sorted(base_props.keys() - head_props.keys()):
        impact = DiffImpact.BREAKING if removed_property_is_breaking else DiffImpact.CHANGED
        findings.append(
            _finding(impact, area, f"{location}.{name}", "property removed", base_props[name], None)
        )

    for name in sorted(base_props.keys() & head_props.keys()):
        _compare_schema(
            base_props[name],
            head_props[name],
            area=area,
            location=f"{location}.{name}",
            findings=findings,
            added_required_is_breaking=added_required_is_breaking,
            removed_property_is_breaking=removed_property_is_breaking,
        )

    for name in sorted(head_required - base_required):
        if name in base_props and name in head_props:
            findings.append(
                _finding(
                    DiffImpact.BREAKING,
                    area,
                    f"{location}.{name}",
                    "property became required",
                    sorted(base_required),
                    sorted(head_required),
                )
            )

    for name in sorted(base_required - head_required):
        findings.append(
            _finding(
                DiffImpact.CHANGED,
                area,
                f"{location}.{name}",
                "property no longer required",
                sorted(base_required),
                sorted(head_required),
            )
        )


def _parameter_key(parameter: dict) -> str:
    return f"{parameter.get('in', 'query')}.{parameter.get('name', '')}"


def _parameter_map(operation: dict) -> dict[str, dict]:
    params = operation.get("parameters")
    if not isinstance(params, list):
        return {}
    return {
        _parameter_key(param): param
        for param in params
        if isinstance(param, dict) and param.get("name")
    }


def _compare_parameters(
    op_key: str,
    base: dict,
    head: dict,
    findings: list[DiffFinding],
) -> None:
    base_params = _parameter_map(base)
    head_params = _parameter_map(head)
    for key in sorted(head_params.keys() - base_params.keys()):
        param = head_params[key]
        required = bool(param.get("required"))
        findings.append(
            _finding(
                DiffImpact.BREAKING if required else DiffImpact.ADDITIVE,
                "openapi.parameters",
                f"{op_key} parameters.{key}",
                "required parameter added" if required else "optional parameter added",
                None,
                param,
            )
        )
    for key in sorted(base_params.keys() - head_params.keys()):
        findings.append(
            _finding(
                DiffImpact.CHANGED,
                "openapi.parameters",
                f"{op_key} parameters.{key}",
                "parameter removed",
                base_params[key],
                None,
            )
        )
    for key in sorted(base_params.keys() & head_params.keys()):
        before = _schema_signature(base_params[key].get("schema"))
        after = _schema_signature(head_params[key].get("schema"))
        if before != after:
            findings.append(
                _finding(
                    DiffImpact.BREAKING,
                    "openapi.parameters",
                    f"{op_key} parameters.{key}",
                    "parameter schema changed",
                    before,
                    after,
                )
            )
        if base_params[key].get("description") != head_params[key].get("description"):
            findings.append(
                _finding(
                    DiffImpact.CHANGED,
                    "openapi.parameters",
                    f"{op_key} parameters.{key}",
                    "parameter description changed",
                    base_params[key].get("description"),
                    head_params[key].get("description"),
                )
            )


def _compare_request_body(
    op_key: str,
    base: dict,
    head: dict,
    findings: list[DiffFinding],
) -> None:
    base_schemas = _request_schemas(base)
    head_schemas = _request_schemas(head)
    for media_type in sorted(head_schemas.keys() - base_schemas.keys()):
        findings.append(
            _finding(
                DiffImpact.ADDITIVE,
                "openapi.requestBody",
                f"{op_key} requestBody.{media_type}",
                "request media type added",
                None,
                head_schemas[media_type],
            )
        )
    for media_type in sorted(base_schemas.keys() - head_schemas.keys()):
        findings.append(
            _finding(
                DiffImpact.BREAKING,
                "openapi.requestBody",
                f"{op_key} requestBody.{media_type}",
                "request media type removed",
                base_schemas[media_type],
                None,
            )
        )
    for media_type in sorted(base_schemas.keys() & head_schemas.keys()):
        _compare_schema(
            base_schemas[media_type],
            head_schemas[media_type],
            area="openapi.requestBody",
            location=f"{op_key} requestBody.{media_type}",
            findings=findings,
            added_required_is_breaking=True,
            removed_property_is_breaking=False,
        )


def _responses(operation: dict) -> dict[str, dict]:
    responses = operation.get("responses")
    return responses if isinstance(responses, dict) else {}


def _compare_responses(
    op_key: str,
    base: dict,
    head: dict,
    findings: list[DiffFinding],
) -> None:
    base_responses = _responses(base)
    head_responses = _responses(head)
    for status in sorted(head_responses.keys() - base_responses.keys()):
        findings.append(
            _finding(
                DiffImpact.ADDITIVE,
                "openapi.responses",
                f"{op_key} responses.{status}",
                "response added",
                None,
                head_responses[status],
            )
        )
    for status in sorted(base_responses.keys() - head_responses.keys()):
        findings.append(
            _finding(
                DiffImpact.BREAKING,
                "openapi.responses",
                f"{op_key} responses.{status}",
                "response removed",
                base_responses[status],
                None,
            )
        )
    for status in sorted(base_responses.keys() & head_responses.keys()):
        base_schemas = _response_schemas(base_responses[status])
        head_schemas = _response_schemas(head_responses[status])
        for media_type in sorted(head_schemas.keys() - base_schemas.keys()):
            findings.append(
                _finding(
                    DiffImpact.ADDITIVE,
                    "openapi.responses",
                    f"{op_key} responses.{status}.{media_type}",
                    "response media type added",
                    None,
                    head_schemas[media_type],
                )
            )
        for media_type in sorted(base_schemas.keys() - head_schemas.keys()):
            findings.append(
                _finding(
                    DiffImpact.BREAKING,
                    "openapi.responses",
                    f"{op_key} responses.{status}.{media_type}",
                    "response media type removed",
                    base_schemas[media_type],
                    None,
                )
            )
        for media_type in sorted(base_schemas.keys() & head_schemas.keys()):
            _compare_schema(
                base_schemas[media_type],
                head_schemas[media_type],
                area="openapi.responses",
                location=f"{op_key} responses.{status}.{media_type}",
                findings=findings,
                added_required_is_breaking=False,
                removed_property_is_breaking=True,
            )


def _compare_operations(base: dict, head: dict) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_ops = _operation_map(base)
    head_ops = _operation_map(head)
    for op_key in sorted(head_ops.keys() - base_ops.keys()):
        findings.append(
            _finding(DiffImpact.ADDITIVE, "openapi.paths", op_key, "operation added", None, head_ops[op_key])
        )
    for op_key in sorted(base_ops.keys() - head_ops.keys()):
        findings.append(
            _finding(DiffImpact.BREAKING, "openapi.paths", op_key, "operation removed", base_ops[op_key], None)
        )
    for op_key in sorted(base_ops.keys() & head_ops.keys()):
        base_op = base_ops[op_key]
        head_op = head_ops[op_key]
        for field in ("summary", "description"):
            if base_op.get(field) != head_op.get(field):
                findings.append(
                    _finding(
                        DiffImpact.CHANGED,
                        "openapi.operations",
                        f"{op_key}.{field}",
                        f"operation {field} changed",
                        base_op.get(field),
                        head_op.get(field),
                    )
                )
        if base_op.get("security") != head_op.get("security"):
            findings.append(
                _finding(
                    DiffImpact.BREAKING,
                    "openapi.security",
                    f"{op_key}.security",
                    "operation security changed",
                    base_op.get("security"),
                    head_op.get("security"),
                )
            )
        _compare_parameters(op_key, base_op, head_op, findings)
        _compare_request_body(op_key, base_op, head_op, findings)
        _compare_responses(op_key, base_op, head_op, findings)
    return findings


def _components(openapi: dict, name: str) -> dict:
    components = openapi.get("components")
    if not isinstance(components, dict):
        return {}
    section = components.get(name)
    return section if isinstance(section, dict) else {}


def _compare_component_schemas(base: dict, head: dict) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_schemas = _components(base, "schemas")
    head_schemas = _components(head, "schemas")
    for name in sorted(head_schemas.keys() - base_schemas.keys()):
        findings.append(
            _finding(DiffImpact.ADDITIVE, "openapi.schemas", f"components.schemas.{name}", "schema added", None, head_schemas[name])
        )
    for name in sorted(base_schemas.keys() - head_schemas.keys()):
        findings.append(
            _finding(DiffImpact.CHANGED, "openapi.schemas", f"components.schemas.{name}", "schema removed", base_schemas[name], None)
        )
    for name in sorted(base_schemas.keys() & head_schemas.keys()):
        if isinstance(base_schemas[name], dict) and isinstance(head_schemas[name], dict):
            _compare_schema(
                base_schemas[name],
                head_schemas[name],
                area="openapi.schemas",
                location=f"components.schemas.{name}",
                findings=findings,
                added_required_is_breaking=True,
                removed_property_is_breaking=True,
            )
        elif base_schemas[name] != head_schemas[name]:
            findings.append(
                _finding(DiffImpact.BREAKING, "openapi.schemas", f"components.schemas.{name}", "schema changed", base_schemas[name], head_schemas[name])
            )
    return findings


def _compare_security_schemes(base: dict, head: dict) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_schemes = _components(base, "securitySchemes")
    head_schemes = _components(head, "securitySchemes")
    for name in sorted(head_schemes.keys() - base_schemes.keys()):
        findings.append(
            _finding(DiffImpact.ADDITIVE, "openapi.security", f"components.securitySchemes.{name}", "security scheme added", None, head_schemes[name])
        )
    for name in sorted(base_schemes.keys() - head_schemes.keys()):
        findings.append(
            _finding(DiffImpact.BREAKING, "openapi.security", f"components.securitySchemes.{name}", "security scheme removed", base_schemes[name], None)
        )
    for name in sorted(base_schemes.keys() & head_schemes.keys()):
        if base_schemes[name] != head_schemes[name]:
            findings.append(
                _finding(DiffImpact.BREAKING, "openapi.security", f"components.securitySchemes.{name}", "security scheme changed", base_schemes[name], head_schemes[name])
            )
    return findings


def _compare_openapi(base: dict, head: dict) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    for field in ("title", "version"):
        before = base.get("info", {}).get(field) if isinstance(base.get("info"), dict) else None
        after = head.get("info", {}).get(field) if isinstance(head.get("info"), dict) else None
        if before != after:
            findings.append(
                _finding(DiffImpact.CHANGED, "openapi.info", f"openapi.info.{field}", f"info {field} changed", before, after)
            )
    if base.get("servers") != head.get("servers"):
        findings.append(
            _finding(DiffImpact.CHANGED, "openapi.servers", "openapi.servers", "servers changed", base.get("servers"), head.get("servers"))
        )
    findings.extend(_compare_operations(base, head))
    findings.extend(_compare_component_schemas(base, head))
    findings.extend(_compare_security_schemes(base, head))
    return findings


def build_diff_report(base: RunArtifacts, head: RunArtifacts) -> DiffReport:
    findings = _sorted_findings(_compare_openapi(base.openapi, head.openapi))
    return DiffReport(
        base_run=str(base.run_dir),
        head_run=str(head.run_dir),
        summary=_summary(findings),
        findings=findings,
    )
