from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

_NO_SPECULATION = (
    "For any field the sources do not provide, use null and add a short label "
    "for it to the `missing` array. Do not infer or fill values from REST, OAuth, "
    "or industry conventions. Only report what the sources state."
)


class QueryKind(str, Enum):
    INITIAL = "initial"
    FOLLOWUP = "followup"
    REVERSE = "reverse"


class StageMode(str, Enum):
    STRUCTURED = "structured"
    NARRATIVE = "narrative"


class QueryStage(BaseModel):
    stage_id: str
    title: str
    mode: StageMode
    goal: str
    json_key: str | None = None
    json_hint: str | None = None


def _structured(stage_id: str, title: str, goal: str, key: str, schema: str) -> QueryStage:
    hint = (
        f'Return ONLY one fenced ```json block of the form: {schema} '
        f"The top-level array key MUST be `{key}`, plus a `missing` array of strings. "
        f"{_NO_SPECULATION}"
    )
    return QueryStage(
        stage_id=stage_id, title=title, mode=StageMode.STRUCTURED, goal=goal,
        json_key=key, json_hint=hint,
    )


def _narrative(stage_id: str, title: str, goal: str) -> QueryStage:
    return QueryStage(stage_id=stage_id, title=title, mode=StageMode.NARRATIVE, goal=goal)


STAGES: tuple[QueryStage, ...] = (
    _narrative(
        "01", "Notebook and source inventory",
        "Describe every source document and URL you can see in this notebook, "
        "including file names and the topics each covers. State explicitly if you "
        "cannot see a source.",
    ),
    _narrative(
        "02", "API system overview and terminology",
        "Summarize the overall purpose of the API and define its key terms, strictly "
        "from the sources. Note anything the sources do not cover.",
    ),
    _structured(
        "03", "Environments, base URLs and versions",
        "List every environment, base URL and API version stated by the sources.",
        "environments",
        '{"environments": [{"name": str|null, "base_url": str|null, "version": '
        'str|null, "source": str|null}], "missing": [str]}',
    ),
    _structured(
        "04", "Authentication, authorization and signing",
        "List every authentication, authorization and request-signing scheme stated "
        "by the sources.",
        "security_schemes",
        '{"security_schemes": [{"name": str|null, "type": str|null, "location": '
        'str|null, "details": str|null, "source": str|null}], "missing": [str]}',
    ),
    _structured(
        "05", "Endpoint inventory",
        "List every endpoint stated by the sources with its HTTP method, path and a "
        "short summary.",
        "endpoints",
        '{"endpoints": [{"method": str|null, "path": str|null, "summary": str|null, '
        '"source": str|null}], "missing": [str]}',
    ),
    _structured(
        "06", "Per-endpoint details",
        "For every endpoint, give parameters, request body, response statuses and "
        "schemas, and examples, strictly from the sources.",
        "endpoint_details",
        '{"endpoint_details": [{"method": str|null, "path": str|null, "parameters": '
        '[obj], "request": obj|null, "responses": [obj], "examples": [obj], "source": '
        'str|null}], "missing": [str]}',
    ),
    _structured(
        "07", "Shared schemas, enums and data constraints",
        "List shared schemas, their fields and types, enum value sets and data "
        "constraints stated by the sources.",
        "schemas",
        '{"schemas": [{"name": str|null, "fields": [obj], "enums": [obj], '
        '"constraints": str|null, "source": str|null}], "missing": [str]}',
    ),
    _structured(
        "08", "Error codes and failure behavior",
        "List every error code, its meaning and HTTP status stated by the sources.",
        "errors",
        '{"errors": [{"code": str|null, "meaning": str|null, "http_status": str|null, '
        '"applicable_to": [str], "source": str|null}], "missing": [str]}',
    ),
    _structured(
        "09", "Rate limits, timeouts, retry, idempotency and webhooks",
        "List rate limits, timeouts, retry rules, idempotency rules and webhook "
        "behavior stated by the sources.",
        "operational",
        '{"operational": [{"topic": str|null, "detail": str|null, "source": str|null}],'
        ' "missing": [str]}',
    ),
    _narrative(
        "10", "Source conflicts, gaps and unconfirmable items",
        "List anything the earlier answers may have missed, where the sources conflict, "
        "and any claim that has no source support. Do not resolve conflicts by guessing.",
    ),
)

_BY_ID = {stage.stage_id: stage for stage in STAGES}


def stage_by_id(stage_id: str) -> QueryStage:
    return _BY_ID[stage_id]
