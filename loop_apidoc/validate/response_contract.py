from __future__ import annotations

from pydantic import BaseModel, Field

from loop_apidoc.generate.openapi import MISSING_STATUS, X_LOOP_STATUS
from loop_apidoc.validate.models import Issue, IssueCode, Severity

_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


class ResponseContractMetrics(BaseModel):
    path_operations: int = 0
    operations_with_usable_schema: int = 0
    hollow_operations: int = 0
    field_count: int = 0


class ResponseContractAnalysis(BaseModel):
    metrics: ResponseContractMetrics
    issues: list[Issue] = Field(default_factory=list)


def _success_responses(operation: dict) -> list[dict]:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return []
    return [
        response
        for status, response in responses.items()
        if isinstance(response, dict)
        and (str(status).lower() == "default" or str(status).startswith("2"))
    ]


def _schemas(responses: list[dict]) -> list[dict]:
    schemas: list[dict] = []
    for response in responses:
        content = response.get("content")
        if not isinstance(content, dict):
            continue
        for media in content.values():
            if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                schemas.append(media["schema"])
    return schemas


def _is_missing_source_placeholder(responses: list[dict]) -> bool:
    return any(response.get(X_LOOP_STATUS) == MISSING_STATUS for response in responses)


def _resolve_local_ref(document: dict, ref: str) -> dict | None:
    if not ref.startswith("#/"):
        return None
    current: object = document
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current if isinstance(current, dict) else None


def _schema_field_count(
    schema: dict,
    document: dict,
    seen_refs: frozenset[str] = frozenset(),
) -> int:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        if ref in seen_refs:
            return 0
        resolved = _resolve_local_ref(document, ref)
        if resolved is None:
            return 0
        return _schema_field_count(resolved, document, seen_refs | {ref})

    composed_count = 0
    has_composition = False
    for keyword in ("allOf", "oneOf", "anyOf"):
        branches = schema.get(keyword)
        if not isinstance(branches, list):
            continue
        has_composition = True
        composed_count += sum(
            _schema_field_count(branch, document, seen_refs)
            for branch in branches
            if isinstance(branch, dict)
        )
    if has_composition:
        return composed_count

    properties = schema.get("properties")
    if isinstance(properties, dict):
        return sum(
            _schema_field_count(field_schema, document, seen_refs)
            for field_schema in properties.values()
            if isinstance(field_schema, dict)
        )

    if schema.get("type") == "array":
        items = schema.get("items")
        return (
            _schema_field_count(items, document, seen_refs)
            if isinstance(items, dict)
            else 0
        )

    if schema.get("type") == "object":
        return 0
    return 1 if schema else 0


def analyze_response_contracts(openapi: dict) -> ResponseContractAnalysis:
    path_operations = 0
    operations_with_usable_schema = 0
    hollow_operations = 0
    field_count = 0
    issues: list[Issue] = []

    for path, path_item in (openapi.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            path_operations += 1
            success_responses = _success_responses(operation)
            schemas = _schemas(success_responses)
            operation_field_count = sum(
                _schema_field_count(schema, openapi) for schema in schemas
            )
            if operation_field_count:
                operations_with_usable_schema += 1
                field_count += operation_field_count
                continue
            hollow_operations += 1
            if _is_missing_source_placeholder(success_responses):
                continue
            location = f"paths.{path}.{method.lower()}"
            issues.append(
                Issue(
                    code=IssueCode.REQUIRED_INFO_MISSING,
                    severity=Severity.WARNING,
                    location=location,
                    evidence="successful response has no usable schema contract",
                    suggested_fix=(
                        "Re-read the endpoint response envelope and record its schema; "
                        "when the source is silent, keep this delivery gap visible."
                    ),
                    target_file="endpoints/",
                    field_path="responses",
                    requery_scope=location,
                )
            )

    return ResponseContractAnalysis(
        metrics=ResponseContractMetrics(
            path_operations=path_operations,
            operations_with_usable_schema=operations_with_usable_schema,
            hollow_operations=hollow_operations,
            field_count=field_count,
        ),
        issues=issues,
    )
