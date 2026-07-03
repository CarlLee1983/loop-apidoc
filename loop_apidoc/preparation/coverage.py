"""Load + validate the agent-written url_sources/coverage.json ledger.

This mirrors the pydantic boundary-validation pattern in
loop_apidoc/agentcli/input_schema.py: the agent writes coverage.json, and this
module fails loudly on a malformed ledger (missing key, unknown status, invalid
JSON) *before* the deterministic coverage phase runs — never silently accepting
a broken coverage report.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError


class CoverageInputError(Exception):
    """Raised when url_sources/coverage.json is unreadable or malformed."""


class ExpectedSource(str, Enum):
    NAV = "nav"
    SITEMAP = "sitemap"
    USER = "user"


class ResultStatus(str, Enum):
    FETCHED = "fetched"
    FETCHED_RENDERED = "fetched_rendered"
    EMPTY_SUSPECT = "empty_suspect"
    FETCH_FAILED = "fetch_failed"
    AUTH_REQUIRED = "auth_required"
    SKIPPED_BY_USER = "skipped_by_user"


class FetchMethod(str, Enum):
    DEFUDDLE = "defuddle"
    PLAYWRIGHT = "playwright"


class CoverageExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str | None = None
    source: ExpectedSource


class CoverageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    status: ResultStatus
    file: str | None = None
    method: FetchMethod | None = None


class UrlCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_url: str
    confirmed_by_user: bool = False
    expected: list[CoverageExpected] = []
    results: list[CoverageResult] = []


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(part) for part in err["loc"]) or "(root)"
    return f"{loc}: {err['msg']}"


def load_coverage(path: Path) -> UrlCoverage:
    """Read + validate coverage.json. Fail loud on any malformed input."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CoverageInputError(f"cannot read coverage file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CoverageInputError(f"coverage.json is not valid JSON: {exc}") from exc
    try:
        return UrlCoverage.model_validate(data)
    except ValidationError as exc:
        raise CoverageInputError(
            f"coverage.json schema error: {_first_error(exc)}"
        ) from exc
