from __future__ import annotations

import json
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


def _collect_operations(
    items: Any, out: dict[str, dict], key: Any
) -> None:
    if not isinstance(items, dict):
        return
    for name, item in items.items():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            method_l = str(method).lower()
            if method_l in _METHODS and isinstance(operation, dict):
                out[key(method_l.upper(), name)] = operation


def _operation_map(openapi: dict) -> dict[str, dict]:
    # OpenAPI 3.1 splits operations across top-level `paths` and `webhooks`;
    # the generator emits both, so the diff must cover both. The op-key prefix
    # marks which namespace a location lives in (`POST /x` vs `POST webhooks:x`).
    out: dict[str, dict] = {}
    _collect_operations(openapi.get("paths"), out, lambda m, name: f"{m} {name}")
    _collect_operations(
        openapi.get("webhooks"), out, lambda m, name: f"{m} webhooks:{name}"
    )
    return out


def _op_area(op_key: str) -> str:
    return "openapi.webhooks" if " webhooks:" in op_key else "openapi.paths"


def _looks_like_object(schema: Any) -> bool:
    return isinstance(schema, dict) and (
        schema.get("type") == "object"
        or ("type" not in schema and isinstance(schema.get("properties"), dict))
    )


def _schema_signature(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    keys = ("type", "$ref", "enum", "oneOf", "anyOf", "allOf", "format")
    signature = {key: schema.get(key) for key in keys if key in schema}
    if _looks_like_object(schema):
        signature["type"] = "object"
    return signature


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
        if _looks_like_object(base) != _looks_like_object(head):
            return

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

    # `_schema_signature` deliberately omits `items` (it would be a nested dict),
    # so array element changes (array<string> -> array<integer>) only surface by
    # recursing into items the same way we recurse into object properties.
    base_items = base.get("items")
    head_items = head.get("items")
    if isinstance(base_items, dict) and isinstance(head_items, dict):
        _compare_schema(
            base_items,
            head_items,
            area=area,
            location=f"{location}[]",
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
        base_schema = base_params[key].get("schema")
        head_schema = head_params[key].get("schema")
        if _looks_like_object(base_schema) and _looks_like_object(head_schema):
            _compare_schema(
                base_schema,
                head_schema,
                area="openapi.parameters",
                location=f"{op_key} parameters.{key}",
                findings=findings,
                added_required_is_breaking=True,
                removed_property_is_breaking=False,
            )
        else:
            before = _schema_signature(base_schema)
            after = _schema_signature(head_schema)
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
    base_body = base.get("requestBody")
    head_body = head.get("requestBody")
    if isinstance(base_body, dict) and isinstance(head_body, dict):
        base_req = bool(base_body.get("required"))
        head_req = bool(head_body.get("required"))
        if base_req != head_req:
            findings.append(
                _finding(
                    DiffImpact.BREAKING if head_req else DiffImpact.CHANGED,
                    "openapi.requestBody",
                    f"{op_key} requestBody.required",
                    "request body became required"
                    if head_req
                    else "request body no longer required",
                    base_req,
                    head_req,
                )
            )

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
            _finding(DiffImpact.ADDITIVE, _op_area(op_key), op_key, "operation added", None, head_ops[op_key])
        )
    for op_key in sorted(base_ops.keys() - head_ops.keys()):
        findings.append(
            _finding(DiffImpact.BREAKING, _op_area(op_key), op_key, "operation removed", base_ops[op_key], None)
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


def _integration_items(integration: dict | None, section: str) -> dict[str, dict]:
    if not integration:
        return {}
    raw = integration.get(section)
    if not isinstance(raw, list):
        return {}
    out: dict[str, dict] = {}
    seen: dict[str, int] = {}
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        if section == "crypto":
            key = item.get("name") or f"{item.get('purpose', 'crypto')}:{item.get('algorithm', idx)}"
        elif section == "callbacks":
            key = item.get("name") or item.get("trigger") or str(idx)
        elif section == "field_conditions":
            key = f"{item.get('scope', idx)}:{item.get('when', '')}"
        elif section == "test_cases":
            key = item.get("name") or item.get("operation_ref") or str(idx)
        else:
            key = str(idx)
        key = str(key)
        # Unnamed items can collapse to the same fallback key (e.g. two crypto
        # blocks sharing purpose+algorithm). Suffix repeats with a stable
        # occurrence index so each is tracked separately instead of silently
        # overwriting the prior one.
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        out[f"{key}#{occurrence}" if occurrence else key] = item
    return out


def _compare_section_items(
    base: dict | None,
    head: dict | None,
    section: str,
    singular: str,
    core_fields: set[str],
) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_items = _integration_items(base, section)
    head_items = _integration_items(head, section)
    for key in sorted(head_items.keys() - base_items.keys()):
        findings.append(
            _finding(
                DiffImpact.ADDITIVE,
                "integration",
                f"integration.{section}.{key}",
                f"integration {singular} added",
                None,
                head_items[key],
            )
        )
    for key in sorted(base_items.keys() - head_items.keys()):
        findings.append(
            _finding(
                DiffImpact.BREAKING,
                "integration",
                f"integration.{section}.{key}",
                f"integration {singular} removed",
                base_items[key],
                None,
            )
        )
    for key in sorted(base_items.keys() & head_items.keys()):
        fields = sorted(set(base_items[key]) | set(head_items[key]))
        for field in fields:
            before = base_items[key].get(field)
            after = head_items[key].get(field)
            if before == after:
                continue
            impact = DiffImpact.BREAKING if field in core_fields else DiffImpact.CHANGED
            core = " core" if impact is DiffImpact.BREAKING else ""
            findings.append(
                _finding(
                    impact,
                    "integration",
                    f"integration.{section}.{key}.{field}",
                    f"integration {singular}{core} field changed",
                    before,
                    after,
                )
            )
    return findings


def _compare_integration(base: dict | None, head: dict | None) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    findings.extend(
        _compare_section_items(
            base,
            head,
            "crypto",
            "crypto",
            {"algorithm", "mode", "key_source", "payload_assembly", "verify"},
        )
    )
    findings.extend(
        _compare_section_items(
            base,
            head,
            "callbacks",
            "callback",
            {"verification", "expected_response"},
        )
    )
    findings.extend(
        _compare_section_items(
            base,
            head,
            "field_conditions",
            "field condition",
            {"then_required"},
        )
    )
    findings.extend(
        _compare_section_items(
            base,
            head,
            "test_cases",
            "test case",
            set(),
        )
    )
    return findings


def _provenance_map(artifacts: RunArtifacts) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for entry in artifacts.provenance.entries:
        out.setdefault(entry.target, []).append(entry.model_dump(mode="json"))
    for entries in out.values():
        entries.sort(
            key=lambda entry: (
                entry.get("manifest_source") or "",
                entry.get("query_id") or "",
                json.dumps(entry, sort_keys=True, separators=(",", ":")),
            )
        )
    return out


def _compare_provenance(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_entries = _provenance_map(base)
    head_entries = _provenance_map(head)
    for target in sorted(set(base_entries) | set(head_entries)):
        before = base_entries.get(target)
        after = head_entries.get(target)
        if before != after:
            findings.append(
                _finding(
                    DiffImpact.SOURCE_ONLY,
                    "provenance",
                    target,
                    "provenance changed",
                    before,
                    after,
                )
            )
    return findings


def _issue_key(issue) -> tuple[str, str, str, str, str]:
    # `suggested_fix` is part of the issue's identity here: changing only the
    # remediation text still alters validation/report.json, so it must shift the
    # key (surfacing as a removed+added pair) rather than diffing to nothing.
    return (
        issue.code.value,
        issue.severity.value,
        issue.location,
        issue.evidence,
        issue.suggested_fix,
    )


def _compare_validation(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    base_issues = {_issue_key(issue): issue for issue in base.validation.issues}
    head_issues = {_issue_key(issue): issue for issue in head.validation.issues}
    for key in sorted(head_issues.keys() - base_issues.keys()):
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "validation",
                f"validation.{key[0]}.{key[2]}",
                "validation issue added",
                None,
                head_issues[key].model_dump(mode="json"),
            )
        )
    for key in sorted(base_issues.keys() - head_issues.keys()):
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "validation",
                f"validation.{key[0]}.{key[2]}",
                "validation issue removed",
                base_issues[key].model_dump(mode="json"),
                None,
            )
        )
    return findings


def _manifest_local_map(artifacts: RunArtifacts) -> dict[str, dict]:
    # Exclude `scanned_at`: it changes on every rescan even when the source file
    # is byte-identical, which would flood a normal rerun diff with spurious
    # "manifest source changed" noise. Content identity lives in sha256/status.
    return {
        source.relative_path: source.model_dump(mode="json", exclude={"scanned_at"})
        for source in artifacts.manifest.local_sources
    }


def _manifest_url_map(artifacts: RunArtifacts) -> dict[str, dict]:
    # Same rationale as local sources: `fetched_at` is a rerun timestamp, not a
    # content signal (content_sha256/http_status carry that).
    return {
        source.url: source.model_dump(mode="json", exclude={"fetched_at"})
        for source in artifacts.manifest.url_sources
    }


def _compare_manifest(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    for label, base_map, head_map in (
        ("local", _manifest_local_map(base), _manifest_local_map(head)),
        ("url", _manifest_url_map(base), _manifest_url_map(head)),
    ):
        for key in sorted(set(base_map) | set(head_map)):
            before = base_map.get(key)
            after = head_map.get(key)
            if before != after:
                findings.append(
                    _finding(
                        DiffImpact.SOURCE_ONLY,
                        "manifest",
                        f"manifest.{label}.{key}",
                        "manifest source changed",
                        before,
                        after,
                    )
                )
    return findings


def _preparation_phase_map(artifacts: RunArtifacts) -> dict[str, dict]:
    if artifacts.preparation is None:
        return {}
    return {
        phase.id: phase.model_dump(mode="json")
        for phase in artifacts.preparation.phases
    }


def _compare_preparation(base: RunArtifacts, head: RunArtifacts) -> list[DiffFinding]:
    findings: list[DiffFinding] = []
    if base.preparation is None and head.preparation is None:
        return findings
    if base.preparation is None:
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "preparation",
                "preparation",
                "preparation report added",
                None,
                head.preparation.model_dump(mode="json"),
            )
        )
        return findings
    if head.preparation is None:
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "preparation",
                "preparation",
                "preparation report removed",
                base.preparation.model_dump(mode="json"),
                None,
            )
        )
        return findings

    if base.preparation.status != head.preparation.status:
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "preparation",
                "preparation.status",
                "preparation status changed",
                base.preparation.status.value,
                head.preparation.status.value,
            )
        )
    if base.preparation.summary != head.preparation.summary:
        findings.append(
            _finding(
                DiffImpact.SOURCE_ONLY,
                "preparation",
                "preparation.summary",
                "preparation summary changed",
                base.preparation.summary,
                head.preparation.summary,
            )
        )

    base_phases = _preparation_phase_map(base)
    head_phases = _preparation_phase_map(head)
    for phase_id in sorted(set(base_phases) | set(head_phases)):
        before = base_phases.get(phase_id)
        after = head_phases.get(phase_id)
        if before != after:
            findings.append(
                _finding(
                    DiffImpact.SOURCE_ONLY,
                    "preparation",
                    f"preparation.phases.{phase_id}",
                    "preparation phase changed",
                    before,
                    after,
                )
            )
    return findings


def build_diff_report(base: RunArtifacts, head: RunArtifacts) -> DiffReport:
    findings: list[DiffFinding] = []
    findings.extend(_compare_openapi(base.openapi, head.openapi))
    findings.extend(_compare_integration(base.integration, head.integration))
    findings.extend(_compare_provenance(base, head))
    findings.extend(_compare_validation(base, head))
    findings.extend(_compare_manifest(base, head))
    findings.extend(_compare_preparation(base, head))
    findings = _sorted_findings(findings)
    return DiffReport(
        base_run=str(base.run_dir),
        head_run=str(head.run_dir),
        summary=_summary(findings),
        findings=findings,
    )
